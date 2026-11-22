"""Tests for Ali's offline multilingual routing benchmark."""
from geologia_workspace.skill_evaluation import evaluate_routing_benchmark


def test_curated_multilingual_routing_benchmark_passes_exactly():
    report = evaluate_routing_benchmark()
    assert report["status"] == "passed"
    assert report["exact_match_count"] == report["case_count"]
    assert report["exact_match_accuracy"] == 1.0
    assert report["expected_domain_recall"] == 1.0
    assert report["unexpected_domain_count"] == 0
    assert all(case["passed"] for case in report["cases"])


def test_benchmark_is_explicitly_not_scientific_validation():
    report = evaluate_routing_benchmark()
    assert report["scope"] == "curated deterministic routing regression only"
    assert "scientific correctness" in report["not_evaluated"]
    assert "routing confidence calibration" in report["not_evaluated"]
