# Task ledger with mandatory transition gates and isolation spec.
#
# The owner's binding standard (digest_10_acceptance_standard.md), encoded as
# invariants: a task may reach "executed" ONLY when (a) every input dataset
# passed validation, and (b) the engine has status "certified" with a pinned
# version and resource limits. In the foundation phase NO engine is certified,
# so execution is structurally impossible and every attempt is refused with an
# honest, policy-citing message. This is by design, not a limitation to hide.
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional

from geologia.data_layer.records import dataset_is_validated_pass, store_dir
from geologia.registry import get_engine

STATES = ("planned", "inputs_validated", "ready", "executed", "verified", "rejected")

EXECUTION_REFUSAL_AR = (
    "رفض التنفيذ: لا يوجد أي محرك بحالة certified بعد (كل المحركات planned وفق "
    "سياسة الدمج)، ولا نموذج بيانات معتمد بعد. طبقة البيانات الموثوقة والاختبارات "
    "المرجعية أولاً، ثم يُفتح التنفيذ — راجع ADR-0003 ومعيار القبول الملزم."
)
EXECUTION_REFUSAL_EN = (
    "Execution refused: no engine has status 'certified' yet (all engines are "
    "'planned' per the integration policy) and no trusted data model exists. The "
    "trusted data layer and reference tests come first — see ADR-0003."
)


class TaskGateError(RuntimeError):
    """A mandatory transition gate refused the state change."""

    def __init__(self, message: str, gate: str, language: str = "ar") -> None:
        self.gate = gate
        self.language = language
        self.message = message
        super().__init__(message)


def _read_store() -> dict:
    path = store_dir() / "tasks.json"
    if not path.exists():
        return {"tasks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_store(data: dict) -> None:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "tasks.json"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_task(title: str, engine_id: str, dataset_ids: List[str],
                params: Optional[dict] = None,
                isolation: Optional[dict] = None,
                notes: str = "") -> dict:
    """Register a task. Creation is allowed for planned engines — but the task
    can never execute until the engine is certified (see transition())."""
    if not title or not engine_id:
        raise ValueError("title and engine_id are required")
    card = get_engine(engine_id)
    if card is None:
        raise ValueError(f"engine_id {engine_id!r} not in registry")
    if not dataset_ids:
        raise ValueError("at least one dataset_id is required (real data only)")
    iso = isolation or {}
    task = {
        "id": f"task-{_now().replace('-', '').replace(':', '')[:14]}"
        f"-{len(_read_store()['tasks']) + 1:03d}",
        "title": title,
        "engine_id": engine_id,
        "engine_status_at_creation": card["status"],
        "dataset_ids": list(dataset_ids),
        "params": params or {},
        "isolation": {
            "env": iso.get("env", "isolated_required"),
            "pinned_version": iso.get("pinned_version"),
            "cpu": iso.get("cpu"),
            "memory_mb": iso.get("memory_mb"),
            "timeout_seconds": iso.get("timeout_seconds"),
        },
        "state": "planned",
        "history": [{"at": _now(), "from": None, "to": "planned", "gate": "created"}],
        "notes": notes,
        "created_at": _now(),
    }
    store = _read_store()
    store["tasks"].append(task)
    _write_store(store)
    return task


def list_tasks() -> List[dict]:
    return _read_store()["tasks"]


def get_task(task_id: str) -> Optional[dict]:
    for t in _read_store()["tasks"]:
        if t["id"] == task_id:
            return t
    return None


def transition(task_id: str, to_state: str, reason: str = "",
               language: str = "ar") -> dict:
    """Apply a gated state transition. Gates (binding):

    - planned -> inputs_validated : every dataset must be registered AND have
      a passed validation report.
    - inputs_validated -> ready   : engine must be 'certified', pinned version
      and resource limits present.
    - ready -> executed           : same certification gate, then execution-time
      checksum re-verification + the certified engine actually runs and writes
      an evidence report (data_layer/executor.py).
    - executed -> verified        : gate 4 as code — the evidence report must be
      complete (inputs+checksums, citations, params, results, uncertainty,
      validity limits, disclaimers).
    - planned -> rejected         : allowed with a reason (honest closure).
    """
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    if to_state not in STATES:
        raise ValueError(f"unknown state {to_state!r}")
    current = task["state"]
    allowed = {
        "planned": {"inputs_validated", "rejected"},
        "inputs_validated": {"ready", "rejected"},
        "ready": {"executed", "rejected"},
        "executed": {"verified", "rejected"},
        "verified": set(),
        "rejected": set(),
    }
    if to_state not in allowed[current]:
        raise TaskGateError(
            f"transition {current} -> {to_state} is not allowed", gate="state_machine",
            language=language)
    if to_state == "inputs_validated":
        unvalidated = [ds for ds in task["dataset_ids"] if not dataset_is_validated_pass(ds)]
        if unvalidated:
            raise TaskGateError(
                f"gate inputs_validated: datasets without passed validation: {unvalidated}",
                gate="data_validation", language=language)
    if to_state in ("ready", "executed"):
        card = get_engine(task["engine_id"])
        iso = task["isolation"]
        problems = []
        if not card or card["status"] != "certified":
            problems.append(f"engine {task['engine_id']} is {card['status']!r}, needs 'certified'")
        if not iso.get("pinned_version"):
            problems.append("missing pinned_version")
        if not (iso.get("cpu") and iso.get("memory_mb") and iso.get("timeout_seconds")):
            problems.append("missing resource limits (cpu/memory_mb/timeout_seconds)")
        if problems:
            msg = (EXECUTION_REFUSAL_AR if language == "ar" else EXECUTION_REFUSAL_EN)
            raise TaskGateError(f"{msg} | gates: {'; '.join(problems)}",
                                gate="engine_certification", language=language)
    if to_state == "executed":
        # Certification gate passed -> run for real, with execution-time
        # integrity checks. Any refusal raises before the state flips.
        from geologia.data_layer.executor import run_task_execution
        report = run_task_execution(task, language=language)
        task["execution_report_path"] = report["report_path"]
        task["execution_summary"] = {
            "engine_id": report["engine_id"],
            "engine_version": report["engine_version"],
            "n_results": len(report["results"]),
            "issue_codes": [i["code"] for i in report.get("issues", [])],
            "sigma_phi_vv": report["uncertainty"]["sigma_phi_vv"],
            "citations": len(report["method"]["citations"]),
        }
    if to_state == "verified":
        from geologia.data_layer.executor import verify_evidence
        verify_evidence(task, language=language)
    task["state"] = to_state
    task["history"].append({"at": _now(), "from": current, "to": to_state,
                            "gate": "passed" if to_state != "rejected" else "rejected",
                            "reason": reason})
    _save_task(task)
    return task


def _save_task(task: dict) -> None:
    store = _read_store()
    for i, t in enumerate(store["tasks"]):
        if t["id"] == task["id"]:
            store["tasks"][i] = task
            break
    _write_store(store)
