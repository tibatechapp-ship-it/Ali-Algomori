import copy
import math
import sys

import pytest

from geologia_workspace.utm_equations import (
    EQUATION_SOURCE,
    LAT_LIMIT_NORTH_DEG,
    LAT_LIMIT_SOUTH_DEG,
    central_meridian,
    detect_utm_zone,
    load_equation_points,
    reference_fingerprint,
    utm_forward,
    utm_inverse,
    verify_utm_equation_points,
)


def test_central_meridians_follow_utm_convention():
    assert central_meridian(1) == -177.0
    assert central_meridian(37) == 39.0
    assert central_meridian(38) == 45.0
    assert central_meridian(60) == 177.0


def test_central_meridian_refuses_invalid_zones():
    for zone in (0, 61, 37.5, True, "37"):
        with pytest.raises(ValueError, match="zone must be an integer"):
            central_meridian(zone)


@pytest.mark.parametrize(
    ("lon", "zone"),
    [
        (-180.0, 1),
        (-179.9, 1),
        (-6.0, 30),
        (-6.001, 29),
        (0.0, 31),
        (39.0, 37),
        (44.2, 38),
        (48.0, 39),
        (49.13, 39),
        (54.0, 40),
        (179.999, 60),
    ],
)
def test_zone_detection_covers_the_full_longitude_range(lon, zone):
    assert detect_utm_zone(lon) == zone


def test_zone_detection_refuses_out_of_range_longitudes():
    for lon in (180.0, -180.001, float("nan"), float("inf"), "44.2", True):
        with pytest.raises(ValueError):
            detect_utm_zone(lon)


def test_forward_yemen_points_stay_near_published_utm_values():
    # Golden values come from the frozen reference; here we only assert the
    # well-known structural properties of UTM: easting near the false easting
    # for longitudes close to the central meridian, northing scales with latitude.
    easting, northing = utm_forward(37, 39.0001, 15.35)
    assert 499000 < easting < 501000
    assert 1_600_000 < northing < 1_800_000
    easting_s, northing_s = utm_forward(49, 111.0001, -45.0)
    assert 499000 < easting_s < 501000
    assert 4_000_000 < northing_s < 6_000_000


def test_forward_refuses_latitude_outside_utm_domain():
    with pytest.raises(ValueError, match="latitude outside the UTM domain"):
        utm_forward(33, 18.0, LAT_LIMIT_NORTH_DEG + 0.1)
    with pytest.raises(ValueError, match="latitude outside the UTM domain"):
        utm_forward(49, 110.0, LAT_LIMIT_SOUTH_DEG - 0.1)


def test_forward_refuses_non_finite_or_non_numeric_values():
    for lon in (float("nan"), float("inf"), "44.2", True):
        with pytest.raises(ValueError):
            utm_forward(37, lon, 15.35)
    with pytest.raises(ValueError):
        utm_forward(37, 44.2, float("nan"))


def test_forward_refuses_invalid_zones():
    for zone in (0, 61, 37.5, "37", True):
        with pytest.raises(ValueError, match="zone must be an integer"):
            utm_forward(zone, 44.2, 15.35)


def test_inverse_requires_explicit_hemisphere():
    with pytest.raises(ValueError, match="hemisphere"):
        utm_inverse(37, "", 500000.0, 1700000.0)
    with pytest.raises(ValueError, match="hemisphere"):
        utm_inverse(37, None, 500000.0, 1700000.0)


def test_forward_inverse_roundtrip_closes_within_series_truncation():
    samples = [
        (38, 44.2, 15.35),
        (38, 43.25, 13.58),
        (38, 45.03, 12.78),
        (39, 49.13, 14.52),
        (39, 52.2, 15.9),
        (39, 53.9, 12.5),
        (49, 110.0, -45.0),
        (33, 17.9, 59.5),
    ]
    for zone, lon, lat in samples:
        easting, northing = utm_forward(zone, lon, lat)
        hemisphere = "south" if lat < 0 else "north"
        actual_lon, actual_lat = utm_inverse(zone, hemisphere, easting, northing)
        assert abs(actual_lon - lon) < 2e-6
        assert abs(actual_lat - lat) < 2e-6


def test_frozen_equation_points_are_reproduced():
    reference = load_equation_points()
    points = [
        p for p in reference["transformations"] if p["source"] == EQUATION_SOURCE
    ]
    assert len(points) == 16
    result = verify_utm_equation_points(reference, crosscheck_engine=False)
    assert result["ok"] is True, result["findings"]
    assert result["equation_points_checked"] == result["equation_points_total"] == 16
    assert result["engine_crosscheck_status"] == "not_requested"
    assert reference_fingerprint() and len(reference_fingerprint()) == 64


def test_corrupted_frozen_reference_is_a_hard_error():
    reference = copy.deepcopy(load_equation_points())
    target = next(
        p for p in reference["transformations"] if p["source"] == EQUATION_SOURCE
    )
    target["expected_y"] += 1.0
    result = verify_utm_equation_points(reference, crosscheck_engine=False)
    assert result["ok"] is False
    assert any(item["code"] == "UTM_MATH_MISMATCH" for item in result["findings"])


def test_equation_proof_remains_available_without_pyproj(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyproj", None)
    result = verify_utm_equation_points()
    assert result["ok"] is True, result["findings"]
    assert result["equation_points_checked"] == 16
    assert result["engine_crosscheck_status"] == "unverifiable"
    assert any(item["code"] == "UTM_ENGINE_ABSENT" for item in result["findings"])


def test_engine_crosscheck_is_explicit_when_available():
    try:
        import pyproj  # noqa: F401
    except ImportError:
        pytest.skip("pyproj is not installed")
    result = verify_utm_equation_points()
    assert result["ok"] is True, result["findings"]
    assert result["engine_crosscheck_status"] == "passed"


def test_module_scope_statement_is_honest():
    result = verify_utm_equation_points(crosscheck_engine=False)
    assert "not CRS selection" in result["scope"]
    assert "or geology" in result["scope"]
    assert math.isfinite(LAT_LIMIT_NORTH_DEG)
