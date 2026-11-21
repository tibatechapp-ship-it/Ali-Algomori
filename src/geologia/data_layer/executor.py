# Locked executor with evidence produced at execution time.
#
# An engine runs ONLY through this module and ONLY after the task-ledger gates
# passed (engine certified + pinned version + resource limits). Immediately
# before running, every input dataset's sha256 is re-verified: tampering
# detected AT EXECUTION TIME stops the run (gate data_tamper). The execution
# report is the evidence artifact demanded by gate 4 of the acceptance
# standard: inputs+checksums, method+citations, pinned params, results,
# uncertainty bounds, validity limits, disclaimers.
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from geologia.data_layer import records as ds
from geologia.engines import get_executor
from geologia.registry import get_engine

REQUIRED_EVIDENCE_KEYS = (
    "inputs", "method", "results", "uncertainty",
    "validity_limits_ar", "disclaimers_ar",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_report(task_id: str, report: dict) -> str:
    d = ds.store_dir() / "executions"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{task_id}.json"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(report, tmp, ensure_ascii=False, indent=2)
        tmp_name = tmp.name
    os.replace(tmp_name, path)
    return str(path)


def run_task_execution(task: dict, language: str = "ar") -> dict:
    """Execute a certified task's engine with execution-time integrity checks.

    Raises data_layer.tasks.TaskGateError on any refusal (never computes on
    tampered or non-conforming inputs)."""
    from geologia.data_layer.certification import certification_status
    from geologia.data_layer.tasks import TaskGateError

    engine_id = task["engine_id"]
    card = get_engine(engine_id)
    runner = get_executor(engine_id)
    if runner is None or card is None or card.get("family") != "first_party":
        raise TaskGateError(
            f"no executable implementation for {engine_id!r} — only certified "
            "first-party engines may execute", gate="no_executor", language=language)

    contract = card.get("input_contract") or {}
    datasets: List[dict] = []
    for ds_id in task["dataset_ids"]:
        rec = ds.get_dataset(ds_id)
        if rec is None:
            raise TaskGateError(
                f"dataset {ds_id!r} not registered", gate="inputs", language=language)
        chk = ds.verify_checksum(ds_id)  # tamper detection at execution time
        if not chk["checksum_ok"]:
            raise TaskGateError(
                f"dataset {ds_id!r} checksum mismatch at execution time — "
                "execution refused (tamper detected)", gate="data_tamper",
                language=language)
        datasets.append(rec)
    if contract.get("count") is not None and len(datasets) != contract["count"]:
        raise TaskGateError(
            f"engine expects {contract['count']} input(s), task has {len(datasets)}",
            gate="input_contract", language=language)
    if contract.get("dtype") and any(d.get("dtype") != contract["dtype"]
                                     for d in datasets):
        raise TaskGateError(
            f"engine expects dtype {contract['dtype']!r}; task inputs differ",
            gate="input_contract", language=language)

    try:
        out = runner(datasets[0]["path"], params=task.get("params") or {})
    except ValueError as exc:  # includes PorosityEngineError
        raise TaskGateError(f"engine refused to run: {exc}",
                            gate="invalid_params", language=language)
    except FileNotFoundError as exc:
        raise TaskGateError(str(exc), gate="input_missing", language=language)

    cert = certification_status(engine_id)
    report = {
        "task_id": task["id"],
        "engine_id": engine_id,
        "engine_version": out["engine_version"],
        "executed_at": _now(),
        "inputs": [{
            "dataset_id": d["id"],
            "path": d["path"],
            "sha256": d["sha256"],
            "dtype": d.get("dtype"),
            "checksum_verified_at_execution": True,
        } for d in datasets],
        "method": {
            "formula": out["formula"],
            "citations": out["citations"],
            "params": out["params"],
            "deterministic": out["deterministic"],
            "third_party_dependencies": out["third_party_dependencies"],
        },
        "results": out["results"],
        "issues": out["issues"],
        "uncertainty": out["uncertainty"],
        "validity_limits_ar": out["validity_limits_ar"],
        "disclaimers_ar": out["disclaimers_ar"],
        "certification": {
            "certified_at": (cert["record"] or {}).get("certified_at"),
            "reference_version": (cert["record"] or {}).get("reference_version"),
            "max_abs_error": (cert["record"] or {}).get("max_abs_error"),
        },
        "isolation": task.get("isolation", {}),
        "no_generated_content": True,
    }
    report["report_path"] = _write_report(task["id"], report)
    return report


def verify_evidence(task: dict, language: str = "ar") -> dict:
    """Gate 4 as code: a task may become 'verified' only when its execution
    report carries complete evidence."""
    from geologia.data_layer.tasks import TaskGateError

    path = task.get("execution_report_path")
    if not path or not Path(path).exists():
        raise TaskGateError(
            "cannot verify: no execution report exists", gate="evidence_incomplete",
            language=language)
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_EVIDENCE_KEYS if k not in report]
    if missing:
        raise TaskGateError(
            f"evidence incomplete, missing: {', '.join(missing)}",
            gate="evidence_incomplete", language=language)
    if not report["method"].get("citations"):
        raise TaskGateError(
            "evidence incomplete: method has no citations",
            gate="evidence_incomplete", language=language)
    if not all(i.get("sha256") for i in report["inputs"]):
        raise TaskGateError(
            "evidence incomplete: inputs missing checksums",
            gate="evidence_incomplete", language=language)
    if not report["inputs"] or not all(
            i.get("checksum_verified_at_execution") for i in report["inputs"]):
        raise TaskGateError(
            "evidence incomplete: inputs were not re-verified at execution time",
            gate="evidence_incomplete", language=language)
    # Tamper check AFTER execution too: verified must not bless a run whose
    # inputs changed between execution and verification.
    for i in report["inputs"]:
        chk = ds.verify_checksum(i["dataset_id"])
        if not chk["checksum_ok"]:
            raise TaskGateError(
                f"input {i['dataset_id']!r} changed after execution — "
                "verification refused", gate="data_tamper", language=language)
    return report
