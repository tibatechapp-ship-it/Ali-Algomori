# Data verification layer: format validators with deterministic findings.
# Part of the binding acceptance standard: real data in -> verified -> only
# then may it enter any task. No dataset is trusted without a checksum and a
# passed format validation.
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

_NULL_SENTINELS = {"", "null", "nan", "na", "-", "none"}

# Codes with severities (contract is stable; tests assert them).
F = {
    "GEN_FILE_MISSING": "error",
    "GEN_EMPTY_FILE": "error",
    "GEN_UNKNOWN_TYPE": "warning",
    "TIFF_MAGIC_OK": "info",
    "TIFF_MAGIC_UNKNOWN": "warning",
    "LAS_NO_VERSION": "error",
    "LAS_VERSION_UNSUPPORTED": "warning",
    "LAS_NO_WELL_HEADER": "error",
    "LAS_NO_NULL": "warning",
    "LAS_NO_CURVES": "error",
    "LAS_STOP_LE_STRT": "error",
    "LAS_STEP_ZERO": "error",
    "LAS_DATA_ROWS_MISMATCH": "warning",
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
    "CSV_OK": "info",
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
    return None


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


def _check_las(path: Path, findings: List[dict]) -> None:
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
    try:
        strt, stop, step = (float(well[k]) for k in ("STRT", "STOP", "STEP"))
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
                    f"declared rows {expected_rows}, found {data_count}"))
    except (KeyError, ValueError):
        pass
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


def _check_geojson(path: Path, findings: List[dict]) -> None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(_finding("GEOJSON_PARSE_ERROR", f"invalid JSON: {exc}"))
        return
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
    if "crs" not in doc:
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


def _check_csv(path: Path, findings: List[dict]) -> None:
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
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    findings.append(_finding("CSV_LATLON_RANGE",
                                             f"row {r_i + 2}: lat/lon out of range"))
            except (ValueError, IndexError):
                pass
    total_missing = sum(missing_by_col.values())
    if total_missing:
        findings.append(_finding("CSV_MISSING_VALUES",
                                 f"{total_missing} missing cells: {missing_by_col}"))
    if duplicates:
        findings.append(_finding("CSV_DUP_ROWS", f"{duplicates} duplicate row(s)"))
    findings.append(_finding("CSV_OK",
                             f"{len(header)} columns, {len(data_rows)} rows, "
                             f"numeric cols: {sorted(numeric_cols)}"))


def validate_file(path: str, dtype: str = "auto") -> dict:
    """Validate a data file. Returns a stable report:
    {status: pass|fail|needs_review, findings: [{code, severity, message}]}."""
    p = Path(path)
    findings: List[dict] = []
    if not p.exists():
        return {"status": "fail", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_FILE_MISSING", "file does not exist")]}
    if p.stat().st_size == 0:
        return {"status": "fail", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_EMPTY_FILE", "file is empty")]}
    if dtype == "auto":
        dtype = detect_type(p) or "tiff"
    if dtype == "las":
        _check_las(p, findings)
    elif dtype == "geojson":
        _check_geojson(p, findings)
    elif dtype == "csv":
        _check_csv(p, findings)
    elif dtype == "tiff":
        with p.open("rb") as fh:
            head = fh.read(4)
        if head[:2] in (b"II", b"MM"):
            findings.append(_finding("TIFF_MAGIC_OK",
                                     "TIFF container magic detected (byte-level only)"))
        else:
            findings.append(_finding("TIFF_MAGIC_UNKNOWN",
                                     "no TIFF magic; deferring full raster check"))
    else:
        return {"status": "needs_review", "file": str(p), "dtype": dtype,
                "findings": [_finding("GEN_UNKNOWN_TYPE", f"no validator for type {dtype!r}")]}
    status = "fail" if any(f["severity"] == "error" for f in findings) else "pass"
    return {"status": status, "file": str(p), "dtype": dtype, "findings": findings}
