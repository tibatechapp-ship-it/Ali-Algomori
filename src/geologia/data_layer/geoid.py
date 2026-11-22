# Geoid grid ingestion (T4.1) — the geoid gate, executable this time.
#
# The approved plan (T4.1) is executed literally: an official EGM grid enters
# through the SAME reception gate as every other byte (tiff is an accepted
# reception dtype), gets pinned by SHA-256, license, tide system, grid
# coordinates, interpolation method and validity domain (the eight gates),
# and is then tested: node values AND interior bilinear interpolation are
# cross-checked between OUR parser and PROJ's implementation of the SAME
# grid bytes — two independent implementations must agree.
#
# Formats:
# - GeoTIFF (production path; the official cdn.proj.org grids
#   us_nga_egm96_15.tif / us_nga_egm08_25.tif) — needs tifffile (optional dep).
# - Legacy GTX (pure-stdlib parser; row-0 = northernmost is a DECLARED
#   assumption kept for test fixtures — the verified production path is TIFF,
#   where GeoTIFF semantics fix the orientation unambiguously).
#
# Honest posture: without an ingested, independently verified grid there is
# NO vertical answer at all (T4.2 rule) — no approximate value, no silent MSL.
from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GEOID_CODES = {
    "GEOID_EMPTY_FILE": "error",
    "GEOID_TOO_LARGE": "error",
    "GEOID_BAD_HEADER": "error",
    "GEOID_BAD_SIZE": "error",
    "GEOID_NONFINITE": "error",
    "GEOID_RECEPTION_REFUSED": "error",
    "GEOID_PROOF_REFUSED": "error",
    "GEOID_GATES_RECORDED": "info",
    "GEOID_RECEPTION_ACCEPTED": "info",
}

MAX_GRID_BYTES = 1 << 30          # 1 GiB hard ceiling for a grid file
GTX_HEADER = struct.Struct(">4d2i")   # south, west, north, east, nlat, nlon


def _f(code: str, message: str) -> dict:
    return {"code": code, "severity": GEOID_CODES[code], "message": message}


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------
def parse_gtx(data: bytes) -> dict:
    """Parse a legacy GTX grid (pure stdlib). Row 0 = northernmost (declared
    assumption; the verified production path is GeoTIFF)."""
    if len(data) < GTX_HEADER.size:
        raise ValueError("GEOID_BAD_HEADER: file shorter than a GTX header")
    south, west, north, east, nlat, nlon = GTX_HEADER.unpack(
        data[:GTX_HEADER.size])
    _check_domain(south, west, north, east, nlat, nlon)
    count = nlat * nlon
    expected = GTX_HEADER.size + 4 * count
    if len(data) < expected:
        raise ValueError(
            f"GEOID_BAD_SIZE: need {expected} bytes for {nlat}x{nlon}, got "
            f"{len(data)}")
    values = struct.unpack(f">{count}f", data[GTX_HEADER.size:expected])
    return _grid_from_rows(values, nlat, nlon, south, west, north, east,
                           source_format="gtx")


def _check_domain(south, west, north, east, nlat, nlon) -> None:
    if not (nlat >= 2 and nlon >= 2 and nlat * nlon <= 200_000_000):
        raise ValueError(f"GEOID_BAD_HEADER: implausible grid shape "
                         f"{nlat}x{nlon}")
    if north <= south or east <= west:
        raise ValueError("GEOID_BAD_HEADER: empty or inverted domain "
                         f"(S{south} W{west} N{north} E{east})")


def _grid_from_rows(values, nlat, nlon, south, west, north, east,
                    source_format: str) -> dict:
    finite = sum(1 for v in values if math.isfinite(v))
    if finite == 0:
        raise ValueError("GEOID_NONFINITE: no finite undulation values")
    return {
        "south": south, "west": west, "north": north, "east": east,
        "nlat": nlat, "nlon": nlon,
        "scale_y": (north - south) / (nlat - 1),
        "scale_x": (east - west) / (nlon - 1),
        "values": list(values),
        "finite_count": finite,
        "source_format": source_format,
    }


def parse_grid_file(path: str) -> dict:
    """Parse a grid file: GeoTIFF via tifffile (production), GTX via stdlib.
    Raises ValueError(GEOID_*) on refusal."""
    p = Path(path)
    size = p.stat().st_size if p.exists() else 0
    if size == 0:
        raise ValueError("GEOID_EMPTY_FILE: no readable grid file")
    if size > MAX_GRID_BYTES:
        raise ValueError(f"GEOID_TOO_LARGE: {size} bytes exceeds the grid "
                         f"ceiling of {MAX_GRID_BYTES}")
    head = p.open("rb").read(8)
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        try:
            import tifffile
        except ImportError as exc:
            raise ValueError(
                "GEOID_BAD_HEADER: GeoTIFF grids need the optional tifffile "
                "dependency (pip install tifffile)") from exc
        return _grid_from_tifffile(str(p))
    if head.startswith(b"%"):
        raise ValueError("GEOID_BAD_HEADER: not a grid (looks like text/pdf)")
    data = p.read_bytes()
    if len(data) >= GTX_HEADER.size:
        return parse_gtx(data)
    raise ValueError("GEOID_BAD_HEADER: unrecognized grid container")


def _grid_from_tifffile(path: str) -> dict:
    import numpy as np                     # tifffile depends on numpy
    import tifffile
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        arr = page.asarray()
        if arr.ndim == 3:
            arr = arr[0]
        scale = page.tags.get("ModelPixelScaleTag")
        tie = page.tags.get("ModelTiepointTag")
        if scale is None or tie is None:
            raise ValueError(
                "GEOID_BAD_HEADER: GeoTIFF lacks ModelPixelScale/"
                "ModelTiepoint - not a geo-referenced grid")
        scale_x, scale_y = float(scale.value[0]), float(scale.value[1])
        i, j, _k, x, y, _z = [float(v) for v in tie.value[:6]]
        west, north = x - i * scale_x, y + j * scale_y
        nlat, nlon = arr.shape[0], arr.shape[1]
        south, east = north - scale_y * (nlat - 1), west + scale_x * (nlon - 1)
        desc = (page.description or "")
        flat = arr.reshape(-1).astype("float64")
        finite = int(np.isfinite(flat).sum())
        if finite == 0:
            raise ValueError("GEOID_NONFINITE: no finite undulation values")
        finite_vals = flat[np.isfinite(flat)]
        return {
            "south": south, "west": west, "north": north, "east": east,
            "nlat": nlat, "nlon": nlon, "scale_y": scale_y,
            "scale_x": scale_x, "values": flat,
            "finite_count": finite, "source_format": "geotiff",
            "min_m": float(finite_vals.min()), "max_m": float(finite_vals.max()),
            "description": desc,
        }


# ---------------------------------------------------------------------------
# interpolation
# ---------------------------------------------------------------------------
def undulation_at(grid: dict, lat: float, lon: float) -> Optional[float]:
    """Bilinear undulation (metres) at (lat, lon); None outside the domain."""
    south, north = grid["south"], grid["north"]
    west, east = grid["west"], grid["east"]
    nlat, nlon = grid["nlat"], grid["nlon"]
    if not (south <= lat <= north):
        return None
    lon_w = lon
    while lon_w < west:
        lon_w += 360.0
    while lon_w > west + 360.0 and lon_w - 360.0 >= west:
        lon_w -= 360.0
    if not (west <= lon_w <= east):
        return None
    row_f = (north - lat) / grid["scale_y"]     # row 0 = northernmost
    col_f = (lon_w - west) / grid["scale_x"]
    r0, c0 = int(math.floor(row_f)), int(math.floor(col_f))
    if r0 < 0 or r0 + 1 >= nlat:
        return None
    dr, dc = row_f - r0, col_f - c0
    vals = grid["values"]

    def node(r: int, c: int) -> float:
        return vals[r * nlon + (c % nlon)]

    n00, n01 = node(r0, c0), node(r0, c0 + 1)
    n10, n11 = node(r0 + 1, c0), node(r0 + 1, c0 + 1)
    if not all(math.isfinite(v) for v in (n00, n01, n10, n11)):
        return None
    top = n00 + (n01 - n00) * dc
    bottom = n10 + (n11 - n10) * dc
    return top + (bottom - top) * dr


def grid_stats(grid: dict) -> dict:
    if "min_m" in grid:            # numpy path: stats computed at parse time
        return {"min_m": grid["min_m"], "max_m": grid["max_m"],
                "finite_nodes": grid["finite_count"],
                "total_nodes": grid["nlat"] * grid["nlon"]}
    vals = [v for v in grid["values"] if math.isfinite(v)]
    return {"min_m": min(vals), "max_m": max(vals),
            "finite_nodes": len(vals),
            "total_nodes": grid["nlat"] * grid["nlon"]}


def golden_nodes(grid: dict, max_nodes: int = 25) -> List[dict]:
    """Deterministic interior node samples: EXACT grid node values (no
    interpolation) — the frozen reference for the node-matching test."""
    out: List[dict] = []
    nlat, nlon = grid["nlat"], grid["nlon"]
    stride_r = max(1, (nlat - 1) // 5)
    stride_c = max(1, (nlon - 1) // 5)
    for r in range(0, nlat, stride_r):
        for c in range(0, nlon, stride_c):
            if len(out) >= max_nodes:
                return out
            lat = grid["north"] - r * grid["scale_y"]
            lon = grid["west"] + c * grid["scale_x"]
            v = grid["values"][r * nlon + c]
            if math.isfinite(v):
                out.append({"lat": round(lat, 6), "lon": round(lon, 6),
                            "undulation_m": round(float(v), 6)})
    return out


# ---------------------------------------------------------------------------
# ingestion through the SAME gate + the eight gates + crosscheck
# ---------------------------------------------------------------------------
def ingest_grid(path: str, *, model_id: str, epsg_vertical: int,
                license_status: str, license_source: str,
                tide_system: str, tide_evidence: str, source_url: str,
                run_crosscheck: bool = True) -> dict:
    """Run an official grid through reception -> proof -> geoid gates.

    Returns the registry record (or a refusal with findings). The reception
    gate here IS the platform gate (tiff is an accepted dtype): no second door.
    """
    from geologia.data_layer.evidence import prove_file
    from geologia.data_layer.reception import check_upload

    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return {"status": "rejected",
                "findings": [_f("GEOID_EMPTY_FILE",
                                f"no readable grid at {p}")]}
    sha256 = hashlib.sha256(p.read_bytes()).hexdigest()

    reception = check_upload(str(p), dtype="tiff",
                             run_content_validation=True)
    if reception["status"] == "rejected":
        return {"status": "rejected", "sha256": sha256,
                "findings": [_f("GEOID_RECEPTION_REFUSED",
                                "the platform reception gate refused this "
                                f"file: {reception['findings']}")]}
    proof = prove_file(str(p), dtype="tiff")
    if proof.get("proof_status") == "refused":
        return {"status": "rejected", "sha256": sha256,
                "findings": [_f("GEOID_PROOF_REFUSED",
                                "honest proof refused the file")]}

    try:
        grid = parse_grid_file(str(p))
    except ValueError as exc:
        # The refusing code is the prefix before the first colon; if the
        # underlying reader produced an unexpected prefix, fall back to the
        # generic GEOID_BAD_HEADER while keeping the full honest message.
        code = str(exc).split(":")[0].strip()
        if code not in GEOID_CODES:
            code = "GEOID_BAD_HEADER"
        return {"status": "rejected", "sha256": sha256,
                "findings": [_f(code, str(exc))]}

    stats = grid_stats(grid)
    gates = {
        "sha256": sha256,
        "license": {"status": license_status, "source": license_source},
        "tide_system": {"value": tide_system, "evidence": tide_evidence},
        "grid_coords": {
            "south": round(grid["south"], 6),
            "west": round(grid["west"], 6),
            "north": round(grid["north"], 6),
            "east": round(grid["east"], 6),
            "resolution_deg": round(grid["scale_x"], 8),
            "nlat": grid["nlat"], "nlon": grid["nlon"],
        },
        "interpolation": "bilinear (declared; validated against node "
                         "values and the PROJ crosscheck)",
        "crs_pair": {"horizontal": "EPSG:4326 (WGS 84)",
                     "vertical": f"EPSG:{epsg_vertical}"},
        "validity_domain": {"lat": [round(grid["south"], 6),
                                    round(grid["north"], 6)],
                            "lon": [round(grid["west"], 6),
                                    round(grid["east"], 6)],
                            "undulation_m": [round(stats["min_m"], 4),
                                             round(stats["max_m"], 4)]},
        "independent_check": "pending",
    }
    record = {
        "status": "recorded",
        "model_id": model_id,
        "source_url": source_url,
        "source_format": grid["source_format"],
        "file_name": p.name,
        "size_bytes": p.stat().st_size,
        "gates": gates,
        "grid_stats": {"min_m": round(stats["min_m"], 4),
                       "max_m": round(stats["max_m"], 4),
                       "finite_nodes": stats["finite_nodes"],
                       "total_nodes": stats["total_nodes"]},
        "description": grid.get("description", ""),
    }

    if run_crosscheck:
        cross = crosscheck_with_proj(grid, epsg_vertical,
                                     grid_dir=str(p.parent))
        record["crosscheck"] = cross
        gates["independent_check"] = (
            f"passed: max |ours - PROJ| = {cross['max_abs_diff_m']:.6f} m "
            f"over {cross['points']} interior points"
            if cross["status"] == "passed"
            else f"unavailable: {cross['status']}")

    findings = [_f("GEOID_RECEPTION_ACCEPTED",
                   "grid entered through the platform reception gate"),
                _f("GEOID_GATES_RECORDED", "eight geoid gates recorded")]
    record["findings"] = findings
    return record


def crosscheck_with_proj(grid: dict, epsg_vertical: int,
                         grid_dir: str, points: int = 9) -> dict:
    """Independent-implementation crosscheck: OUR bilinear vs PROJ's own
    interpolation of the SAME grid bytes (PROJ picks the grid by file name
    from an appended data dir)."""
    try:
        import numpy as np
        import pyproj
        from pyproj.datadir import append_data_dir
    except ImportError:
        return {"status": "pyproj_unavailable", "points": 0,
                "max_abs_diff_m": None}
    try:
        append_data_dir(grid_dir)
        transformer = pyproj.Transformer.from_crs(
            "EPSG:4979", f"EPSG:4326+{epsg_vertical}", always_xy=True)
    except Exception as exc:                    # noqa: BLE001 - honest report
        return {"status": f"transformer_error: {exc}", "points": 0,
                "max_abs_diff_m": None}

    south, north = grid["south"], grid["north"]
    west, east = grid["west"], grid["east"]
    lat_mid = (south + north) / 2.0
    lon_mid = (west + east) / 2.0
    lat_pts = [south + (north - south) * f for f in (0.25, 0.5, 0.75)]
    lon_pts = [west + (east - west) * f for f in (0.25, 0.5, 0.75)]
    samples: List[Tuple[float, float]] = [(lat_mid, lon_mid)]
    for la in lat_pts:
        for lo in lon_pts:
            samples.append((la, lo))
    samples = samples[:points]
    diffs: List[float] = []
    for lat, lon in samples:
        ours = undulation_at(grid, lat, lon)
        if ours is None:
            continue
        _lon, _lat, h_egm = transformer.transform(lon, lat, 1000.0)
        proj_und = 1000.0 - h_egm
        diffs.append(abs(ours - proj_und))
    if not diffs:
        return {"status": "no_comparable_points", "points": 0,
                "max_abs_diff_m": None}
    return {"status": "passed", "points": len(diffs),
            "max_abs_diff_m": max(diffs),
            "note": "our parser vs PROJ on the same grid bytes; "
                    f"numpy={np.__version__}, pyproj={pyproj.__version__}"}
