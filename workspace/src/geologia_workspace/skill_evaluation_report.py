"""Versioned, auditable skill-evaluation report contract.

This module validates benchmark evidence metadata. It does not execute a skill,
score scientific correctness, or certify a domain capability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

REPORT_SCHEMA_VERSION = "1.0.0"
_SCORE_KEYS = {
    "routing",
    "input_validation",
    "scientific_correctness",
    "provenance",
    "reproducibility",
    "uncertainty",
    "abstention",
    "safety",
    "usability",
}
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_STATUSES = {"passed", "failed", "review_required"}


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_skill_evaluation_report(report: Mapping[str, Any]) -> list[str]:
    """Return deterministic validation errors; an empty list means schema-valid."""
    errors: list[str] = []
    required_strings = (
        "report_id",
        "skill_id",
        "skill_version",
        "benchmark_id",
        "benchmark_version",
        "generated_at",
    )
    for key in required_strings:
        if not _is_nonempty_string(report.get(key)):
            errors.append(f"{key} must be a non-empty string")

    if report.get("report_schema_version") != REPORT_SCHEMA_VERSION:
        errors.append("report_schema_version must equal " + REPORT_SCHEMA_VERSION)

    timestamp = report.get("generated_at")
    if _is_nonempty_string(timestamp):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append("generated_at must include a timezone")
        except ValueError:
            errors.append("generated_at must be ISO 8601")

    for key in ("environment", "parameters", "scores", "hard_gates"):
        if not isinstance(report.get(key), Mapping):
            errors.append(f"{key} must be an object")

    environment = report.get("environment")
    if isinstance(environment, Mapping):
        if not _is_nonempty_string(environment.get("python")):
            errors.append("environment.python must be a non-empty string")
        if not _is_nonempty_string(environment.get("platform")):
            errors.append("environment.platform must be a non-empty string")

    inputs = report.get("inputs")
    if not isinstance(inputs, list):
        errors.append("inputs must be a list")
    else:
        for index, item in enumerate(inputs):
            if not isinstance(item, Mapping):
                errors.append(f"inputs[{index}] must be an object")
                continue
            if not _is_nonempty_string(item.get("name")):
                errors.append(f"inputs[{index}].name must be a non-empty string")
            if not _is_nonempty_string(item.get("sha256")) or not _SHA256_RE.fullmatch(
                str(item.get("sha256", ""))
            ):
                errors.append(f"inputs[{index}].sha256 must be a 64-character SHA-256")

    outcomes = report.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        errors.append("outcomes must be a non-empty list")
    else:
        for index, item in enumerate(outcomes):
            if not isinstance(item, Mapping):
                errors.append(f"outcomes[{index}] must be an object")
                continue
            for key in ("case_id", "result"):
                if not _is_nonempty_string(item.get(key)):
                    errors.append(f"outcomes[{index}].{key} must be a non-empty string")

    scores = report.get("scores")
    if isinstance(scores, Mapping):
        for key, value in scores.items():
            if key not in _SCORE_KEYS:
                errors.append(f"scores contains unsupported dimension: {key}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"scores.{key} must be numeric")
            elif not 0.0 <= value <= 1.0:
                errors.append(f"scores.{key} must be between 0 and 1")

    gates = report.get("hard_gates")
    if isinstance(gates, Mapping):
        if not gates:
            errors.append("hard_gates must contain at least one gate")
        for key, value in gates.items():
            if not _is_nonempty_string(key):
                errors.append("hard gate names must be non-empty strings")
            if not isinstance(value, bool):
                errors.append(f"hard_gates.{key} must be boolean")
        if report.get("status") == "passed" and any(value is not True for value in gates.values()):
            errors.append("status cannot be passed when any hard gate is false")

    status = report.get("status")
    if status not in _STATUSES:
        errors.append("status must be passed, failed, or review_required")

    for key in ("failures", "limitations"):
        value = report.get(key)
        if not isinstance(value, list) or any(not _is_nonempty_string(item) for item in value):
            errors.append(f"{key} must be a list of non-empty strings")

    reviewer = report.get("reviewer")
    if reviewer is not None and not isinstance(reviewer, Mapping):
        errors.append("reviewer must be an object or null")
    if isinstance(reviewer, Mapping):
        if not _is_nonempty_string(reviewer.get("name")):
            errors.append("reviewer.name must be a non-empty string")
        if not _is_nonempty_string(reviewer.get("review_status")):
            errors.append("reviewer.review_status must be a non-empty string")

    return errors


def new_skill_evaluation_report(
    *,
    report_id: str,
    skill_id: str,
    skill_version: str,
    benchmark_id: str,
    benchmark_version: str,
    environment: Mapping[str, str],
    inputs: list[Mapping[str, str]],
    parameters: Mapping[str, Any],
    outcomes: list[Mapping[str, Any]],
    scores: Mapping[str, float],
    hard_gates: Mapping[str, bool],
    failures: list[str] | None = None,
    limitations: list[str] | None = None,
    reviewer: Mapping[str, str] | None = None,
    status: str = "review_required",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build and validate a report, raising ValueError on contract violations."""
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "benchmark_id": benchmark_id,
        "benchmark_version": benchmark_version,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "environment": dict(environment),
        "inputs": [dict(item) for item in inputs],
        "parameters": dict(parameters),
        "outcomes": [dict(item) for item in outcomes],
        "scores": dict(scores),
        "hard_gates": dict(hard_gates),
        "status": status,
        "failures": list(failures or []),
        "limitations": list(limitations or []),
        "reviewer": dict(reviewer) if reviewer is not None else None,
    }
    errors = validate_skill_evaluation_report(report)
    if errors:
        raise ValueError("invalid skill evaluation report: " + "; ".join(errors))
    return report
