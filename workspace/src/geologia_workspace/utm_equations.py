"""Independent UTM (Transverse Mercator) equation checks, pyproj-free.

Published source: USGS Professional Paper 1395 (Snyder, 1987),
"Map Projections: A Working Manual", transverse Mercator equations 8-9..8-15
(forward) and 8-25..8-29 (inverse), with the standard even-power e^2
meridian-arc series (binomial expansion of the meridian radius of curvature,
signs verified numerically against the exact integral), applied to the UTM
conventions: WGS 84 ellipsoid, k0 = 0.9996, false easting 500 000 m, false
northing 0 m (north zones) / 10 000 000 m (south zones). Golden values are
frozen in data/utm_equation_points.json and cross-checked against the
installed pyproj engine when it is available.

The equation proof is pure math and does not require pyproj. This module
does not validate geological meaning, CRS suitability, datum shifts
(WGS 84 vs other datums), vertical coordinates, or the accuracy of input
coordinates. The 6th-order series truncation limits in-zone accuracy to
roughly millimetres-to-centimetres; see the frozen tolerance values.

Truth classification for every output of this module: verified_structural
at most — a math check against published equations, never geological truth.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

A_WGS84 = 6378137.0
F_WGS84 = 1.0 / 298.257223563
K0_UTM = 0.9996
FE_UTM = 500000.0
FN_NORTH = 0.0
FN_SOUTH = 10000000.0
E2_WGS84 = F_WGS84 * (2.0 - F_WGS84)
EP2_WGS84 = E2_WGS84 / (1.0 - E2_WGS84)
LAT_LIMIT_NORTH_DEG = 84.0
LAT_LIMIT_SOUTH_DEG = -80.0
EQUATION_SOURCE = "snyder_utm_equations"
_REFERENCE_PATH = Path(__file__).resolve().parent / "data" / "utm_equation_points.json"
MERIDIAN_ARC_COEFFS = (
    1.0 - E2_WGS84 / 4.0 - 3.0 * E2_WGS84**2 / 64.0 - 5.0 * E2_WGS84**3 / 256.0,
    3.0 * E2_WGS84 / 8.0 + 3.0 * E2_WGS84**2 / 32.0 + 45.0 * E2_WGS84**3 / 1024.0,
    15.0 * E2_WGS84**2 / 256.0 + 45.0 * E2_WGS84**3 / 1024.0,
    35.0 * E2_WGS84**3 / 3072.0,
)


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def central_meridian(zone: int) -> float:
    """Central meridian longitude in degrees for a UTM zone (1..60)."""
    if isinstance(zone, bool) or not isinstance(zone, int) or not 1 <= zone <= 60:
        raise ValueError("zone must be an integer between 1 and 60")
    return 6.0 * zone - 183.0


def detect_utm_zone(lon_deg: float) -> int:
    """UTM zone number from longitude alone (hemisphere is a latitude matter)."""
    lon = _finite_number(lon_deg, "longitude")
    if not -180.0 <= lon < 180.0:
        raise ValueError("longitude outside the UTM zone range [-180, 180)")
    return int(math.floor((lon + 180.0) / 6.0)) + 1


def _validate_zone_and_latitude(zone: int, lat_deg: float) -> float:
    if isinstance(zone, bool) or not isinstance(zone, int) or not 1 <= zone <= 60:
        raise ValueError("zone must be an integer between 1 and 60")
    lat = _finite_number(lat_deg, "latitude")
    if not LAT_LIMIT_SOUTH_DEG <= lat <= LAT_LIMIT_NORTH_DEG:
        raise ValueError("latitude outside the UTM domain [-80, 84] degrees")
    return lat


def _meridian_arc(phi: float) -> float:
    c0, c2, c4, c6 = MERIDIAN_ARC_COEFFS
    return A_WGS84 * (
        c0 * phi
        - c2 * math.sin(2.0 * phi)
        + c4 * math.sin(4.0 * phi)
        - c6 * math.sin(6.0 * phi)
    )


def utm_forward(zone: int, lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """Forward UTM (Snyder eqs 8-9..8-15) for a WGS 84 longitude/latitude.

    Hemisphere is inferred from the latitude sign; the equator maps to the
    north-zone false northing. Returns (easting_m, northing_m).
    """
    lat = _validate_zone_and_latitude(zone, lat_deg)
    lon = _finite_number(lon_deg, "longitude")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("longitude outside the [-180, 180] degree range")
    lam = math.radians(lon - central_meridian(zone))
    phi = math.radians(lat)
    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)
    n_radius = A_WGS84 / math.sqrt(1.0 - E2_WGS84 * sin_phi * sin_phi)
    t = tan_phi * tan_phi
    c = EP2_WGS84 * cos_phi * cos_phi
    a = lam * cos_phi
    x = FE_UTM + K0_UTM * n_radius * (
        a
        + (1.0 - t + c) * a**3 / 6.0
        + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * EP2_WGS84) * a**5 / 120.0
    )
    if lat < 0.0:
        fn = FN_SOUTH
    else:
        fn = FN_NORTH
    y = fn + K0_UTM * (
        _meridian_arc(phi)
        + n_radius
        * tan_phi
        * (
            a * a / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * a**4 / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c - 330.0 * EP2_WGS84)
            * a**6
            / 720.0
        )
    )
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("UTM forward produced non-finite coordinates")
    return x, y


def utm_inverse(
    zone: int, hemisphere: str, easting: float, northing: float
) -> tuple[float, float]:
    """Inverse UTM (Snyder eqs 8-25..8-29) for one WGS 84 UTM zone.

    ``hemisphere`` must be "north" or "south" because a northing value alone
    cannot disambiguate the two false-northing conventions. Returns
    (longitude_deg, latitude_deg).
    """
    if hemisphere not in {"north", "south"}:
        raise ValueError('hemisphere must be "north" or "south"')
    if isinstance(zone, bool) or not isinstance(zone, int) or not 1 <= zone <= 60:
        raise ValueError("zone must be an integer between 1 and 60")
    x = _finite_number(easting, "easting")
    y = _finite_number(northing, "northing")
    fn = FN_NORTH if hemisphere == "north" else FN_SOUTH
    m = (y - fn) / K0_UTM
    mu = m / (A_WGS84 * MERIDIAN_ARC_COEFFS[0])
    e1 = (1.0 - math.sqrt(1.0 - E2_WGS84)) / (1.0 + math.sqrt(1.0 - E2_WGS84))
    phi1 = mu + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu) + (
        21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0
    ) * math.sin(4.0 * mu) + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu) + (
        1097.0 * e1**4 / 512.0
    ) * math.sin(8.0 * mu)
    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    tan_phi1 = math.tan(phi1)
    c1 = EP2_WGS84 * cos_phi1 * cos_phi1
    t1 = tan_phi1 * tan_phi1
    n1 = A_WGS84 / math.sqrt(1.0 - E2_WGS84 * sin_phi1 * sin_phi1)
    r1 = A_WGS84 * (1.0 - E2_WGS84) / (1.0 - E2_WGS84 * sin_phi1 * sin_phi1) ** 1.5
    d = (x - FE_UTM) / (n1 * K0_UTM)
    phi = phi1 - (n1 * tan_phi1 / r1) * (
        d * d / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 * c1 - 9.0 * EP2_WGS84)
        * d**4
        / 24.0
        + (
            61.0 + 90.0 * t1 + 45.0 * t1 * t1 + 46.0 * c1 - 252.0 * t1 * c1 - 3.0 * c1 * c1
        )
        * d**6
        / 720.0
    )
    lam = (
        d
        - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (
            5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 * c1 + 8.0 * EP2_WGS84 + 24.0 * t1 * t1
        )
        * d**5
        / 120.0
    ) / cos_phi1
    lon_deg_value = math.degrees(lam) + central_meridian(zone)
    lat_deg_value = math.degrees(phi)
    if not math.isfinite(lon_deg_value) or not math.isfinite(lat_deg_value):
        raise ValueError("UTM inverse produced non-finite coordinates")
    return lon_deg_value, lat_deg_value


def load_equation_points() -> dict[str, Any]:
    """Load the pinned UTM equation-derived control points packaged with GEOLOGIA."""
    return json.loads(_REFERENCE_PATH.read_text(encoding="utf-8"))


def reference_fingerprint() -> str:
    """SHA-256 of the packaged UTM control-point file for provenance records."""
    return hashlib.sha256(_REFERENCE_PATH.read_bytes()).hexdigest()


def verify_utm_equation_points(
    reference: dict[str, Any] | None = None,
    *,
    crosscheck_engine: bool = True,
) -> dict[str, Any]:
    """Re-derive frozen UTM values; optionally compare the installed pyproj engine.

    Missing pyproj is reported as unverifiable for the engine check while the
    pure-equation proof still runs. Equation/reference mismatches are errors.
    """
    ref = reference if reference is not None else load_equation_points()
    targets = [
        point
        for point in ref.get("transformations", [])
        if point.get("source") == EQUATION_SOURCE
    ]
    findings: list[dict[str, str]] = []
    checked = 0
    engine_checked = 0
    engine_name: str | None = None
    engine_available = False

    if crosscheck_engine:
        try:
            import pyproj

            engine_name = f"pyproj {pyproj.__version__}"
            engine_available = True
        except ImportError:
            findings.append({
                "code": "UTM_ENGINE_ABSENT",
                "severity": "warning",
                "message": "pyproj absent; engine cross-check is unverifiable, not passed",
            })

    for point in targets:
        name = str(point.get("name", "unnamed"))
        try:
            zone = point["zone"]
            hemisphere = point["hemisphere"]
            if point.get("kind") == "roundtrip":
                actual_x, actual_y = utm_inverse(
                    zone, hemisphere, point["x"], point["y"]
                )
            else:
                actual_x, actual_y = utm_forward(zone, point["x"], point["y"])
            expected_x = _finite_number(point["expected_x"], "expected_x")
            expected_y = _finite_number(point["expected_y"], "expected_y")
            tolerance = _finite_number(point["tol"], "tolerance")
            if tolerance < 0:
                raise ValueError("tolerance must be non-negative")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            findings.append({
                "code": "UTM_MATH_MISMATCH",
                "severity": "error",
                "message": f"{name}: equation or reference validation failed: {exc}",
            })
            continue

        error = max(abs(actual_x - expected_x), abs(actual_y - expected_y))
        if error > tolerance:
            findings.append({
                "code": "UTM_MATH_MISMATCH",
                "severity": "error",
                "message": (
                    f"{name}: frozen value differs from published UTM equations "
                    f"by {error:.3e}{point.get('tol_unit', '')} "
                    f"(tolerance {tolerance}); reference not trusted"
                ),
            })
            continue

        checked += 1
        findings.append({
            "code": "UTM_MATH_OK",
            "severity": "info",
            "message": (
                f"{name}: frozen value reproduced from published UTM equations "
                f"(max error {error:.3e}{point.get('tol_unit', '')})"
            ),
        })

        if engine_available:
            try:
                from pyproj import Transformer

                transformer = Transformer.from_crs(
                    point["from_crs"], point["to_crs"], always_xy=True
                )
                engine_x, engine_y = transformer.transform(
                    point["x"], point["y"], errcheck=True
                )
                engine_error = max(abs(engine_x - actual_x), abs(engine_y - actual_y))
            except Exception as exc:
                findings.append({
                    "code": "UTM_CROSS_MISMATCH",
                    "severity": "error",
                    "message": f"{name}: pyproj cross-check failed: {type(exc).__name__}: {exc}",
                })
                continue
            if not math.isfinite(engine_error) or engine_error > tolerance:
                findings.append({
                    "code": "UTM_CROSS_MISMATCH",
                    "severity": "error",
                    "message": (
                        f"{name}: {engine_name} disagrees with equations by "
                        f"{engine_error:.3e}{point.get('tol_unit', '')}"
                    ),
                })
            else:
                engine_checked += 1
                findings.append({
                    "code": "UTM_CROSS_OK",
                    "severity": "info",
                    "message": f"{name}: {engine_name} agrees with equation result",
                })

    equation_ok = bool(targets) and checked == len(targets) and not any(
        item["severity"] == "error" and item["code"] == "UTM_MATH_MISMATCH"
        for item in findings
    )
    cross_errors = any(
        item["severity"] == "error" and item["code"] == "UTM_CROSS_MISMATCH"
        for item in findings
    )
    if not targets:
        findings.append({
            "code": "UTM_MATH_NO_POINTS",
            "severity": "warning",
            "message": "No control points tagged for Snyder UTM equations were found",
        })

    engine_status = (
        "not_requested"
        if not crosscheck_engine
        else "unverifiable"
        if not engine_available
        else "failed"
        if cross_errors
        else "passed"
        if engine_checked == len(targets) and bool(targets)
        else "incomplete"
    )
    return {
        "ok": equation_ok and not cross_errors,
        "method": "UTM (Transverse Mercator) via USGS Snyder 1987 equations",
        "equation_points_checked": checked,
        "equation_points_total": len(targets),
        "engine_crosscheck_status": engine_status,
        "engine": engine_name,
        "reference_sha256": reference_fingerprint() if reference is None else None,
        "findings": findings,
        "scope": (
            "Equation/control-point verification only; not CRS selection, datum "
            "transformation, vertical conversion, coordinate accuracy, or geology."
        ),
    }
