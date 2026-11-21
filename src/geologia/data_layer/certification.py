# Engine certification path — the binding gate 3 of the acceptance standard.
#
# certify_engine(engine_id) re-verifies, EVERY call, that the engine reproduces
# pinned reference results (computed with exact rational arithmetic, independent
# of the engine's float path) within tolerance on the golden reference input.
# Refusals are loud and reasoned:
#   - third-party engines cannot be certified (integration policy lifecycle);
#   - no registered reference test -> no certification;
#   - tampered reference input (sha256 mismatch) -> certification refused.
# A passing run writes a certification record to the trusted store; the
# registry overlay displays "certified" only while the latest record passes.
# A failed re-run overwrites the record with passed=false -> status falls back.
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from geologia.data_layer.records import sha256_file, store_dir
from geologia.engines import EXECUTORS
from geologia.registry import get_engine

REFERENCE_DIR = Path(__file__).parent.parent / "data" / "reference"

CERTIFY_THIRD_PARTY_AR = (
    "رفض الاعتماد: هذا المحرك من الطرف الثالث. وفق سياسة الدمج وADR-0003 لا يُعتمد "
    "أي محرك خارجي إلا بعد دورة حياة كاملة (evaluated → sandboxed → integrated) "
    "ثم اختبار مرجعي قابل لإعادة الإنتاج — ولا دمج لـ GemPy أو MODFLOW أو مثيلاتها "
    "قبل طبقة بيانات موثوقة واختبارات مرجعية مكتملة."
)


class CertificationRefused(RuntimeError):
    """Certification cannot proceed; carries machine-readable reasons."""

    def __init__(self, message: str, reasons: List[str]) -> None:
        self.reasons = reasons
        super().__init__(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_reference(engine_id: str) -> Optional[dict]:
    path = REFERENCE_DIR / f"{engine_id}_reference.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_reference_input(ref: dict) -> Path:
    """Locate the pinned reference input file (repo root or cwd relative)."""
    rel = ref["input"]["file"]
    candidates = [REFERENCE_DIR.parents[3] / rel, Path.cwd() / rel, Path(rel)]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"reference input not found: {rel}")


def _write_record(record: dict) -> None:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "certifications.json"
    data = {"certifications": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data["certifications"] = [
        r for r in data.get("certifications", [])
        if r["engine_id"] != record["engine_id"]
    ]
    data["certifications"].append(record)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def _compare_results(ref: dict, engine_out: dict) -> dict:
    tol = float(ref.get("tolerance", 1e-9))
    expected = ref["expected"]["results"]
    got = engine_out["results"]
    mismatches: List[str] = []
    max_err = 0.0
    if len(expected) != len(got):
        mismatches.append(f"row count {len(got)} != pinned {len(expected)}")
    for i, (exp, act) in enumerate(zip(expected, got)):
        if exp["depth_m"] != act["depth_m"]:
            mismatches.append(f"row {i}: depth {act['depth_m']} != {exp['depth_m']}")
            continue
        ev, av = exp["porosity_vv"], act["porosity_vv"]
        if ev is None or av is None:
            if ev != av:
                mismatches.append(f"row {i}: porosity None mismatch ({ev} vs {av})")
            continue
        err = abs(ev - av)
        max_err = max(max_err, err)
        if err > tol:
            mismatches.append(f"row {i}: |{av} - {ev}| = {err} > tol {tol}")
        exp_flag = exp.get("flag")
        act_flag = act.get("flag")
        if exp_flag != act_flag:
            mismatches.append(f"row {i}: flag {act_flag!r} != pinned {exp_flag!r}")
    sigma_err = abs(ref["expected"]["sigma_phi_vv"]
                    - engine_out["uncertainty"]["sigma_phi_vv"])
    if sigma_err > tol:
        mismatches.append(f"sigma_phi error {sigma_err} > tol {tol}")
    neg_expected = ref["expected"].get("negative_porosity_count", 0)
    neg_got = next((i["count"] for i in engine_out["issues"]
                    if i["code"] == "NEGATIVE_POROSITY"), 0)
    if neg_expected != neg_got:
        mismatches.append(
            f"NEGATIVE_POROSITY count {neg_got} != pinned {neg_expected}")
    return {"max_abs_error": max_err, "sigma_error": sigma_err,
            "mismatches": mismatches}


def certify_engine(engine_id: str, language: str = "ar") -> dict:
    """Run the pinned reference test; return the certification report.

    Raises ValueError for unknown engines, CertificationRefused for refusals
    (third-party, missing reference test, tampered reference input)."""
    card = get_engine(engine_id)
    if card is None:
        raise ValueError(f"engine_id {engine_id!r} not in registry")
    if card.get("family") != "first_party":
        raise CertificationRefused(CERTIFY_THIRD_PARTY_AR, [
            "family=third_party: needs evaluated→sandboxed→integrated lifecycle "
            "first (INTEGRATION_POLICY.md, ADR-0003)"])
    runner = EXECUTORS.get(engine_id)
    if runner is None:
        raise CertificationRefused(
            f"no reference test registered for {engine_id}", [
                "engine has no entry in engines.EXECUTORS — certification requires "
                "a reproducible pinned reference test"])
    ref = load_reference(engine_id)
    if ref is None:
        raise CertificationRefused(
            f"no pinned reference file for {engine_id}", [
                f"missing src/geologia/data/reference/{engine_id}_reference.json"])
    input_path = resolve_reference_input(ref)
    digest = sha256_file(str(input_path))
    if digest != ref["input"]["sha256"]:
        raise CertificationRefused(
            "reference input tampered — refusing to certify", [
                f"reference input sha256 {digest[:16]} != pinned "
                f"{ref['input']['sha256'][:16]}"])
    engine_out = runner(str(input_path), params=ref["params"])
    comparison = _compare_results(ref, engine_out)
    passed = not comparison["mismatches"]
    record = {
        "engine_id": engine_id,
        "engine_version": engine_out["engine_version"],
        "reference_version": ref["reference_version"],
        "reference_input_sha256": digest,
        "passed": passed,
        "max_abs_error": comparison["max_abs_error"],
        "sigma_error": comparison["sigma_error"],
        "tolerance": float(ref.get("tolerance", 1e-9)),
        "checked_rows": len(engine_out["results"]),
        "mismatches": comparison["mismatches"],
        "citations": ref["provenance"]["citations"],
        "certified_at": _now() if passed else None,
        "verified_at": _now(),
    }
    _write_record(record)
    return {
        "engine_id": engine_id,
        "certified": passed,
        "family": "first_party",
        "record": record,
        "message_ar": (
            "الاعتماد ناجح: المحرك أعاد القيم المرجعية المثبتة ضمن السماحية."
            if passed else
            "فشل الاعتماد: انحراف بين المحرك والمرجع المثبت — الحالة تعود planned."
        ),
    }


def certification_status(engine_id: str) -> dict:
    """Latest certification record summary for an engine (or honest empty)."""
    from geologia.data_layer.records import store_dir
    path = store_dir() / "certifications.json"
    if not path.exists():
        return {"engine_id": engine_id, "certified": False, "record": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = [r for r in data.get("certifications", [])
            if r["engine_id"] == engine_id]
    if not recs:
        return {"engine_id": engine_id, "certified": False, "record": None}
    rec = recs[-1]
    return {"engine_id": engine_id, "certified": bool(rec["passed"]), "record": rec}
