"""Independent mathematical verification for EPSG:3857 — no pyproj.

Binding problem this module solves (owner's review, v0.7.0): the frozen
control points in `data/reference/transformations.json` were compared
against pyproj, but comparing pyproj with pyproj-frozen values proves
consistency of the engine, NOT independence of the reference. For EPSG:3857
the published equations are simple enough to implement from the standard
itself, so the reference values can be re-derived from FIRST PRINCIPLES
without any transformation library — including on the pure-Python Termux
track where pyproj is absent.

EPSG:3857 "WGS 84 / Pseudo-Mercator" is defined (EPSG method 1024,
Popular Visualisation Pseudo Mercator; EPSG Guidance Note 7-2) as a
SPHERICAL Mercator applied to WGS84 lon/lat degrees, with the sphere
radius R equal to the WGS84 semi-major axis:

    X = R * lambda              (lambda in radians from Greenwich)
    Y = R * ln[ tan(pi/4 + phi/2) ]   (equivalently R * atanh(sin(phi)))
    R = 6378137 m

Inverse (for round-trip closure):

    lambda = X / R
    phi    = 2*atan(exp(Y/R)) - pi/2

Equation-derived invariants (computed, never hard-coded as claims):
    X(+90 deg lon) = R*pi/2 = 10018754.171394622 m
    |Y| at the CRS latitude limit phi_max = atan(sinh(pi)) =
    85.0511287798066 deg equals R*pi = 20037508.342789244 m
    (the familiar ±20037508.342789244 m world extent and ±85.06 deg tile
    bounds are CONSEQUENCES of the equations, not extra constants).

Honesty contract: this module never imports pyproj. Its verdicts carry
their own evidence codes (XFORM_MATH_*) and distinguish:
- frozen value vs published equations  (is the reference itself right?)
- installed engine vs published equations (is the engine right?)
A mismatch with the equations is a hard error in BOTH cases: the layer
must refuse to trust the reference or the engine — never recalibrate.
"""
from __future__ import annotations

import math
from typing import List, Optional

from .evidence import compile_evidence, ev_read, ev_unverifiable, ev_verified

# EPSG method 1024 sphere radius = WGS84 semi-major axis (metres).
R_3857 = 6378137.0

# Equation-derived latitude limit of the CRS domain (degrees).
LAT_LIMIT_DEG = math.degrees(math.atan(math.sinh(math.pi)))

# Source marker stored in transformations.json entries this module can
# re-derive from first principles.
EQUATION_SOURCE = "epsg_method_1024_equations"

CODES = {
    "XFORM_MATH_OK": "info",
    "XFORM_MATH_MISMATCH": "error",
    "XFORM_CROSS_OK": "info",
    "XFORM_CROSS_MISMATCH": "error",
    "XFORM_ENGINE_ABSENT": "warning",
}

__all__ = ["R_3857", "LAT_LIMIT_DEG", "EQUATION_SOURCE", "CODES",
           "pseudo_mercator", "inverse_pseudo_mercator",
           "verify_frozen_equation_points"]


def _mf(code: str, message: str) -> dict:
    return {"code": code, "severity": CODES[code], "message": message}


def pseudo_mercator(lon_deg: float, lat_deg: float) -> tuple:
    """EPSG method 1024 forward: WGS84 degrees -> EPSG:3857 metres.

    Raises ValueError outside the mathematical domain (|phi| >= 90 deg);
    the CRS working domain additionally ends at ±LAT_LIMIT_DEG.
    """
    if not (-90.0 < lat_deg < 90.0):
        raise ValueError(f"latitude {lat_deg} outside the Mercator domain")
    lam = math.radians(lon_deg)
    phi = math.radians(lat_deg)
    x = R_3857 * lam
    y = R_3857 * math.log(math.tan(math.pi / 4.0 + phi / 2.0))
    return x, y


def inverse_pseudo_mercator(x: float, y: float) -> tuple:
    """EPSG method 1024 inverse: EPSG:3857 metres -> WGS84 degrees."""
    lon = math.degrees(x / R_3857)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_3857)) - math.pi / 2.0)
    return lon, lat


def verify_frozen_equation_points(transformations: Optional[dict] = None) -> dict:
    """Re-derive frozen control points from the published equations.

    For every entry whose `source` is `epsg_method_1024_equations`:
    1. recompute the expected values with `pseudo_mercator` (pure math) and
       compare against the FROZEN values -> the reference is only accepted
       if the equations reproduce it (XFORM_MATH_OK / XFORM_MATH_MISMATCH);
    2. when pyproj is installed, also transform the entry with the engine
       and compare against the EQUATION result (XFORM_CROSS_OK /
       XFORM_CROSS_MISMATCH) — closing the independence triangle
       equations <-> frozen reference <-> engine;
    3. when pyproj is absent, record an honest `unverifiable` gap for the
       cross-check only — step 1 still runs, so the frozen reference is
       provable without any geo library.

    Returns the standard report shape {ok, findings, evidence, checked,
    total} — `total` counts ONLY equation-source entries.
    """
    ref = transformations if transformations is not None else \
        _load_default()
    findings: List[dict] = []
    read_l, ver_l, unv_l = [], [], []

    targets = [t for t in ref.get("transformations", [])
               if t.get("source") == EQUATION_SOURCE]
    read_l.append(ev_read(
        "XFORM_MATH_READ",
        f"{len(targets)} of {len(ref.get('transformations', []))} frozen "
        f"control points carry source={EQUATION_SOURCE} and can be "
        f"re-derived from published equations without a library"))
    if not targets:
        unv_l.append(ev_unverifiable(
            "XFORM_MATH_NOTHING_TO_DERIVE",
            "no equation-source control points found",
            reason="the reference file carries no entries this module can "
                   "re-derive; independence from the engine is not proven "
                   "for this corpus"))
        return {"ok": True, "findings": findings,
                "evidence": compile_evidence(read_l, ver_l, unv_l),
                "checked": 0, "total": 0}

    engine = None
    try:
        import pyproj
        engine = f"pyproj {pyproj.__version__}"
    except ImportError:
        unv_l.append(ev_unverifiable(
            "XFORM_ENGINE_ABSENT",
            "engine-vs-equation cross-check not performed",
            reason="pyproj is not installed; the frozen-vs-equation proof "
                   "still ran, but the installed engine was not "
                   "independently cross-checked"))

    checked = 0
    for t in targets:
        name = t["name"]
        try:
            if t.get("kind") == "roundtrip":
                lon, lat = inverse_pseudo_mercator(t["x"], t["y"])
                got_x, got_y = lon, lat
            else:
                got_x, got_y = pseudo_mercator(t["x"], t["y"])
        except Exception as exc:
            findings.append(_mf(
                "XFORM_MATH_MISMATCH",
                f"{name}: equation evaluation failed "
                f"({type(exc).__name__}: {exc})"))
            continue
        err = max(abs(got_x - t["expected_x"]), abs(got_y - t["expected_y"]))
        if err > t["tol"]:
            findings.append(_mf(
                "XFORM_MATH_MISMATCH",
                f"{name}: the frozen reference contradicts the published "
                f"EPSG:3857 equations by {err:.3e}{t['tol_unit']} "
                f"(tolerance {t['tol']}) — the reference itself is wrong, "
                f"not just the engine"))
            continue
        checked += 1
        ver_l.append(ev_verified(
            "XFORM_MATH_OK",
            f"{name}: frozen value reproduced by the published EPSG method "
            f"1024 equations (max err {err:.3e}{t['tol_unit']})",
            check="pure-math recomputation from EPSG method 1024 "
                  "(Guidance Note 7-2), no transformation library"))
        if engine is not None:
            try:
                from pyproj import Transformer
                tr = Transformer.from_crs(t["from_crs"], t["to_crs"],
                                          always_xy=True)
                ex, ey = tr.transform(t["x"], t["y"])
                cerr = max(abs(ex - got_x), abs(ey - got_y))
            except Exception as exc:
                findings.append(_mf(
                    "XFORM_CROSS_MISMATCH",
                    f"{name}: engine failed on an equation-reproducible "
                    f"point ({type(exc).__name__}: {exc})"))
                continue
            if cerr > t["tol"]:
                findings.append(_mf(
                    "XFORM_CROSS_MISMATCH",
                    f"{name}: installed engine {engine} disagrees with the "
                    f"published EPSG:3857 equations by "
                    f"{cerr:.3e}{t['tol_unit']} — do not trust the engine"))
            else:
                ver_l.append(ev_verified(
                    "XFORM_CROSS_OK",
                    f"{name}: engine {engine} agrees with the published "
                    f"equations (max diff {cerr:.3e}{t['tol_unit']})",
                    check=f"engine-vs-equation cross-check, {engine}"))

    ok = not any(f["severity"] == "error" for f in findings)
    if ok and checked == len(targets):
        findings.append(_mf(
            "XFORM_MATH_OK",
            f"all {checked} equation-source control points re-derived from "
            f"first principles"
            + (f" and cross-checked against {engine}" if engine else "")))
    return {"ok": ok, "findings": findings,
            "evidence": compile_evidence(read_l, ver_l, unv_l),
            "checked": checked, "total": len(targets)}


def _load_default() -> dict:
    """Load the packaged frozen reference (lazy import avoids a cycle)."""
    import json
    from .reference import REFERENCE_DATA_DIR
    return json.loads(
        (REFERENCE_DATA_DIR / "transformations.json").read_text(
            encoding="utf-8"))
