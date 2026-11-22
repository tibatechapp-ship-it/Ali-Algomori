"""Workspace CRS content tests: zone verification by inverse math + workers.

The zone half of the governing sequence step 4: a declared UTM zone is
tested against actual content through the frozen UTM equations, and the
analysis runs in bounded workers with classified refusals at both
boundaries. Golden UTM literals below are the same frozen reference the
display gate uses (pyproj 3.7.2, see test_api_dataset_display).
"""
from __future__ import annotations

import pytest

import geologia_workspace.analysis_workers as aw_module
from geologia_workspace.analysis_workers import (
    AnalysisRefused,
    AnalysisWorkers,
)
from geologia_workspace.crs_content import (
    extract_geojson_positions,
    loudest_truth,
    parse_utm_epsg,
    utm_zone_longitude_band,
    verify_utm_zone_from_content,
)

# Frozen golden reference: (lon, lat) -> (easting_m, northing_m) EPSG:32638
# (pyproj 3.7.2 on 2026-11-23; identical literals to the display tests).
GOLDEN_UTM38N = [
    (414133.1015027688, 1697196.8389235127),
    (419519.25330974074, 1702708.4364362634),
    (408744.4018885594, 1691686.3892644697),
]


def test_zone_band_table():
    assert utm_zone_longitude_band(38) == (42.0, 48.0)
    assert utm_zone_longitude_band(1) == (-180.0, -174.0)
    assert utm_zone_longitude_band(60) == (174.0, 180.0)
    with pytest.raises(ValueError):
        utm_zone_longitude_band(0)
    with pytest.raises(ValueError):
        utm_zone_longitude_band(61)


def test_parse_utm_epsg():
    assert parse_utm_epsg("EPSG:32638") == (38, "north")
    assert parse_utm_epsg("epsg:32707") == (7, "south")
    assert parse_utm_epsg(" EPSG:32638 ") == (38, "north")
    assert parse_utm_epsg("EPSG:4326") is None
    assert parse_utm_epsg("EPSG:32699") is None  # zone 99 out of range
    assert parse_utm_epsg(None) is None
    assert parse_utm_epsg("") is None


def test_extract_positions_bounded_and_nested():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Point",
                          "coordinates": [414133.1, 1697196.8, 99.0]}},
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [408744.4, 1691686.4], [424849.1, 1691628.9],
                 [424902.8, 1708221.2], [408744.4, 1691686.4],
             ]]}},
        ],
    }
    pairs = extract_geojson_positions(payload)
    assert pairs == [
        (414133.1, 1697196.8),
        (408744.4, 1691686.4),
        (424849.1, 1691628.9),
        (424902.8, 1708221.2),
        (408744.4, 1691686.4),
    ]
    capped = extract_geojson_positions(payload, max_points=2)
    assert len(capped) == 2
    # booleans and non-numeric positions are skipped, never fabricated
    weird = {"type": "Feature", "geometry": {"type": "Point",
                                             "coordinates": [True, 5]}}
    assert extract_geojson_positions(weird) == []


def test_verify_zone_38_content_verified():
    verdict = verify_utm_zone_from_content(GOLDEN_UTM38N, 38, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_VERIFIED"
    assert verdict["truth_class"] == "verified_content"
    assert verdict["declared_band"] == [42.0, 48.0]
    assert verdict["n_outside_band"] == 0
    assert verdict["suggested_zone"] == 38
    # round-trip reference matching must be sub-metre (series tolerance)
    assert verdict["max_roundtrip_residual_m"] < 0.001
    # the honest limit is carried ON the verdict, not buried in prose
    assert "not confirmable" in verdict["note_en"]
    assert "مرساة" in verdict["note_ar"]


def test_verify_zone_label_not_falsifiable_from_easting_northing_alone():
    """The honest-limit test: the SAME golden-38 pairs declared as zone 37
    invert to an equally self-consistent position inside zone 37's band —
    a zone NUMBER cannot be falsified from (easting, northing) alone.
    The verdict must say verified_content WITH the limit note, never claim
    a contradiction that pure E/N content cannot prove."""
    verdict = verify_utm_zone_from_content(GOLDEN_UTM38N, 37, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_VERIFIED"
    assert verdict["truth_class"] == "verified_content"
    assert verdict["declared_band"] == [36.0, 42.0]
    assert "not confirmable" in verdict["note_en"]


def test_verify_degree_magnitudes_under_utm_declaration_caught():
    """Degree-like magnitudes stored under a UTM declaration: the inverse
    does not raise (the series is total over the magnitudes) but the
    recovered longitudes fall outside the zone band — the band check is
    what catches degree-in-disguise content."""
    verdict = verify_utm_zone_from_content(
        [(44.2, 15.35), (44.25, 15.4)], 38, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_MISMATCH"
    assert verdict["truth_class"] == "contradicted_declared"
    assert verdict["n_outside_band"] == 2


def test_verify_implausible_easting_outside_band_mismatch():
    # easting 150000 m at this northing implies lon ~41.7 — outside the
    # zone-38 band (42..48): the content is not plausible under zone 38.
    verdict = verify_utm_zone_from_content(
        [(150000.0, 1697196.8389)], 38, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_MISMATCH"
    assert verdict["truth_class"] == "contradicted_declared"
    assert verdict["suggested_zone"] == 37


def test_verify_zone_out_of_range_is_unverifiable():
    verdict = verify_utm_zone_from_content(GOLDEN_UTM38N, 0, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_UNVERIFIABLE"
    assert verdict["truth_class"] == "undetermined"


def test_verify_empty_sample_is_unverifiable():
    verdict = verify_utm_zone_from_content([], 38, "north")
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_UNVERIFIABLE"
    assert verdict["n_points_checked"] == 0


def test_loudest_truth_ordering():
    assert loudest_truth("verified_content", "contradicted_declared") == \
        "contradicted_declared"
    assert loudest_truth("verified_content", "undetermined") == "undetermined"
    assert loudest_truth("declared_unverified", "verified_content") == \
        "verified_content"
    assert loudest_truth("declared_unverified") == "declared_unverified"
    assert loudest_truth() == "undetermined"


# --- analysis workers ---------------------------------------------------------

def test_worker_success_envelope():
    workers = AnalysisWorkers()
    out = workers.submit_analysis(lambda a, b: a + b, 2, b=3)
    assert out["ok"] is True
    assert out["result"] == 5
    assert out["truth_class"] == "verified_content"
    assert out["executed_in"] == "analysis_worker"


def test_worker_kernel_error_propagates_untouched():
    workers = AnalysisWorkers()

    def boom():
        raise ArithmeticError("kernel honesty")

    with pytest.raises(ArithmeticError):
        workers.submit_analysis(boom)


def test_worker_saturation_refusal(monkeypatch):
    import threading

    monkeypatch.setattr(aw_module, "queue_cap", lambda: 1)
    workers = AnalysisWorkers()
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        release.wait(timeout=10)

    # the pool is synchronous-per-caller: saturate it from a background
    # thread so the main thread can observe the classified refusal
    done = threading.Event()

    def hold():
        workers.submit_analysis(blocking, timeout_s=30)
        done.set()

    t = threading.Thread(target=hold, daemon=True)
    t.start()
    assert started.wait(timeout=5)
    with pytest.raises(AnalysisRefused) as exc:
        workers.submit_analysis(lambda: 1, timeout_s=30)
    assert exc.value.code == "analysis.refusal.workers_saturated"
    release.set()
    assert done.wait(timeout=10)


def test_worker_timeout_refusal(monkeypatch):
    import time

    monkeypatch.setattr(aw_module, "analysis_timeout_s", lambda: 1)
    workers = AnalysisWorkers()
    with pytest.raises(AnalysisRefused) as exc:
        workers.submit_analysis(time.sleep, 3, timeout_s=1)
    assert exc.value.code == "analysis.refusal.timeout"


def test_worker_env_bounds(monkeypatch):
    monkeypatch.setenv("GEOLOGIA_ANALYSIS_WORKERS", "99")
    assert aw_module.max_workers() == 2  # out of band -> default, never trusted
    monkeypatch.setenv("GEOLOGIA_ANALYSIS_WORKERS", "abc")
    assert aw_module.max_workers() == 2
    monkeypatch.setenv("GEOLOGIA_ANALYSIS_WORKERS", "4")
    assert aw_module.max_workers() == 4
    monkeypatch.delenv("GEOLOGIA_ANALYSIS_WORKERS")
    assert aw_module.max_workers() == 2
