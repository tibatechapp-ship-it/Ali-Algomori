"""Independent mathematical tests for EPSG:3857 — the engine-independence proof.

Owner's review point (v0.7.0): existing transformation tests compare pyproj
output against frozen values, which proves engine consistency but NOT that
the frozen values are independent of the engine itself. These tests close
that gap for EPSG:3857 by implementing the published EPSG method 1024
equations directly (no pyproj) and proving three separable things:

1. the equation implementation satisfies its own mathematical invariants;
2. the FROZEN reference values are reproduced by the published equations
   — with pyproj present AND with pyproj blocked (pure-Python track);
3. the installed engine agrees with the published equations (cross-check,
   skipped honestly when pyproj is absent).

Tests 1 and 2 run with ZERO geo dependencies — the reference is provable
on Termux, which is exactly the independence the owner asked for.
"""
import math
import sys

import pytest

from geologia.data_layer.transforms_math import (CODES, LAT_LIMIT_DEG,
                                                 R_3857, inverse_pseudo_mercator,
                                                 pseudo_mercator,
                                                 verify_frozen_equation_points)


def _load_ref():
    from geologia.data_layer.reference import load_transformations
    return load_transformations()


# --- 1. mathematical invariants (no library, no reference file) -------------
def test_forward_x_is_exactly_R_times_longitude():
    for lon in (-180.0, -37.5, 0.0, 46.6753, 180.0):
        x, _ = pseudo_mercator(lon, 0.0)
        assert x == R_3857 * math.radians(lon)


def test_equator_y_is_zero_and_symmetry_is_odd():
    # math.pi/4 is not exactly pi/4, so tan(pi/4) < 1 by ~1 ulp and
    # y(0) = R*ln(tan(pi/4)) ~= -7.1e-10 m — one ulp scaled by Earth radius.
    # The honest claim: zero to machine precision, not bitwise zero.
    assert pseudo_mercator(15.0, 0.0)[1] == pytest.approx(0.0, abs=1e-8)
    # Odd symmetry holds mathematically (tan(pi/4 - phi/2) = 1/tan(pi/4 + phi/2)).
    # Two honest floating-point caveats, both documented rather than hidden:
    # 1. near the equator, ln(tan(pi/4 + phi/2)) cancels digits (the argument
    #    sits at 1 + 2*eps_phi), so relative symmetry error reaches ~1e-8
    #    for phi ~ 1e-6 deg — inherent to the published formula, not a bug;
    # 2. at |y| ~ 2e7 m, one ulp is ~7e-9 m.
    # rel=1e-7 covers both bounds; anything looser would hide real breakage.
    for lat in (1e-6, 10.0, 24.7136, 84.9):
        y_plus = pseudo_mercator(0.0, lat)[1]
        y_minus = pseudo_mercator(0.0, -lat)[1]
        assert y_minus == pytest.approx(-y_plus, rel=1e-7, abs=0)


def test_world_extent_is_equation_derived_not_hardcoded():
    """±20037508.342789244 m is a CONSEQUENCE of the equations (R*pi), not
    an extra constant typed from a website."""
    _, y_max = pseudo_mercator(0.0, LAT_LIMIT_DEG)
    assert y_max == pytest.approx(R_3857 * math.pi, rel=0, abs=1e-6)
    assert LAT_LIMIT_DEG == pytest.approx(
        math.degrees(math.atan(math.sinh(math.pi))), rel=0, abs=1e-12)
    assert 85.05 < LAT_LIMIT_DEG < 85.06


def test_inverse_is_exact_inverse_of_forward():
    for lon, lat in ((46.6753, 24.7136), (-9.0, 38.0), (110.0, -45.0)):
        x, y = pseudo_mercator(lon, lat)
        lo, la = inverse_pseudo_mercator(x, y)
        assert abs(lo - lon) < 1e-12
        assert abs(la - lat) < 1e-12


def test_latitude_outside_domain_is_refused():
    with pytest.raises(ValueError):
        pseudo_mercator(0.0, 90.0)
    with pytest.raises(ValueError):
        pseudo_mercator(0.0, -91.0)


# --- 2. frozen reference reproduced by the equations -------------------------
def test_frozen_3857_points_counted_and_reproven():
    ref = _load_ref()
    res = verify_frozen_equation_points(ref)
    assert res["total"] == 4, "four equation-source control points expected"
    assert res["checked"] == res["total"]
    assert res["ok"], res["findings"]
    assert any(f["code"] == "XFORM_MATH_OK" and "first principles"
               in f["message"] for f in res["findings"])
    # and the pyproj-only UTM entries are NOT silently re-counted
    names = {t["name"] for t in ref["transformations"]
             if t.get("source") == "epsg_method_1024_equations"}
    assert names == {"riyadh_wgs84_to_3857", "jeddah_wgs84_to_3857",
                     "dammam_wgs84_to_3857", "riyadh_3857_to_wgs84_roundtrip"}


def test_frozen_proof_runs_even_without_pyproj(monkeypatch):
    """THE independence test: block pyproj entirely and prove the frozen
    reference from the equations alone. The engine cross-check must be
    honestly reported as unverifiable — not claimed."""
    monkeypatch.setitem(sys.modules, "pyproj", None)
    res = verify_frozen_equation_points(_load_ref())
    assert res["ok"] is True
    assert res["checked"] == res["total"] == 4
    unv = {i["code"] for i in res["evidence"]["unverifiable"]}
    assert "XFORM_ENGINE_ABSENT" in unv
    ver = [i["code"] for i in res["evidence"]["verified"]]
    assert ver.count("XFORM_MATH_OK") == 4
    assert "XFORM_CROSS_OK" not in ver


def test_corrupted_reference_contradicting_equations_is_hard_error():
    ref = _load_ref()
    broken = {
        "transformations": [
            dict(t) for t in ref["transformations"]
            if t.get("source") == "epsg_method_1024_equations"
        ]
    }
    broken["transformations"][0]["expected_y"] += 1.0  # lie about Riyadh Y
    res = verify_frozen_equation_points(broken)
    assert res["ok"] is False
    codes_ = [f["code"] for f in res["findings"]]
    assert "XFORM_MATH_MISMATCH" in codes_
    assert any("the reference itself is wrong" in f["message"]
               for f in res["findings"] if f["code"] == "XFORM_MATH_MISMATCH")


def test_equation_source_marker_is_stable():
    from geologia.data_layer.transforms_math import EQUATION_SOURCE
    ref = _load_ref()
    tagged = [t["name"] for t in ref["transformations"]
              if t.get("source") == EQUATION_SOURCE]
    assert len(tagged) == 4


# --- 3. engine vs published equations (needs pyproj; honest skip) -----------
def _has_pyproj():
    try:
        import pyproj  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_pyproj(),
                    reason="pyproj absent — engine cross-check cannot run "
                           "and will NOT be claimed")
def test_installed_engine_agrees_with_published_equations():
    res = verify_frozen_equation_points(_load_ref())
    ver = [i for i in res["evidence"]["verified"]
           if i["code"] == "XFORM_CROSS_OK"]
    assert len(ver) == 4
    for i in ver:
        assert "pyproj" in i["check"]


@pytest.mark.skipif(not _has_pyproj(),
                    reason="pyproj absent — engine checks cannot run")
def test_pyproj_verify_now_covers_all_eight_frozen_points():
    from geologia.data_layer.reference import verify_transformations
    res = verify_transformations()
    assert res["ok"], res["findings"]
    assert res["total"] == 8 and res["checked"] == 8


# --- codes contract -----------------------------------------------------------
def test_math_codes_are_typed_with_severity():
    assert CODES["XFORM_MATH_MISMATCH"] == "error"
    assert CODES["XFORM_CROSS_MISMATCH"] == "error"
    assert CODES["XFORM_ENGINE_ABSENT"] == "warning"
    assert CODES["XFORM_MATH_OK"] == "info"
