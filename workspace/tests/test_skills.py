"""Tests for Ali's auditable specialist competency profiles."""
import pytest

from geologia_workspace.planner import SUPPORTED_DOMAINS, build_plan
from geologia_workspace.skills import (
    DOMAIN_SKILLS,
    assess_skill_readiness,
    get_domain_skill_profile,
)


def test_skill_contract_covers_every_planner_domain():
    assert set(DOMAIN_SKILLS) == set(SUPPORTED_DOMAINS)
    for domain in SUPPORTED_DOMAINS:
        profile = get_domain_skill_profile(domain)
        assert profile["competencies"] and profile["required_inputs"]
        assert profile["outputs"] and profile["verification"]
        assert profile["safety_limits"]
        assert profile["model_training_claim"] is False
        assert profile["engine_execution_claim"] is False


def test_no_input_inventory_is_not_misreported_as_ready():
    report = assess_skill_readiness(["hydrology"])
    assert report["readiness_status"] == "not_assessed"
    assert report["missing_required_inputs"] is None
    assert report["mastery_status"] == "not_certified"


def test_missing_input_gaps_and_validation_readiness():
    required = set(get_domain_skill_profile("gis")["required_inputs"])
    partial = assess_skill_readiness(["gis"], required - {"crs_definition"})
    assert partial["readiness_status"] == "missing_required_inputs"
    assert partial["missing_required_inputs"] == ["crs_definition"]
    complete = assess_skill_readiness(["gis"], required)
    assert complete["readiness_status"] == "ready_for_validation"
    assert complete["missing_required_inputs"] == []


def test_multi_domain_required_inputs_are_deduplicated():
    report = assess_skill_readiness(["hydrology", "well_logs"], {"las_files"})
    assert report["required_inputs"] == sorted(set(report["required_inputs"]))
    assert "well_logs" in report["required_inputs"]


def test_unknown_domain_fails_closed():
    with pytest.raises(ValueError, match="unsupported skill domain"):
        get_domain_skill_profile("not-a-domain")


def test_profiles_are_defensive_copies():
    profile = get_domain_skill_profile("gis")
    profile["competencies"].append("fabricated")
    assert "fabricated" not in get_domain_skill_profile("gis")["competencies"]


def test_plans_include_skill_readiness_but_no_execution_claim():
    plan = build_plan("Groundwater and GIS mapping", language="en")
    skills = plan["agent_skill_readiness"]
    assert {item["domain"] for item in skills["domain_profiles"]} == {
        "hydrology", "gis"
    }
    assert skills["readiness_status"] == "not_assessed"
    assert skills["training_status"] == "no_neural_training_performed"
    assert plan["no_results_computed"] is True
