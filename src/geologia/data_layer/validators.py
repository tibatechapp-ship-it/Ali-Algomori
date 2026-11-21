# Data verification layer: format validators with deterministic findings.
# Part of the binding acceptance standard: real data in -> verified -> only
# then may it enter any task. No dataset is trusted without a checksum and a
# passed format validation.
from __future__ import annotations

import csv
import json
import re
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_NULL_SENTINELS = {"", "null", "nan", "na", "-", "none"}

# v0.5.0: corrupted-file hardening. A text file whose lines exceed this bound
# is refused before parsing (pathological memory input), and NUL bytes in text
# formats are treated as corruption, not data.
_MAX_LINE_BYTES = 1 << 20  # 1 MiB per line

# v0.5.0 CRS consistency (declared vs observed): geographic CRS declared for
# data that looks projected (or the reverse) is an error, not a note —
# it would poison every downstream transform.
_GEO_CRS_RE = re.compile(r"(4326|CRS84|WGS\s*84)", re.I)
_UTM_CRS_RE = re.compile(r"(?:EPSG\s*:\s*)?32[67](\d{2})\b|UTM", re.I)

# Codes with severities (contract is stable; tests assert them).
F = {
    "GEN_FILE_MISSING": "error",
    "GEN_EMPTY_FILE": "error",
    "GEN_UNKNOWN_TYPE": "warning",
    "TIFF_MAGIC_UNKNOWN": "error",
    "TIFF_NO_IFD": "error",
    "TIFF_MISSING_TAG": "error",
    "TIFF_SIZE_MISMATCH": "error",
    "TIFF_TRUNCATED": "error",
    "TIFF_UNSUPPORTED_COMPRESSION": "warning",
    "TIFF_GEO_TAGS": "info",
    "TIFF_OK": "info",
    "LAS_NO_VERSION": "error",
    "LAS_VERSION_UNSUPPORTED": "warning",
    "LAS_NO_WELL_HEADER": "error",
    "LAS_NO_NULL": "warning",
    "LAS_NO_CURVES": "error",
    "LAS_STOP_LE_STRT": "error",
    "LAS_STEP_ZERO": "error",
    # v0.5.0 hardening: a declared-vs-actual row mismatch is corruption
    # (truncation or tampering), not a review note. It now fails validation.
    "LAS_DATA_ROWS_MISMATCH": "error",
    "LAS_CONTROL_CHARS": "error",
    "LAS_LINE_TOO_LONG": "error",
    "LAS_OK": "info",
    "GEOJSON_PARSE_ERROR": "error",
    "GEOJSON_NO_FEATURES": "error",
    "GEOJSON_BAD_GEOMETRY_TYPE": "error",
    "GEOJSON_BAD_COORDS": "error",
    "GEOJSON_NO_CRS": "info",
    "GEOJSON_OK": "info",
    "CSV_EMPTY": "error",
    "CSV_NO_HEADER": "error",
    "CSV_MISSING_VALUES": "warning",
    "CSV_NON_NUMERIC": "error",
    "CSV_DUP_ROWS": "warning",
    "CSV_LATLON_RANGE": "error",
    # v0.5.0 corruption + integrity hardening:
    "CSV_CONTROL_CHARS": "error",
    "CSV_LINE_TOO_LONG": "error",
    "CSV_ID_CONFLICT": "error",
    "CSV_OK": "info",
    # v0.5.0 declared-vs-observed CRS consistency codes:
    "CRS_MISMATCH_PROJECTED_GEO": "error",
    "CRS_MISMATCH_GEO_PROJECTED": "error",
    "CRS_GEOJSON_NON_WGS84": "error",
    "CRS_GEOJSON_CRS_UNRECOGNIZED": "warning",
    "CRS_LOCAL_NO_TRANSFORM": "warning",
    "CRS_UNITS_SUSPECT": "warning",
    "CRS_DECLARED_OK": "info",
    "CRS_AXIS_ORDER_NOTE": "info",
    "CRS_NONE_DECLARED": "info",
}

VALID_TYPES = ("las", "geojson", "csv", "tiff", "auto")


def _finding(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "severity": F[code], "message": message}


def detect_type(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix in (".las",):
        return "las"
    if suffix in (".geojson", ".json"):
        return "geojson"
    if suffix in (".csv", ".tsv"):
        return "csv"
    if suffix in (".tif", ".tiff"):
        return "tiff"
    if suffix in (".gpkg",):
        return "gpkg"
    return None


# --- corruption pre-scan (text formats) -------------------------------------
def _prescan_text(path: Path, code_nul: str, code_line: str,
                  findings: List[dict]) -> bool:
    """Refuse NUL bytes and pathological lines before any parsing.
    Returns False when a hard corruption was found."""
    raw = path.read_bytes()
    if b"\x00" in raw:
        findings.append(_finding(code_nul,
                                 "NUL byte in text data — refusing to parse as text"))
        return False
    for ln in raw.splitlines():
        if len(ln) > _MAX_LINE_BYTES:
            findings.append(_finding(code_line,
                                     f"line exceeds {_MAX_LINE_BYTES} bytes "
                                     f"(found {len(ln)})"))
            return False
    return True


# --- declared-vs-observed CRS consistency -----------------------------------
def classify_crs(declared: Optional[str]) -> Tuple[str, Optional[int]]:
    """Classify a declared CRS string -> ("geo_deg"|"utm"|"local"|"unknown", zone)."""
    if not declared:
        return "unknown", None
    s = str(declared).strip()
    if _GEO_CRS_RE.search(s):
        return "geo_deg", None
    m = _UTM_CRS_RE.search(s)
    if m:
        zone = int(m.group(1)) if m.group(1) else None
        return "utm", zone
    if re.search(r"local|depth", s, re.I):
        return "local", None
    return "unknown", None


def _utm_as_degrees_conflict(vals: List[float]) -> bool:
    """All values look like geographic degrees while a projected CRS was declared."""
    return bool(vals) and all(abs(v) <= 360 for v in vals)


def _check_crs_csv(declared: Optional[str], declared_units: Optional[str],
                   lat_vals: List[float], lon_vals: List[float],
                   en_vals: List[float], findings: List[dict]) -> None:
    kind, zone = classify_crs(declared)
    if kind == "unknown":
        if declared:
            findings.append(_finding("CRS_NONE_DECLARED",
                                     f"declared CRS {declared!r} unrecognized — treated as opaque"))
        else:
            findings.append(_finding("CRS_NONE_DECLARED",
                                     "no CRS declared — georeferencing rests on "
                                     "column semantics alone"))
        return
    if kind == "geo_deg":
        if lat_vals or lon_vals:
            findings.append(_finding("CRS_DECLARED_OK",
                                     "declared geographic CRS matches lat/lon degree columns"))
        elif en_vals and max((abs(v) for v in en_vals), default=0) > 360:
            findings.append(_finding("CRS_MISMATCH_GEO_PROJECTED",
                                     f"declared geographic CRS but coordinate values look "
                                     f"projected (max |value| "
                                     f"{max(abs(v) for v in en_vals):.1f} ≫ 360°)"))
        else:
            findings.append(_finding("CRS_DECLARED_OK",
                                     "declared geographic CRS; no contradicting "
                                     "magnitudes observed"))
    elif kind == "utm":
        if (lat_vals and lon_vals
                and _utm_as_degrees_conflict(lat_vals + lon_vals)):
            findings.append(_finding("CRS_MISMATCH_PROJECTED_GEO",
                                     f"declared projected CRS (UTM zone {zone}, metres) but "
                                     f"lat/lon columns hold geographic degrees — refusing "
                                     f"to guess the transform"))
        elif en_vals and _utm_as_degrees_conflict(en_vals):
            findings.append(_finding("CRS_MISMATCH_GEO_PROJECTED",
                                     "declared projected CRS but easting/northing values "
                                     "look like degrees"))
        else:
            findings.append(_finding("CRS_DECLARED_OK",
                                     f"declared projected CRS (UTM zone {zone}) consistent "
                                     f"with observed coordinate magnitudes"))
    elif kind == "local":
        findings.append(_finding("CRS_LOCAL_NO_TRANSFORM",
                                 f"declared local CRS {declared!r}: unusable for georeferencing "
                                 f"until a pinned transform is registered"))
    # units sanity (any declared kind)
    du = (declared_units or "").lower()
    if "ft" in du or "foot" in du:
        pass  # imperial declaration: magnitudes checked in the LAS branch
    # no-op for CSV here; documented for future expansion


def _check_crs_geojson(declared: Optional[str], findings: List[dict]) -> None:
    kind, _zone = classify_crs(declared)
    if kind == "geo_deg":
        findings.append(_finding("CRS_DECLARED_OK",
                                 "declared WGS84 geographic CRS matches RFC 7946 content"))
        findings.append(_finding("CRS_AXIS_ORDER_NOTE",
                                 "GeoJSON axis order is lon,lat; EPSG:4326 formal order is "
                                 "lat,lon — platform assumes RFC 7946 order, recorded explicitly"))
    elif kind == "utm":
        findings.append(_finding("CRS_GEOJSON_NON_WGS84",
                                 "declared projected CRS contradicts the file: RFC 7946 "
                                 "content is WGS84 lon/lat degrees by specification"))
    elif kind == "local":
        findings.append(_finding("CRS_GEOJSON_NON_WGS84",
                                 f"declared local CRS {declared!r} contradicts RFC 7946 "
                                 f"WGS84 lon/lat content"))
    elif declared:
        findings.append(_finding("CRS_GEOJSON_CRS_UNRECOGNIZED",
                                 f"declared CRS {declared!r} unrecognized; content is "
                                 f"WGS84 lon/lat per RFC 7946"))
    else:
        findings.append(_finding("CRS_NONE_DECLARED",
                                 "no crs member: RFC 7946 assumes WGS84 — record the assumption"))


def _check_crs_las_units(declared_units: Optional[str], strt: Optional[float],
                         stop: Optional[float], findings: List[dict]) -> None:
    if not declared_units or strt is None or stop is None:
        return
    du = declared_units.lower()
    if ("ft" in du or "foot" in du) and max(abs(strt), abs(stop)) < 100:
        findings.append(_finding("CRS_UNITS_SUSPECT",
                                 f"declared units {declared_units!r} but depth magnitudes "
                                 f"({strt}-{stop}) look metric"))
    if ("m" == du.strip() or du.startswith("m;") or du.startswith("meter")) \
            and max(abs(strt), abs(stop)) > 6000:
        findings.append(_finding("CRS_UNITS_SUSPECT",
                                 f"declared units {declared_units!r} but depth magnitudes "
                                 f"({strt}-{stop}) look like feet"))


def _parse_las_sections(text: str) -> Dict[str, Dict[str, str]]:
    """Minimal LAS header parser: section letter -> {key: value}."""
    sections: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("~"):
            letter = line[1:2].upper()
            current = letter if letter.isalpha() else None
            sections.setdefault(current or "_", {})
            continue
        if current is None or not line or line.startswith("#"):
            continue
        if current == "A":
            continue
        if "." in line:
            name, rest = line.split(".", 1)
            if rest.startswith(" "):
                rest = rest[1:]
            value = rest.split(":", 1)[0].strip()
            sections[current][name.strip().upper()] = value
    return sections


def _check_las(path: Path, findings: List[dict], declared_crs: Optional[str] = None,
               declared_units: Optional[str] = None) -> None:
    if not _prescan_text(path, "LAS_CONTROL_CHARS", "LAS_LINE_TOO_LONG", findings):
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = _parse_las_sections(text)
    ver = sections.get("V", {})
    well = sections.get("W", {})
    curves = sections.get("C", {})
    if "VERS" not in ver:
        findings.append(_finding("LAS_NO_VERSION", "missing ~V VERS field"))
    elif ver["VERS"] not in ("1.2", "2.0"):
        findings.append(_finding("LAS_VERSION_UNSUPPORTED",
                                 f"unsupported LAS version {ver['VERS']}"))
    if not well:
        findings.append(_finding("LAS_NO_WELL_HEADER", "missing ~W well section"))
        return
    if "NULL" not in well:
        findings.append(_finding("LAS_NO_NULL", "NULL value not declared"))
    for key in ("STRT", "STOP", "STEP"):
        if key not in well:
            findings.append(_finding("LAS_NO_WELL_HEADER", f"missing ~W {key}"))
    strt_f = stop_f = None
    try:
        strt, stop, step = (float(well[k]) for k in ("STRT", "STOP", "STEP"))
        strt_f, stop_f = strt, stop
        if stop <= strt:
            findings.append(_finding("LAS_STOP_LE_STRT", f"STOP {stop} <= STRT {strt}"))
        elif step == 0:
            findings.append(_finding("LAS_STEP_ZERO", "STEP is zero"))
        else:
            expected_rows = int(round((stop - strt) / step)) + 1
            # Count data rows strictly inside the ~A section.
            data_count = 0
            in_data = False
            for ln in text.splitlines():
                stripped = ln.strip()
                if stripped.startswith("~"):
                    in_data = stripped[1:2].upper() == "A"
                    continue
                if in_data and stripped and not stripped.startswith("#"):
                    data_count += 1
            if data_count != expected_rows:
                findings.append(_finding(
                    "LAS_DATA_ROWS_MISMATCH",
                    f"declared rows {expected_rows}, found {data_count} — "
                    f"file truncated or tampered"))
    except (KeyError, ValueError):
        pass
    _check_crs_las_units(declared_units, strt_f, stop_f, findings)
    if not curves:
        findings.append(_finding("LAS_NO_CURVES", "no curve definitions in ~C"))
    else:
        findings.append(_finding("LAS_OK", f"{len(curves)} curve definitions parsed"))


# Coordinate nesting depth per geometry type, where depth 1 == a [lon, lat]
# position. (RFC 7946: Polygon wraps rings which wrap positions -> depth 3.)
_GEOM_TYPES = {"Point": 1, "MultiPoint": 2, "LineString": 2, "MultiLineString": 3,
               "Polygon": 3, "MultiPolygon": 4}


def _check_coord_depth(coords, depth: int) -> bool:
    if depth == 1:
        return (isinstance(coords, (list, tuple)) and len(coords) >= 2
                and all(isinstance(c, (int, float)) for c in coords))
    if not isinstance(coords, (list, tuple)) or not coords:
        return False
    return all(_check_coord_depth(c, depth - 1) for c in coords)


def _check_geojson(path: Path, findings: List[dict],
                   declared_crs: Optional[str] = None) -> None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(_finding("GEOJSON_PARSE_ERROR", f"invalid JSON: {exc}"))
        return
    _check_crs_geojson(declared_crs, findings)
    ftype = doc.get("type")
    features = []
    if ftype == "FeatureCollection":
        features = doc.get("features", [])
    elif ftype == "Feature":
        features = [doc]
    elif ftype in _GEOM_TYPES:
        features = [{"geometry": doc}]
    if not features:
        findings.append(_finding("GEOJSON_NO_FEATURES", "no features found"))
        return
    for i, feat in enumerate(features):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        if gtype not in _GEOM_TYPES:
            findings.append(_finding("GEOJSON_BAD_GEOMETRY_TYPE",
                                     f"feature {i}: bad geometry type {gtype!r}"))
            continue
        if not _check_coord_depth(geom.get("coordinates"), _GEOM_TYPES[gtype]):
            findings.append(_finding("GEOJSON_BAD_COORDS", f"feature {i}: malformed coordinates"))
        for lon, lat in _flatten_points(geom.get("coordinates")):
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                findings.append(_finding(
                    "GEOJSON_BAD_COORDS",
                    f"feature {i}: point ({lon}, {lat}) outside WGS84 range"))
                break
    if "crs" not in doc and declared_crs is None:
        findings.append(_finding(
            "GEOJSON_NO_CRS", "no crs member: RFC 7946 assumes WGS84 — record the assumption"))
    findings.append(_finding("GEOJSON_OK", f"{len(features)} feature(s) structurally checked"))


def _flatten_points(coords):
    """Yield (lon, lat) pairs from any GeoJSON coordinates nesting."""
    if not isinstance(coords, (list, tuple)) or not coords:
        return
    if all(isinstance(c, (int, float)) for c in coords[:2]) and len(coords) >= 2:
        yield coords[0], coords[1]
        return
    for child in coords:
        yield from _flatten_points(child)


def _check_csv(path: Path, findings: List[dict], declared_crs: Optional[str] = None,
               declared_units: Optional[str] = None) -> None:
    if not _prescan_text(path, "CSV_CONTROL_CHARS", "CSV_LINE_TOO_LONG", findings):
        return
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        findings.append(_finding("CSV_EMPTY", "file has no rows"))
        return
    header = [h.strip().lstrip("\ufeff") for h in rows[0]]
    if not header or all(not h for h in header):
        findings.append(_finding("CSV_NO_HEADER", "empty header row"))
        return
    lower = [h.lower() for h in header]
    lat_names = ("lat", "latitude", "خط العرض")
    lon_names = ("lon", "lng", "long", "longitude", "خط الطول")
    lat_i = next((i for i, h in enumerate(lower) if h in lat_names), None)
    lon_i = next((i for i, h in enumerate(lower) if h in lon_names), None)
    numeric_cols: Dict[int, int] = {}
    missing_by_col: Dict[int, int] = {i: 0 for i in range(len(header))}
    data_rows = rows[1:]
    if not data_rows:
        findings.append(_finding("CSV_NO_HEADER", "header present but no data rows"))
        return
    seen_rows = set()
    duplicates = 0
    # v0.5.0: identifier integrity — same entity id with contradictory data
    # is corruption (double entry / merge error), not a note.
    id_names = ("id", "well", "well_name", "well_id", "station", "site", "name")
    id_i = next((i for i, h in enumerate(lower) if h in id_names), None)
    id_seen: Dict[str, tuple] = {}
    id_conflicts = 0
    lat_vals: List[float] = []
    lon_vals: List[float] = []
    en_vals: List[float] = []
    en_names = ("easting", "northing", "x", "y", "utm_e", "utm_n")
    en_i = [i for i, h in enumerate(lower) if h in en_names]
    for r_i, row in enumerate(data_rows):
        if len(row) != len(header):
            findings.append(_finding("CSV_NON_NUMERIC",
                                     f"row {r_i + 2}: width {len(row)} != {len(header)}"))
            continue
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        if len(row) > len(header):
            row = row[:len(header)]
        key = tuple(row)
        if key in seen_rows:
            duplicates += 1
        seen_rows.add(key)
        if id_i is not None:
            entity_id = row[id_i].strip().lower()
            if entity_id:
                rest = tuple(c.strip() for i, c in enumerate(row) if i != id_i)
                if entity_id in id_seen and id_seen[entity_id] != rest:
                    id_conflicts += 1
                id_seen.setdefault(entity_id, rest)
        for i, cell in enumerate(row):
            cell = cell.strip()
            if cell.lower() in _NULL_SENTINELS:
                missing_by_col[i] += 1
                continue
            try:
                float(cell)
                numeric_cols[i] = numeric_cols.get(i, 0) + 1
            except ValueError:
                pass
        if lat_i is not None and lon_i is not None:
            try:
                lat = float(row[lat_i])
                lon = float(row[lon_i])
                lat_vals.append(lat)
                lon_vals.append(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    findings.append(_finding("CSV_LATLON_RANGE",
                                             f"row {r_i + 2}: lat/lon out of range"))
            except (ValueError, IndexError):
                pass
        for j in en_i:
            try:
                en_vals.append(float(row[j]))
            except (ValueError, IndexError):
                pass
    total_missing = sum(missing_by_col.values())
    if total_missing:
        findings.append(_finding("CSV_MISSING_VALUES",
                                 f"{total_missing} missing cells: {missing_by_col}"))
    if duplicates:
        findings.append(_finding("CSV_DUP_ROWS", f"{duplicates} duplicate row(s)"))
    if id_conflicts:
        findings.append(_finding("CSV_ID_CONFLICT",
                                 f"{id_conflicts} conflicting row(s) share an identifier "
                                 f"with different data"))
    _check_crs_csv(declared_crs, declared_units, lat_vals, lon_vals, en_vals, findings)
    findings.append(_finding("CSV_OK",
                             f"{len(header)} columns, {len(data_rows)} rows, "
                             f"numeric cols: {sorted(numeric_cols)}"))


# --- TIFF structure validator (byte-level, zero dependencies) -------------
_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
                    11: 4, 12: 8}
_TIFF_REQUIRED_TAGS = {
    256: "ImageWidth", 257: "ImageLength", 258: "BitsPerSample",
    259: "Compression", 262: "Photometric", 273: "StripOffsets",
    277: "SamplesPerPixel", 278: "RowsPerStrip", 279: "StripByteCounts",
}
_TAG_PIXEL_SCALE = 33550   # GeoTIFF ModelPixelScaleTag
_TAG_TIEPOINT = 33922      # GeoTIFF ModelTiepointTag


def _parse_tiff_ifd(fh) -> Tuple[Optional[Dict[int, tuple]], Optional[str]]:
    """Parse header + first IFD. Returns ({tag: values}, None) or (None, code)."""
    header = fh.read(8)
    if len(header) < 8:
        return None, "TIFF_NO_IFD"
    order = header[:2]
    if order == b"II":
        e = "<"
    elif order == b"MM":
        e = ">"
    else:
        return None, "TIFF_MAGIC_UNKNOWN"
    magic = struct.unpack(e + "H", header[2:4])[0]
    if magic != 42:
        return None, "TIFF_MAGIC_UNKNOWN"
    ifd_off = struct.unpack(e + "I", header[4:8])[0]
    file_size = fh.seek(0, 2)
    if ifd_off < 8 or ifd_off >= file_size:
        return None, "TIFF_NO_IFD"
    fh.seek(ifd_off)
    raw = fh.read(2)
    if len(raw) < 2:
        return None, "TIFF_NO_IFD"
    n_entries = struct.unpack(e + "H", raw)[0]
    entries: Dict[int, tuple] = {}
    base = fh.tell()  # absolute position of the first 12-byte entry record
    for i in range(n_entries):
        fh.seek(base + 12 * i)  # absolute: out-of-line value reads move us around
        rec = fh.read(12)
        if len(rec) < 12:
            return None, "TIFF_NO_IFD"
        tag, typ, count = struct.unpack(e + "HHI", rec[:8])
        unit = _TIFF_TYPE_SIZES.get(typ)
        if unit is None:
            continue
        size = unit * count
        if size <= 4:
            data = rec[8:8 + size]
        else:
            off = struct.unpack(e + "I", rec[8:12])[0]
            if off + size > file_size:
                return None, "TIFF_TRUNCATED"
            fh.seek(off)
            data = fh.read(size)
            if len(data) < size:
                return None, "TIFF_TRUNCATED"
        if typ == 3:
            values = struct.unpack(e + "H" * count, data)
        elif typ == 4:
            values = struct.unpack(e + "I" * count, data)
        elif typ == 5:
            values = tuple(
                (num, den) for num, den in
                zip(struct.unpack(e + "I" * (2 * count), data)[::2],
                    struct.unpack(e + "I" * (2 * count), data)[1::2]))
        elif typ == 11:
            values = struct.unpack(e + "f" * count, data)
        elif typ == 12:
            # DOUBLE: what GDAL/tifffile actually write for ModelPixelScale
            # and ModelTiepoint — real-world GeoTIFFs carry type 12, and a
            # validator that cannot read them misses real georeferencing.
            values = struct.unpack(e + "d" * count, data)
        else:
            values = ()
        entries[tag] = values
    return entries, None


def _check_tiff(path: Path, findings: List[dict]) -> None:
    file_size = path.stat().st_size
    with path.open("rb") as fh:
        ifd, err = _parse_tiff_ifd(fh)
    if ifd is None:
        findings.append(_finding(err, "not a readable TIFF (magic/IFD parse failed)"))
        return

    def num(tag: int) -> Optional[int]:
        v = ifd.get(tag)
        return v[0] if v else None

    missing = [name for tag, name in _TIFF_REQUIRED_TAGS.items() if tag not in ifd]
    if missing:
        findings.append(_finding("TIFF_MISSING_TAG",
                                 f"missing required tags: {', '.join(missing)}"))
    w, h = num(256), num(257)
    bits, comp = num(258), num(259)
    spp = num(277)
    offsets = ifd.get(273, ())
    counts = ifd.get(279, ())
    if comp not in (None, 1):
        findings.append(_finding(
            "TIFF_UNSUPPORTED_COMPRESSION",
            f"compression {comp}: structural check only, raster decode deferred"))
    if comp == 1 and all(v is not None for v in (w, h, bits, spp)):
        expected = w * h * spp * bits // 8
        if sum(counts) != expected:
            findings.append(_finding(
                "TIFF_SIZE_MISMATCH",
                f"strip byte counts sum {sum(counts)} != {w}x{h}x{spp}x{bits}/8 = {expected}"))
    for off, cnt in zip(offsets, counts):
        if off + cnt > file_size:
            findings.append(_finding(
                "TIFF_TRUNCATED",
                f"strip at {off}+{cnt} exceeds file size {file_size}"))
            break
    if _TAG_PIXEL_SCALE in ifd and _TAG_TIEPOINT in ifd:
        tp = ifd[_TAG_TIEPOINT]

        def _num(v):
            if isinstance(v, tuple) and len(v) == 2:
                return v[0] / v[1] if v[1] else None
            if isinstance(v, (int, float)):
                return float(v)
            return None

        lon = _num(tp[3]) if len(tp) > 3 else None
        lat = _num(tp[4]) if len(tp) > 4 else None
        findings.append(_finding(
            "TIFF_GEO_TAGS",
            f"georeferenced raster (pixel scale + tiepoint), origin ~({lon}, {lat})"))
    findings.append(_finding("TIFF_OK",
                             f"{w}x{h}, {bits}-bit, compression {comp}, "
                             f"{len(ifd)} tags parsed"))


def validate_file(path: str, dtype: str = "auto",
                  declared_crs: Optional[str] = None,
                  declared_units: Optional[str] = None) -> dict:
    """Validate a data file. Returns a stable report:
    {status: pass|fail|needs_review, findings: [{code, severity, message}]}.

    v0.5.0: when declared_crs/declared_units are provided (from the dataset
    record), declared-vs-observed CRS/units consistency is checked and any
    contradiction fails validation with an explicit code.

    v0.6.0: beyond structural checks, real readers (lasio / tifffile /
    sqlite3) parse the actual content; reader findings merge into the same
    report and the report carries `reader` (machine-readable facts) and
    `evidence` ({read, verified, unverifiable}) — the layer must prove
    what it read, what it verified, and what it cannot confirm."""
    p = Path(path)
    if not p.exists():
        return {"status": "fail", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_FILE_MISSING", "file does not exist")]}
    if p.stat().st_size == 0:
        return {"status": "fail", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_EMPTY_FILE", "file is empty")]}
    if dtype == "auto":
        dtype = detect_type(p) or "tiff"
    from .readers import read_geopackage, read_geotiff, read_las

    reader_report = None
    findings: List[dict] = []
    if dtype == "las":
        _check_las(p, findings, declared_crs, declared_units)
        # A file refused at hygiene level is not parseable content — the
        # reader would only re-read garbage the gate already rejected.
        fatal = any(f["code"].startswith(("LAS_CONTROL", "LAS_LINE"))
                    for f in findings)
        if not fatal:
            reader_report = read_las(str(p))
    elif dtype == "geojson":
        _check_geojson(p, findings, declared_crs)
    elif dtype == "csv":
        _check_csv(p, findings, declared_crs, declared_units)
    elif dtype == "tiff":
        _check_tiff(p, findings)
        reader_report = read_geotiff(str(p), declared_crs=declared_crs)
    elif dtype == "gpkg":
        reader_report = read_geopackage(str(p), declared_crs=declared_crs)
    else:
        return {"status": "needs_review", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_UNKNOWN_TYPE", f"no validator for type {dtype!r}")]}
    if reader_report is not None:
        findings.extend(reader_report["findings"])
    status = "fail" if any(f["severity"] == "error" for f in findings) else "pass"
    report = {"status": status, "file": str(p), "dtype": dtype,
              "declared_crs": declared_crs, "declared_units": declared_units,
              "findings": findings}
    if reader_report is not None:
        report["reader"] = reader_report["data"]
        report["evidence"] = reader_report["evidence"]
    return report
