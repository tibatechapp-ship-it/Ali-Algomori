"""Tests for Ali's domain-specific workflow playbooks."""
import pytest

from geologia_workspace.planner import SUPPORTED_DOMAINS, build_plan
from geologia_workspace.skill_workflows import (
    get_domain_workflow,
    supported_workflow_domains,
)


def test_workflow_playbooks_cover_all_agent_domains():
    assert set(supported_workflow_domains()) == set(SUPPORTED_DOMAINS)
    for domain in SUPPORTED_DOMAINS:
        workflow = get_domain_workflow(domain)
        assert workflow["domain"] == domain
        assert workflow["workflow_status"] == "planned_not_executed"
        assert len(workflow["steps"]) >= 4
        for step in workflow["steps"]:
            assert step["step_id"]
            assert step["objective"]
            assert step["required_inputs"]
            assert step["acceptance_checks"]
            assert step["expected_artifact"]
            assert step["status"] == "not_started"
            assert step["execution"] == "not_started"


def test_workflow_copy_is_safe_to_mutate():
    workflow = get_domain_workflow("hydrology")
    workflow["steps"][0]["required_inputs"].append("invented")
    assert "invented" not in get_domain_workflow("hydrology")["steps"][0]["required_inputs"]


def test_unknown_workflow_domain_fails_closed():
    with pytest.raises(ValueError, match="unsupported workflow domain"):
        get_domain_workflow("unknown")


def test_plan_contains_domain_workflow_and_keeps_execution_disabled():
    plan = build_plan("Groundwater assessment", language="en")
    step = plan["steps"][0]
    assert step["domain"] == "hydrology"
    assert step["skill_workflow"]["workflow_status"] == "planned_not_executed"
    assert step["skill_workflow"]["steps"][0]["step_id"] == "conceptual_model"
    assert step["execution"] == "not_started"
    assert plan["no_results_computed"] is True
