"""Tests for the versioned skill evaluation evidence contract."""
import pytest

from geologia_workspace.skill_evaluation_report import (
    REPORT_SCHEMA_VERSION,
    new_skill_evaluation_report,
    validate_skill_evaluation_report,
)


def valid_report(**overrides):
    values = {
        "report_id": "run-0001",
        "skill_id": "hydrology.water_level_descriptive",
        "skill_version": "1.0.0",
        "benchmark_id": "hydrology-water-level-fixtures",
        "benchmark_version": "1.0.0",
        "generated_at": "2026-11-23T00:00:00+00:00",
        "environment": {"python": "3.12.8", "platform": "linux"},
        "inputs": [{"name": "levels.csv", "sha256": "a" * 64}],
        "parameters": {"time_column": "date", "value_column": "level_m"},
        "outcomes": [{"case_id": "valid-series", "result": "passed"}],
        "scores": {"input_validation": 1.0, "provenance": 1.0, "safety": 1.0},
        "hard_gates": {"input_integrity": True, "safety": True, "provenance": True},
        "status": "passed",
        "failures": [],
        "limitations": ["Descriptive statistics only; not a forecast."],
        "reviewer": None,
    }
    values.update(overrides)
    return values


def test_valid_report_contract_passes():
    report = valid_report()
    assert validate_skill_evaluation_report(report) == []
    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION


def test_passed_status_requires_all_hard_gates():
    report = valid_report(hard_gates={"input_integrity": True, "safety": False})
    assert "status cannot be passed when any hard gate is false" in (
        validate_skill_evaluation_report(report)
    )


def test_input_hash_must_be_sha256():
    report = valid_report(inputs=[{"name": "levels.csv", "sha256": "not-a-hash"}])
    assert any("sha256" in error for error in validate_skill_evaluation_report(report))


def test_timestamp_requires_timezone():
    report = valid_report(generated_at="2026-11-23T00:00:00")
    assert "generated_at must include a timezone" in validate_skill_evaluation_report(report)


def test_score_must_be_in_unit_interval():
    report = valid_report(scores={"safety": 1.2})
    assert "scores.safety must be between 0 and 1" in validate_skill_evaluation_report(report)


def test_builder_defaults_to_review_required_and_validates():
    report = new_skill_evaluation_report(
        report_id="run-0002",
        skill_id="gis.layer_qc",
        skill_version="0.1.0",
        benchmark_id="gis-qc-fixtures",
        benchmark_version="0.1.0",
        environment={"python": "3.12.8", "platform": "linux"},
        inputs=[{"name": "layers.gpkg", "sha256": "b" * 64}],
        parameters={},
        outcomes=[{"case_id": "basic", "result": "ok"}],
        scores={"input_validation": 1.0},
        hard_gates={"integrity": True, "safety": True},
        limitations=["Not a scientific interpretation."],
    )
    assert report["status"] == "review_required"
    assert validate_skill_evaluation_report(report) == []


def test_builder_rejects_invalid_report():
    with pytest.raises(ValueError, match="invalid skill evaluation report"):
        new_skill_evaluation_report(
            report_id="bad",
            skill_id="skill",
            skill_version="1",
            benchmark_id="bench",
            benchmark_version="1",
            environment={"python": "3.12", "platform": "linux"},
            inputs=[],
            parameters={},
            outcomes=[{"case_id": "x", "result": "ok"}],
            scores={"safety": 0.9},
            hard_gates={"safety": False},
            status="passed",
        )
