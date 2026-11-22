"""Regression tests for the lightweight groundwater time-series skill."""
import hashlib

import pytest

from geologia_workspace.hydrology_skill import analyze_water_level_timeseries


def _write_csv(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_water_level_skill_returns_descriptive_statistics_and_hash(tmp_path):
    path = _write_csv(
        tmp_path / "levels.csv",
        "timestamp,water_level_m\n"
        "2026-01-01T00:00:00Z,10.0\n"
        "2026-01-02T00:00:00Z,11.0\n"
        "2026-01-03T00:00:00Z,12.0\n",
    )
    report = analyze_water_level_timeseries(
        path, vertical_datum="MSL", measurement_reference="elevation"
    )
    assert report["status"] == "completed"
    assert report["metadata_status"] == "declared"
    assert report["row_count"] == 3
    assert report["statistics"]["minimum_m"] == 10.0
    assert report["statistics"]["maximum_m"] == 12.0
    assert report["statistics"]["mean_m"] == 11.0
    assert report["statistics"]["descriptive_linear_slope_m_per_day"] == pytest.approx(1.0)
    assert report["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["groundwater_model_executed"] is False


def test_missing_vertical_datum_and_reference_are_not_hidden(tmp_path):
    path = _write_csv(
        tmp_path / "levels.csv",
        "date,water_level_m\n2026-01-01,2.5\n2026-01-02,2.6\n",
    )
    report = analyze_water_level_timeseries(path)
    assert report["metadata_status"] == "incomplete"
    codes = {item["code"] for item in report["warnings"]}
    assert {"vertical_datum_missing", "measurement_reference_missing"} <= codes


def test_duplicate_and_irregular_timestamps_are_reported(tmp_path):
    path = _write_csv(
        tmp_path / "levels.csv",
        "timestamp,water_level_m\n"
        "2026-01-01T00:00:00Z,1\n"
        "2026-01-01T00:00:00Z,1.1\n"
        "2026-01-02T00:00:00Z,1.2\n"
        "2026-01-10T00:00:00Z,1.3\n",
    )
    report = analyze_water_level_timeseries(path)
    assert report["duplicate_timestamp_count"] == 1
    assert report["sampling"]["gap_count"] >= 1
    assert "duplicate_timestamps" in {item["code"] for item in report["warnings"]}


@pytest.mark.parametrize(
    "csv_text",
    [
        "date,level\n2026-01-01,1\n",
        "date,water_level_m\n2026-01-01,nan\n",
        "date,water_level_m\n2026-01-01,1\n2026-01-02\n",
    ],
)
def test_invalid_schema_or_measurements_fail_closed(tmp_path, csv_text):
    path = _write_csv(tmp_path / "bad.csv", csv_text)
    report = analyze_water_level_timeseries(path)
    assert report["status"] == "invalid_input"
    assert report["scientific_interpretation"] is False


def test_symlink_input_is_refused(tmp_path):
    real = _write_csv(
        tmp_path / "real.csv",
        "date,water_level_m\n2026-01-01,1\n",
    )
    link = tmp_path / "link.csv"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="non-symlink"):
        analyze_water_level_timeseries(link)
