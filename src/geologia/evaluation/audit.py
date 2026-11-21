"""Deterministic audit over the frozen golden evaluation set (T3.3).

Loads data/evaluation/golden_eval_v1.json (fingerprint-locked), runs every
item of the requested split through the real KnowledgeBase and applies
deterministic graders. No randomness, no wall-clock inside metrics (a UTC
timestamp lives only in the non-compared "generated_at" header field).

Grader contract (ADR-0002 retrieval-only honesty):
- documented_retrieval: PASS iff status=="found" AND the TOP hit's citation
  doc_id is one of expected_source.id / alt_doc_ids AND at least one
  required_term (normalized) occurs in the top hit's stored chunk text.
- conflict_reasoning: PASS iff the top-3 hits collectively cite ALL required
  docs (and at least one required term across their combined text).
- negative unanswerable / fake references: PASS iff status=="not_in_library"
  (fake refs additionally record any forbidden id appearing in results).
The refusal gate is split-independent: negatives run on every invocation.

Regeneration procedure (never edit the frozen file silently): rebuild the
evaluation object from the digest texts, recompute both sha256 fingerprints
over the canonical JSON (sort_keys=True, ensure_ascii=False, compact
separators), update the "frozen" date, and re-run this audit plus
tests/test_golden_eval.py before committing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from geologia.knowledge.retrieval import KnowledgeBase
from geologia.normalize import normalize_text

AUDIT_VERSION = "1.0.0"
GOLDEN_EVAL_PATH = (
    Path(__file__).parent.parent / "data" / "evaluation" / "golden_eval_v1.json"
)
CITATION_TARGET = 0.95

METRIC_KEYS = (
    "citation_validity_rate",
    "evidence_traceability_rate",
    "refusal_correctness_rate",
    "fact_vs_hypothesis_rate",
    "duplication_detection_rate",
    "metadata_extraction_rate",
    "improvement_stability",
    "geoid_gate",
)

_CITATION_ID = re.compile(r"\[([^\]]+)\]")


# -- fingerprints -------------------------------------------------------------
def canonical_bytes(obj) -> bytes:
    """Canonical JSON bytes used for every fingerprint in this package."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha256_of(obj) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def heldout_qids(document: dict) -> List[str]:
    """All heldout qids (golden items + negatives), sorted for the hash."""
    qids = [i["qid"] for i in document.get("items", [])
            if i.get("split") == "heldout"]
    qids += [n["qid"] for n in document.get("negative_unanswerable", [])
             if n.get("split") == "heldout"]
    qids += [f["qid"] for f in document.get("negative_fake_references", [])
             if f.get("split") == "heldout"]
    return sorted(qids)


def verify_fingerprint(document: dict) -> None:
    """Recompute both fingerprints; raise a loud ValueError on any mismatch.

    A mismatch means the frozen evaluation set was modified — regenerate via
    the documented procedure, never edit silently.
    """
    without_fp = {k: v for k, v in document.items()
                  if k != "fingerprint_sha256"}
    actual = sha256_of(without_fp)
    expected = document.get("fingerprint_sha256")
    if actual != expected:
        raise ValueError(
            "golden-eval fingerprint mismatch: the frozen evaluation set was "
            f"modified (expected {expected}, computed {actual}) — regenerate "
            "via the documented procedure, never edit silently."
        )
    actual_split = sha256_of(heldout_qids(document))
    expected_split = document.get("blocked_split_sha256")
    if actual_split != expected_split:
        raise ValueError(
            "blocked-split fingerprint mismatch: which items are heldout was "
            f"modified (expected {expected_split}, computed {actual_split}) — "
            "regenerate via the documented procedure, never edit silently."
        )


def load_golden_eval(path: Optional[Path] = None) -> dict:
    """Load the frozen golden eval set and verify both fingerprints."""
    src = Path(path) if path else GOLDEN_EVAL_PATH
    document = json.loads(src.read_text(encoding="utf-8"))
    verify_fingerprint(document)
    return document


# -- hit helpers ---------------------------------------------------------------
def _base_doc_id(doc_id: str) -> str:
    """digest:digest-04#p2 -> digest-digest-04 (strip chunk + kind prefix)."""
    base = doc_id.split("#", 1)[0]
    return base.split(":", 1)[1] if ":" in base else base


def _citation_doc_id(hit: dict) -> str:
    """The doc_id inside the citation string "... [doc_id]" of the hit."""
    match = _CITATION_ID.search(hit.get("payload", {}).get("citation", ""))
    return match.group(1) if match else hit.get("doc_id", "")


def _chunk_text_map(kb: KnowledgeBase) -> Dict[str, str]:
    """doc_id -> full stored chunk text (the excerpt returned to callers is a
    320-char truncation; the citation points at the full stored chunk)."""
    return {doc.doc_id: doc.text for doc in kb._index._docs}


def _hit_full_text(hit: dict, chunks: Dict[str, str]) -> str:
    doc_id = hit.get("doc_id", "")
    if doc_id in chunks:
        return chunks[doc_id]
    return hit.get("excerpt", "")


def _missing_terms(terms: List[str], text: str) -> List[str]:
    norm = normalize_text(text)
    return [t for t in terms if normalize_text(t) not in norm]


# -- graders --------------------------------------------------------------------
def _grade_documented(item: dict, kb: KnowledgeBase, chunks: Dict[str, str],
                      top_k: int) -> dict:
    query = item.get("question_ar") or item.get("question_en") or ""
    res = kb.search(query, top_k=top_k)
    expected_ids = [item["expected_source"]["id"]] + \
        list(item["grader"].get("alt_doc_ids", []))
    if res["status"] != "found":
        return {"passed": False, "actual_doc_id": None, "missing_terms": [],
                "reason": "honest miss: retrieval returned not_in_library"}
    top = res["results"][0]
    actual = _base_doc_id(_citation_doc_id(top))
    text = _hit_full_text(top, chunks)
    missing = _missing_terms(item["grader"]["required_terms"], text)
    doc_ok = actual in expected_ids
    terms_ok = len(missing) < len(item["grader"]["required_terms"])
    reason = None
    if not doc_ok:
        reason = f"top hit cites {actual!r}, expected one of {expected_ids}"
    elif not terms_ok:
        reason = "no required term present in top hit text"
    return {"passed": doc_ok and terms_ok, "actual_doc_id": actual,
            "missing_terms": missing, "reason": reason}


def _grade_conflict(item: dict, kb: KnowledgeBase, chunks: Dict[str, str],
                    top_k: int) -> dict:
    query = item.get("question_ar") or item.get("question_en") or ""
    res = kb.search(query, top_k=max(top_k, 3))
    required = [item["expected_source"]["id"]] + \
        list(item["grader"].get("alt_doc_ids", []))
    if res["status"] != "found":
        return {"passed": False, "actual_doc_ids": [], "missing_terms": [],
                "reason": "honest miss: retrieval returned not_in_library"}
    top_hits = res["results"][:3]
    cited = [_base_doc_id(_citation_doc_id(h)) for h in top_hits]
    missing_docs = [d for d in required if d not in cited]
    combined = " ".join(_hit_full_text(h, chunks) for h in top_hits)
    missing = _missing_terms(item["grader"]["required_terms"], combined)
    passed = not missing_docs and (
        not item["grader"]["required_terms"] or len(missing) <
        len(item["grader"]["required_terms"])
    )
    reason = None
    if missing_docs:
        reason = f"top-3 hits do not cite required docs {missing_docs}"
    elif missing and len(missing) == len(item["grader"]["required_terms"]):
        reason = "no required term present across top-3 hit texts"
    return {"passed": passed, "actual_doc_ids": cited,
            "missing_terms": missing, "reason": reason}


def _grade_negative(item: dict, kb: KnowledgeBase, top_k: int) -> dict:
    query = item.get("question_ar") or item.get("question_en") or ""
    res = kb.search(query, top_k=top_k)
    if res["status"] == "not_in_library":
        return {"passed": True, "actual_status": "not_in_library",
                "forbidden_found": False, "reason": None}
    forbidden = list(item.get("grader", {}).get("forbidden_ids", []))
    found_ids = [_citation_doc_id(h) for h in res.get("results", [])]
    hit_forbidden = [f for f in forbidden
                     if any(f in fid for fid in found_ids)]
    return {"passed": False, "actual_status": "found",
            "forbidden_found": bool(hit_forbidden),
            "found_doc_ids": found_ids,
            "reason": "retrieval answered instead of the honest refusal"}


# -- metrics -------------------------------------------------------------------
def _metric(value, target, gated: bool, note: str) -> dict:
    return {"value": value, "target": target, "gated": gated, "note": note}


def _rate(passed: int, total: int) -> Optional[float]:
    return round(passed / total, 4) if total else None


# -- audit ------------------------------------------------------------------------
def run_audit(split: str = "both", top_k: int = 5) -> dict:
    """Run the deterministic audit for split in {both, dev, heldout}."""
    if split not in ("both", "dev", "heldout"):
        raise ValueError(f"unknown split: {split!r}")
    document = load_golden_eval()
    kb = KnowledgeBase()
    chunks = _chunk_text_map(kb)

    golden = document["items"]
    golden_scope = golden if split == "both" else \
        [i for i in golden if i.get("split") == split]
    # The refusal gate is split-independent (ADR-0002): negatives always run.
    negatives = document["negative_unanswerable"]
    fakes = document["negative_fake_references"]

    failures: List[dict] = []
    documented = conflict = 0
    documented_pass = conflict_pass = 0
    for item in golden_scope:
        if item.get("expected_behavior") == "conflict_reasoning":
            conflict += 1
            outcome = _grade_conflict(item, kb, chunks, top_k)
            conflict_pass += outcome["passed"]
        else:
            documented += 1
            outcome = _grade_documented(item, kb, chunks, top_k)
            documented_pass += outcome["passed"]
        if not outcome["passed"]:
            failures.append({
                "qid": item["qid"], "item_type": "golden",
                "domain": item.get("domain"),
                "expected_behavior": item.get("expected_behavior"),
                "expected_doc_ids": [item["expected_source"]["id"]] +
                    list(item["grader"].get("alt_doc_ids", [])),
                **outcome,
            })

    neg_pass = 0
    for group, kind in ((negatives, "unanswerable"),
                        (fakes, "fake_reference")):
        for item in group:
            outcome = _grade_negative(item, kb, top_k)
            neg_pass += outcome["passed"]
            if not outcome["passed"]:
                failures.append({
                    "qid": item["qid"], "item_type": kind,
                    "expected": item.get("expected"),
                    "actual_status": outcome.get("actual_status"),
                    "forbidden_found": outcome.get("forbidden_found"),
                    "reason": outcome.get("reason"),
                })

    citation_rate = _rate(documented_pass, documented)
    refusal_rate = _rate(neg_pass, len(negatives) + len(fakes))
    counts = {
        "golden_questions": len(golden_scope),
        "golden_dev": sum(1 for i in golden_scope if i.get("split") == "dev"),
        "golden_heldout": sum(1 for i in golden_scope
                              if i.get("split") == "heldout"),
        "golden_documented_retrieval": documented,
        "golden_conflict_reasoning": conflict,
        "unanswerable": len(negatives),
        "fake_references": len(fakes),
        "passed": documented_pass + conflict_pass + neg_pass,
        "failed": len(failures),
        "kb_indexed_chunks": kb.stats()["indexed_chunks"],
    }

    metrics = {
        "citation_validity_rate": _metric(
            citation_rate, CITATION_TARGET, False,
            "documented_retrieval pass rate on the requested split; reported "
            "not gated in v1 — TF-IDF retrieval quality is measured, CI green "
            "does not certify geological validity"),
        "evidence_traceability_rate": _metric(
            citation_rate, CITATION_TARGET, False,
            "v1 proxy: same pass rate measured at golden-question level "
            "(top hit must cite the expected stored digest and carry a "
            "required evidence term); claim-level grading arrives with the "
            "evidence-store package"),
        "refusal_correctness_rate": _metric(
            refusal_rate, 1.0, True,
            "zero-hallucination gate (ADR-0002): unanswerable + fake-reference "
            "probes must be refused with not_in_library; MUST be 1.0; runs in "
            "every invocation regardless of split"),
        "fact_vs_hypothesis_rate": _metric(
            "not_measurable_yet", None, False,
            "claim-level fact/hypothesis classification needs the knowledge-"
            "unit evidence store (T1.2); no such pipeline exists in v1"),
        "duplication_detection_rate": _metric(
            "not_measurable_yet", None, False,
            "duplication detection over indexed chunks arrives with a later "
            "package; no pipeline in v1"),
        "metadata_extraction_rate": _metric(
            "not_measurable_yet", None, False,
            "metadata extraction benchmarks over LAS/GeoTIFF/CSV arrive with "
            "a later package; no pipeline in v1"),
        "improvement_stability": _metric(
            "not_measurable_yet", None, False,
            "v1 is the frozen baseline; stability needs a measured baseline "
            "plus a later change to compare against"),
        "geoid_gate": _metric(
            "not_measurable_yet", None, False,
            "vertical/geoid gate belongs to package T4; not measurable yet"),
    }
    missing_metrics = [k for k in METRIC_KEYS if k not in metrics]
    if missing_metrics:  # structural guard, never expected to fire
        raise AssertionError(f"metric table incomplete: {missing_metrics}")

    return {
        "audit_version": AUDIT_VERSION,
        "frozen": document["frozen"],
        "split": split,
        "counts": counts,
        "metrics": metrics,
        "failures": failures,
        "generated_from": "golden_eval_v1.json + fingerprint verified",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# -- readable output -------------------------------------------------------------
def _print_report(report: dict) -> None:
    c = report["counts"]
    print(f"GEOLOGIA golden-eval audit v{report['audit_version']} — "
          f"frozen {report['frozen']} — split={report['split']}")
    print(f"generated from: {report['generated_from']}")
    print(f"knowledge base: {c['kb_indexed_chunks']} indexed chunks")
    print(f"golden questions: {c['golden_questions']} "
          f"(dev={c['golden_dev']}, heldout={c['golden_heldout']}, "
          f"documented={c['golden_documented_retrieval']}, "
          f"conflict={c['golden_conflict_reasoning']})")
    print(f"negatives: unanswerable={c['unanswerable']}, "
          f"fake_references={c['fake_references']}")
    print(f"passed={c['passed']} failed={c['failed']}")
    print("metrics:")
    for key, m in report["metrics"].items():
        print(f"  {key:<28} value={m['value']} target={m['target']} "
              f"gated={m['gated']}")
        print(f"    {m['note']}")
    if report["failures"]:
        print("failures:")
        for f in report["failures"]:
            print(f"  {f['qid']} [{f['item_type']}]: {f.get('reason')}")
    else:
        print("failures: none")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m geologia.evaluation.audit",
        description="Deterministic audit over the frozen golden eval set.",
    )
    parser.add_argument("--split", choices=("both", "dev", "heldout"),
                        default="both", help="which golden items to audit")
    parser.add_argument("--json", action="store_true",
                        help="print the raw JSON report")
    args = parser.parse_args(argv)
    try:
        report = run_audit(split=args.split)
    except ValueError as exc:
        print(f"FINGERPRINT FAILURE: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    refusal = report["metrics"]["refusal_correctness_rate"]["value"]
    return 0 if refusal == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
