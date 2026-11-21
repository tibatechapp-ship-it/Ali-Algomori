"""Real format readers with specialized libraries and honest capability reporting.

The v0.5.0 validators inspect bytes structurally (magic, IFDs, text
sections). That proves format validity, not that the DATA inside is what it
claims. v0.6.0 adds real readers:

- LAS (CWLS Log ASCII Standard, well logs)  -> lasio
- GeoTIFF (DEM and raster grids)            -> tifffile
- GeoPackage (OGG SQLite container)         -> sqlite3 (stdlib, the
  format's actual engine) + pyproj for SRS definition verification

Every reader returns the same honest triple:
    {ok, data, findings, evidence: {read, verified, unverifiable}}

- When the specialized library is ABSENT, the reader never fakes a result:
  it reports READER_LIB_ABSENT and an unverifiable evidence entry. Absence
  of a tool is a limitation to declare, not a reason to guess.
- When the library is present but the file is broken, the failure is a
  finding with its own specific code — never a silent pass.
- Reader codes live here (R severities), separate from the text-level
  validator contract in validators.py, because they are different layers
  of proof (reception safety != format validity != content claims).
"""
from __future__ import annotations

import importlib.metadata
import re
import sqlite3
import struct
import warnings
from typing import Any, Dict, List, Optional, Tuple

from .evidence import (compile_evidence, ev_read, ev_unverifiable,
                       ev_verified)
from .vertical import (classify_vertical_geokeys,
                       las_depth_datum, vertical_evidence,
                       vertical_findings)

GPKG_APP_ID = 0x47504B47  # "GPKG"
_GPKG_META_TABLES = ("gpkg_spatial_ref_sys", "gpkg_contents",
                     "gpkg_geometry_columns")

# Reader finding severities (contract is stable; tests assert them).
R = {
    "READER_LIB_ABSENT": "info",
    "LAS_READER_PARSE_FAILED": "error",
    "LAS_READER_ROWS_MISMATCH": "error",
    "LAS_READER_NON_NUMERIC": "error",
    "LAS_CURVE_UNIT_MISSING": "warning",
    "TIFF_READER_PARSE_FAILED": "error",
    "TIFF_GEOKEYS_MISSING": "warning",
    "TIFF_GEOKEYS_UNREADABLE": "error",
    "TIFF_EXTENT_INCONSISTENT": "error",
    "TIFF_NODATA_INVALID": "warning",
    "CRS_READER_MISMATCH": "error",
    "GPKG_NOT_GPKG": "error",
    "GPKG_CORRUPT_DB": "error",
    "GPKG_MISSING_META_TABLES": "error",
    "GPKG_CONTENTS_EMPTY": "warning",
    "GPKG_GEOM_MAGIC_INVALID": "error",
    "GPKG_GEOM_SRS_MISMATCH": "error",
    "GPKG_CONTENTS_BBOX_MISMATCH": "error",
    "GPKG_SRS_UNRESOLVED": "warning",
    "CRS_SRS_DEFINITION_MISMATCH": "error",
}


def _rf(code: str, message: str) -> dict:
    return {"code": code, "severity": R[code], "message": message}


def _lib_version(dist: str) -> Optional[str]:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def capabilities() -> Dict[str, Optional[str]]:
    """Version of every specialized engine this layer can use, or None.

    The data layer must be able to state which engines verified its claims.
    A None here means every claim that would need that engine stays
    unverifiable — reported, never hidden.
    """
    return {
        "lasio": _lib_version("lasio"),
        "tifffile": _lib_version("tifffile"),
        "pyproj": _lib_version("pyproj"),
        "numpy": _lib_version("numpy"),
        "sqlite3": sqlite3.sqlite_version,
    }


def _unavailable(fmt: str, lib: str) -> dict:
    return {"ok": False, "data": None, "findings": [_rf(
        "READER_LIB_ABSENT",
        f"{fmt} deep read not performed: {lib} is not installed")],
        "evidence": compile_evidence([], [], [ev_unverifiable(
            "READER_LIB_ABSENT", f"{fmt} content claims not verified",
            reason=f"{lib} absent — the layer cannot read the real "
                   f"structure and refuses to pretend it did")])}


def _evidence(read: List[dict], verified: List[dict],
              unverifiable: List[dict]) -> dict:
    return compile_evidence(read, verified, unverifiable)


# --- LAS: CWLS Log ASCII Standard (well logs) -------------------------------

def read_las(path: str) -> dict:
    """Real LAS read via lasio, cross-checking the text parser's claims."""
    cap = capabilities()
    if not cap["lasio"]:
        return _unavailable("LAS", "lasio")
    import lasio  # deferred: optional dependency

    read_l, ver_l, unv_l = [], [], []
    findings: List[dict] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            las = lasio.read(str(path))
    except Exception as exc:  # lasio raises several exception types
        findings.append(_rf("LAS_READER_PARSE_FAILED",
                            f"lasio could not parse: {type(exc).__name__}: "
                            f"{exc}"))
        read_l.append(ev_read("LAS_READER_ATTEMPTED",
                              f"lasio parse failed ({type(exc).__name__})"))
        return {"ok": False, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}

    rows = int(len(las.data)) if las.data is not None else 0
    curves = [str(c.mnemonic) for c in las.curves]
    units = [str(c.unit or "") for c in las.curves]
    read_l.append(ev_read(
        "LAS_READER_OPENED",
        f"lasio read OK: version={_las_version(las)}, rows={rows}, "
        f"curves={curves}"))

    # Independent row-count check: lasio's data vs STRT/STOP/STEP arithmetic.
    try:
        strt = float(las.well["STRT"].value)
        stop = float(las.well["STOP"].value)
        step = float(las.well["STEP"].value)
        if step != 0 and stop > strt:
            expected = int(round((stop - strt) / step)) + 1
            if rows != expected:
                findings.append(_rf(
                    "LAS_READER_ROWS_MISMATCH",
                    f"lasio read {rows} data rows; STRT/STOP/STEP imply "
                    f"{expected} — truncated or tampered"))
            else:
                ver_l.append(ev_verified(
                    "LAS_READER_ROWS_VERIFIED",
                    f"{rows} rows match STRT/STOP/STEP arithmetic",
                    check="independent recomputation by lasio of the "
                          "declared depth interval"))
    except (KeyError, ValueError, TypeError):
        unv_l.append(ev_unverifiable(
            "LAS_READER_HEADER_INCOMPLETE",
            "STRT/STOP/STEP incomplete; row arithmetic impossible",
            reason="header lacks machine-usable depth interval"))

    # Curve units: a curve without a unit is a claim nobody signed.
    for mnem, unit in zip(curves, units):
        if not unit.strip():
            findings.append(_rf(
                "LAS_CURVE_UNIT_MISSING",
                f"curve {mnem} has no unit in ~C — value meaning undefined"))

    # Null value: what lasio actually honored.
    null = _las_null(las)
    if null is not None:
        read_l.append(ev_read("LAS_READER_NULL", f"NULL declared as {null}"))
        if rows and las.data is not None:
            import numpy as _np
            try:
                matrix = _np.asarray(las.data, dtype=float)
            except (ValueError, TypeError):
                # lasio silently falls back to string columns when the data
                # section carries non-numeric junk (e.g. NUL bytes). That is
                # corruption, not data — refuse, never guess.
                findings.append(_rf(
                    "LAS_READER_NON_NUMERIC",
                    "lasio parsed curve data as non-numeric values — the "
                    "data section is corrupted or carries embedded junk"))
                matrix = None
            if matrix is not None:
                nan_cells = int(_np.isnan(matrix).sum())
                if nan_cells:
                    read_l.append(ev_read(
                        "LAS_READER_NULL_CELLS",
                        f"{nan_cells} cells became NaN at NULL={null}"))
                ver_l.append(ev_verified(
                    "LAS_READER_NULL_HONORED",
                    f"null value {null} applied by lasio to the data matrix",
                    check="lasio replaced the declared NULL with NaN in the "
                          "parsed matrix"))
    else:
        unv_l.append(ev_unverifiable(
            "LAS_READER_NULL_ABSENT",
            "no NULL value applied",
            reason="well section lacks NULL; sentinels in data cannot be "
                   "distinguished from real values"))

    # Depth datum + CRS: LAS 1.2/2.0 declares neither.
    datum_findings, datum_evidence = las_depth_datum(curves)
    findings.extend(datum_findings)
    unv_l.extend(datum_evidence["unverifiable"])
    read_l.extend(datum_evidence["read"])
    unv_l.append(ev_unverifiable(
        "CRS_NONE_DECLARED",
        "LAS 1.2/2.0 carries no CRS field",
        reason="the format has no CRS mechanism; horizontal reference is "
               "external knowledge, not file content"))

    data = {"engine": "lasio", "engine_version": cap["lasio"],
            "version": _las_version(las), "rows": rows, "curves": curves,
            "units": units, "null": _las_null(las)}
    return {"ok": True, "data": data, "findings": findings,
            "evidence": _evidence(read_l, ver_l, unv_l)}


def _las_version(las: Any) -> Optional[str]:
    try:
        return str(las.version["VERS"].value)
    except Exception:
        return None


def _las_null(las: Any) -> Optional[float]:
    try:
        return float(las.well["NULL"].value)
    except (KeyError, TypeError, ValueError):
        return None


# --- GeoTIFF ----------------------------------------------------------------

def _tag(page: Any, code: int) -> Any:
    try:
        return page.tags[code].value
    except (KeyError, AttributeError):
        return None


def parse_geokeys(raw: Any, ascii_params: Any = None,
                  double_params: Any = None) -> Optional[Dict[int, object]]:
    """Minimal GeoKeyDirectory (34735) parser: inline shorts + 34736/34737."""
    if not raw or len(raw) < 4:
        return None
    try:
        raw = list(raw)
        count = int(raw[3])
        keys: Dict[int, object] = {}
        for i in range(count):
            base = 4 + 4 * i
            if base + 3 >= len(raw):
                return keys if keys else None
            kid, loc, cnt, off = raw[base:base + 4]
            if loc == 0:
                # GeoTIFF spec: value packed in the value_offset field itself
                # (single SHORT). Multi-value inline entries are spec-quirky:
                # report the raw pair honestly instead of guessing.
                keys[kid] = off if cnt == 1 else tuple(raw[off:off + cnt])
            elif loc == 34736 and double_params is not None:
                vals = list(double_params[off:off + cnt])
                keys[kid] = vals[0] if cnt == 1 else tuple(vals)
            elif loc == 34737 and ascii_params is not None:
                s = ascii_params[off:off + cnt].rstrip("\x00")
                keys[kid] = s
        return keys
    except (TypeError, ValueError):
        return None


def read_geotiff(path: str, declared_crs: Optional[str] = None) -> dict:
    """Real GeoTIFF read via tifffile: geokeys, georeferencing, vertical."""
    cap = capabilities()
    if not cap["tifffile"]:
        return _unavailable("GeoTIFF", "tifffile")
    import tifffile

    read_l, ver_l, unv_l = [], [], []
    findings: List[dict] = []
    try:
        tf = tifffile.TiffFile(str(path))
        page = tf.pages[0]
        series = tf.series[0]
        shape = list(series.shape)
        dtype = str(series.dtype)
    except Exception as exc:
        findings.append(_rf("TIFF_READER_PARSE_FAILED",
                            f"tifffile could not parse: {type(exc).__name__}: "
                            f"{exc}"))
        read_l.append(ev_read("TIFF_READER_ATTEMPTED",
                              f"tifffile parse failed ({type(exc).__name__})"))
        return {"ok": False, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}

    read_l.append(ev_read("TIFF_READER_OPENED",
                          f"tifffile read OK: shape={shape}, dtype={dtype}"))

    scale = _tag(page, 33550)
    tiepoint = _tag(page, 33922)
    extent: Optional[dict] = None
    if scale and tiepoint and len(shape) == 2:
        sx, sy = float(scale[0]), float(scale[1])
        x0, y0 = float(tiepoint[3]), float(tiepoint[4])
        h, w = shape[0], shape[1]
        if sx <= 0 or sy <= 0 or h <= 0 or w <= 0:
            findings.append(_rf(
                "TIFF_EXTENT_INCONSISTENT",
                f"non-positive pixel scale ({sx}, {sy}) or dims "
                f"({w}x{h}) — georeferencing is broken"))
        else:
            extent = {"minx": x0, "miny": y0 - sy * h,
                      "maxx": x0 + sx * w, "maxy": y0}
            read_l.append(ev_read(
                "TIFF_GEOREFERENCING_READ",
                f"pixel scale {sx}x{sy}, tiepoint origin ({x0}, {y0})"))
            ver_l.append(ev_verified(
                "TIFF_EXTENT_RECOMPUTED",
                f"extent {extent} recomputed from tiepoint+scale",
                check="independent corner arithmetic: min/max edges from "
                      "ModelTiepoint + ModelPixelScale * dims"))
    elif not scale or not tiepoint:
        unv_l.append(ev_unverifiable(
            "TIFF_GEOREFERENCING_ABSENT",
            "no ModelPixelScale/ModelTiepoint tags",
            reason="pixel coordinates cannot be mapped to world coordinates; "
                   "any placement would be invented"))

    # GeoKeys: the horizontal + vertical claim.
    gk_raw = _tag(page, 34735)
    geokeys = parse_geokeys(gk_raw, _tag(page, 34737), _tag(page, 34736))
    if gk_raw is None:
        findings.append(_rf("TIFF_GEOKEYS_MISSING",
                            "no GeoKeyDirectory (34735) — raster is not "
                            "georeferenced in GeoTIFF terms"))
        unv_l.append(ev_unverifiable(
            "TIFF_GEOKEYS_MISSING",
            "no CRS claim inside the file",
            reason="GeoKeyDirectory absent; CRS must come from external "
                   "metadata and cannot be confirmed"))
    elif geokeys is None:
        findings.append(_rf("TIFF_GEOKEYS_UNREADABLE",
                            "GeoKeyDirectory present but unparsable"))
        unv_l.append(ev_unverifiable(
            "TIFF_GEOKEYS_UNREADABLE",
            "GeoKeyDirectory malformed",
            reason="structure exists but keys cannot be extracted"))
    else:
        read_l.append(ev_read("TIFF_GEOKEYS_READ",
                              f"GeoKeys parsed: {sorted(geokeys.items())}"))
        _verify_geotiff_crs(geokeys, declared_crs, findings, ver_l, unv_l)
        v = classify_vertical_geokeys(geokeys)
        findings.extend(vertical_findings(v))
        v_evidence = vertical_evidence(v)
        read_l.extend(v_evidence["read"])
        ver_l.extend(v_evidence["verified"])
        unv_l.extend(v_evidence["unverifiable"])

    # GDAL nodata tag honesty.
    nodata_raw = _tag(page, 42113)
    nodata: Optional[float] = None
    if nodata_raw is not None:
        try:
            nodata = float(nodata_raw)
        except (TypeError, ValueError):
            findings.append(_rf("TIFF_NODATA_INVALID",
                                f"GDAL_NODATA '{nodata_raw}' is not numeric"))
            unv_l.append(ev_unverifiable(
                "TIFF_NODATA_INVALID",
                "nodata tag unparsable",
                reason="masking values in the grid cannot be interpreted"))
    data = {"engine": "tifffile", "engine_version": cap["tifffile"],
            "shape": shape, "dtype": dtype, "scale": _as_floats(scale),
            "tiepoint": _as_floats(tiepoint), "extent": extent,
            "crs_epsg": _geokey_epsg(geokeys), "geokeys": _plain(geokeys),
            "nodata": nodata}
    return {"ok": True, "data": data, "findings": findings,
            "evidence": _evidence(read_l, ver_l, unv_l)}


def _as_floats(vals: Any) -> Optional[List[float]]:
    try:
        return [float(v) for v in vals]
    except (TypeError, ValueError):
        return None


def _plain(geokeys: Optional[Dict[int, object]]) -> Optional[dict]:
    if geokeys is None:
        return None
    return {k: (list(v) if isinstance(v, tuple) else v)
            for k, v in geokeys.items()}


def _geokey_epsg(geokeys: Optional[Dict[int, object]]) -> Optional[int]:
    if not geokeys:
        return None
    v = geokeys.get(3072)  # ProjectedCSTypeGeoKey
    if isinstance(v, int) and v > 0:
        return v
    v = geokeys.get(2048)  # GeographicTypeGeoKey
    if isinstance(v, int) and v > 0:
        return v
    return None


def _verify_geotiff_crs(geokeys: Dict[int, object],
                        declared_crs: Optional[str], findings: List[dict],
                        ver_l: List[dict], unv_l: List[dict]) -> None:
    """Horizontal CRS claim: recognize it, and test it against declarations."""
    cap = capabilities()
    epsg = _geokey_epsg(geokeys)
    if epsg is None:
        unv_l.append(ev_unverifiable(
            "TIFF_CRS_UNRESOLVED",
            "GeoKeys carry no usable Projected/Geographic type code",
            reason="CRS claim present but not mappable to EPSG"))
        return
    if cap["pyproj"]:
        try:
            import pyproj
            pyproj.CRS.from_epsg(epsg)
            ver_l.append(ev_verified(
                "TIFF_CRS_ENGINE_VERIFIED",
                f"EPSG:{epsg} parsed by pyproj {cap['pyproj']}",
                check="pyproj CRS.from_epsg() accepted the code"))
        except Exception:
            findings.append(_rf("TIFF_GEOKEYS_UNREADABLE",
                                f"EPSG:{epsg} rejected by pyproj"))
    else:
        unv_l.append(ev_unverifiable(
            "TIFF_CRS_UNVERIFIED",
            f"EPSG:{epsg} claimed in GeoKeys",
            reason="pyproj absent; code recognized from the GeoTIFF table "
                   "but its definition could not be parsed"))
    if declared_crs:
        m = re.search(r"(\d{4,5})", declared_crs)
        declared_epsg = int(m.group(1)) if m else None
        if declared_epsg is not None and declared_epsg != epsg:
            findings.append(_rf(
                "CRS_READER_MISMATCH",
                f"declared CRS EPSG:{declared_epsg} contradicts the "
                f"GeoTIFF GeoKey EPSG:{epsg}"))
        elif declared_epsg == epsg:
            ver_l.append(ev_verified(
                "CRS_READER_MATCH",
                f"declared CRS EPSG:{declared_epsg} matches GeoKey EPSG:{epsg}",
                check="declared-vs-embedded cross-check"))


# --- GeoPackage -------------------------------------------------------------

def _gpkg_geom_header(blob: bytes) -> Tuple[Optional[int], Optional[dict],
                                            Optional[str]]:
    """Parse a GeoPackageBinary header: magic, flags, srs_id, envelope."""
    if blob is None or len(blob) < 8:
        return None, None, "blob too short for GeoPackageBinary header"
    if blob[0:2] != b"GP":
        return None, None, "magic is not b'GP'"
    flags = blob[3]
    big_endian = bool(flags & 0x01)
    env_code = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}.get(env_code)
    if env_len is None:
        return None, None, f"unknown envelope code {env_code}"
    fmt = ">" if big_endian else "<"
    srs_id = struct.unpack(fmt + "i", blob[4:8])[0]
    env_bytes = blob[8:8 + 8 * env_len]
    env_vals = struct.unpack(fmt + f"{env_len}d", env_bytes) if env_len else ()
    envelope = None
    if env_len == 4:
        envelope = {"minx": env_vals[0], "maxx": env_vals[1],
                    "miny": env_vals[2], "maxy": env_vals[3]}
    return srs_id, envelope, None


def read_geopackage(path: str, declared_crs: Optional[str] = None) -> dict:
    """Real GeoPackage read via its actual engine (SQLite), spec-checked."""
    read_l, ver_l, unv_l = [], [], []
    findings: List[dict] = []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        findings.append(_rf("GPKG_CORRUPT_DB",
                            f"cannot open as SQLite: {exc}"))
        return {"ok": False, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}
    try:
        app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        # Not a valid SQLite database at all: garbage in a .gpkg name.
        _gpkg_close(conn)
        findings.append(_rf("GPKG_CORRUPT_DB",
                            f"SQLite rejects the file: {exc}"))
        return {"ok": False, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}
    if app_id != GPKG_APP_ID:
        _gpkg_close(conn)
        findings.append(_rf(
            "GPKG_NOT_GPKG",
            f"application_id is 0x{app_id:08X}, not 'GPKG' "
            f"(0x47504B47) — this is not a GeoPackage"))
        read_l.append(ev_read("GPKG_APP_ID_READ",
                              f"application_id 0x{app_id:08X}"))
        return {"ok": False, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}
    read_l.append(ev_read("GPKG_APP_ID_READ",
                          "application_id = 'GPKG' (0x47504B47)"))

    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [t for t in _GPKG_META_TABLES if t not in names]
    if missing:
        _gpkg_close(conn)
        findings.append(_rf(
            "GPKG_MISSING_META_TABLES",
            f"required table(s) missing: {', '.join(missing)}"))
        unv_l.append(ev_unverifiable(
            "GPKG_MISSING_META_TABLES",
            "core GeoPackage metadata absent",
            reason="without gpkg_contents/spatial_ref_sys the layer "
                   "cannot even name what data claims to be"))
        return {"ok": True, "data": None, "findings": findings,
                "evidence": _evidence(read_l, ver_l, unv_l)}

    srs_rows = {r[0]: r for r in conn.execute(
        "SELECT srs_id, organization, organization_coordsys_id, definition"
        " FROM gpkg_spatial_ref_sys")}
    contents = list(conn.execute(
        "SELECT table_name, data_type, srs_id, min_x, min_y, max_x, max_y"
        " FROM gpkg_contents"))
    if not contents:
        findings.append(_rf("GPKG_CONTENTS_EMPTY",
                            "gpkg_contents has no rows"))
    read_l.append(ev_read(
        "GPKG_CONTENTS_READ",
        f"gpkg_contents: {[(r[0], r[1], r[2]) for r in contents]}"))

    # SRS definitions: verified only when a real engine parses them.
    cap = capabilities()
    for srs_id, row in srs_rows.items():
        if srs_id in (0, -1):
            continue  # undefined / none: honest non-georeferencing
        definition = row[3]
        if not definition:
            findings.append(_rf("GPKG_SRS_UNRESOLVED",
                                f"srs_id {srs_id} has empty definition"))
            unv_l.append(ev_unverifiable(
                "GPKG_SRS_UNRESOLVED", f"srs_id {srs_id} undefined",
                reason="empty definition in gpkg_spatial_ref_sys"))
            continue
        if cap["pyproj"]:
            try:
                import pyproj
                crs = pyproj.CRS.from_wkt(definition)
                org_epsg = row[2]
                parsed = crs.to_epsg()
                if org_epsg and parsed and org_epsg != parsed:
                    findings.append(_rf(
                        "CRS_SRS_DEFINITION_MISMATCH",
                        f"srs_id {srs_id}: organization says EPSG:"
                        f"{org_epsg} but the WKT definition parses as "
                        f"EPSG:{parsed}"))
                else:
                    ver_l.append(ev_verified(
                        "GPKG_SRS_ENGINE_VERIFIED",
                        f"srs_id {srs_id} definition parsed by pyproj "
                        f"{cap['pyproj']} (EPSG:{parsed})",
                        check="pyproj CRS.from_wkt() accepted the "
                              "definition"))
            except Exception as exc:
                findings.append(_rf("GPKG_SRS_UNRESOLVED",
                                    f"srs_id {srs_id} definition rejected "
                                    f"by pyproj: {exc}"))
        else:
            unv_l.append(ev_unverifiable(
                "GPKG_SRS_UNVERIFIED",
                f"srs_id {srs_id} has a WKT definition",
                reason="pyproj absent; definition present but unparsed"))

    # Feature tables: real geometry header validation.
    features: Dict[str, dict] = {}
    for table_name, data_type, srs_id, min_x, min_y, max_x, max_y in contents:
        if data_type != "features":
            continue
        geom_col_rows = list(conn.execute(
            "SELECT column_name, srs_id FROM gpkg_geometry_columns "
            "WHERE table_name = ?", (table_name,)))
        if not geom_col_rows:
            continue
        geom_col, declared_geom_srs = geom_col_rows[0]
        rows = conn.execute(
            f'SELECT "{geom_col}" FROM "{table_name}"').fetchall()
        n_geom = bad_magic = srs_mismatch = null_geoms = 0
        bbox = {"minx": None, "miny": None, "maxx": None, "maxy": None}
        for (blob,) in rows:
            if blob is None:
                null_geoms += 1
                continue
            header_srs, envelope, err = _gpkg_geom_header(blob)
            if err:
                bad_magic += 1
                continue
            n_geom += 1
            if declared_geom_srs is not None and header_srs != declared_geom_srs:
                srs_mismatch += 1
            if envelope:
                bbox["minx"] = (envelope["minx"] if bbox["minx"] is None
                                else min(bbox["minx"], envelope["minx"]))
                bbox["maxx"] = (envelope["maxx"] if bbox["maxx"] is None
                                else max(bbox["maxx"], envelope["maxx"]))
                bbox["miny"] = (envelope["miny"] if bbox["miny"] is None
                                else min(bbox["miny"], envelope["miny"]))
                bbox["maxy"] = (envelope["maxy"] if bbox["maxy"] is None
                                else max(bbox["maxy"], envelope["maxy"]))
        if bad_magic:
            findings.append(_rf(
                "GPKG_GEOM_MAGIC_INVALID",
                f"{bad_magic} geometry blob(s) in {table_name} lack the "
                f"'GP' GeoPackageBinary magic"))
        if srs_mismatch:
            findings.append(_rf(
                "GPKG_GEOM_SRS_MISMATCH",
                f"{srs_mismatch} geometry header(s) in {table_name} "
                f"declare srs_id differing from gpkg_geometry_columns "
                f"({declared_geom_srs})"))
        features[table_name] = {
            "count": len(rows), "geom_count": n_geom,
            "null_geoms": null_geoms, "srs_id": srs_id,
            "bbox": bbox}
        read_l.append(ev_read(
            "GPKG_FEATURES_READ",
            f"{table_name}: {n_geom} parsed geometries "
            f"({null_geoms} null), bbox {bbox}"))
        ver_l.append(ev_verified(
            "GPKG_FEATURE_COUNT_VERIFIED",
            f"{table_name}: {len(rows)} rows counted by SQLite itself",
            check="SELECT count over the feature table (the format's "
                  "own engine)"))
        # Declared contents bbox vs real envelope union.
        declared_bbox = (min_x, min_y, max_x, max_y)
        if all(v is not None for v in declared_bbox) and n_geom:
            eps = 1e-6
            ok_bbox = (abs(bbox["minx"] - min_x) < eps
                       and abs(bbox["maxx"] - max_x) < eps
                       and abs(bbox["miny"] - min_y) < eps
                       and abs(bbox["maxy"] - max_y) < eps)
            if ok_bbox:
                ver_l.append(ev_verified(
                    "GPKG_CONTENTS_BBOX_VERIFIED",
                    f"declared contents bbox matches the geometry "
                    f"envelopes for {table_name}",
                    check="envelope union recomputed from parsed "
                          "GeoPackageBinary headers"))
            else:
                findings.append(_rf(
                    "GPKG_CONTENTS_BBOX_MISMATCH",
                    f"gpkg_contents bbox {declared_bbox} contradicts "
                    f"actual geometry envelope union {tuple(bbox.values())} "
                    f"for {table_name}"))

    # Declared-CRS cross-check against gpkg_contents.
    if declared_crs and contents:
        m = re.search(r"(\d{4,5})", declared_crs)
        declared_epsg = int(m.group(1)) if m else None
        content_srs = contents[0][2]
        if declared_epsg is not None and declared_epsg != content_srs:
            findings.append(_rf(
                "CRS_READER_MISMATCH",
                f"declared CRS EPSG:{declared_epsg} contradicts "
                f"gpkg_contents srs_id {content_srs}"))
        elif declared_epsg == content_srs:
            ver_l.append(ev_verified(
                "CRS_READER_MATCH",
                f"declared CRS EPSG:{declared_epsg} matches "
                f"gpkg_contents srs_id",
                check="declared-vs-registered cross-check"))

    data = {"engine": "sqlite3", "engine_version": cap["sqlite3"],
            "contents": [{"table": r[0], "data_type": r[1], "srs_id": r[2]}
                         for r in contents],
            "features": features,
            "srs_count": len(srs_rows)}
    return {"ok": True, "data": data, "findings": findings,
            "evidence": _evidence(read_l, ver_l, unv_l)}


def _gpkg_close(conn: Any) -> None:
    try:
        conn.close()
    except sqlite3.Error:
        pass
