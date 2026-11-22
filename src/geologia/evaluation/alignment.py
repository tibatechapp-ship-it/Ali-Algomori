"""GeoBench-style external alignment — closing the internal-only-measurement gap.

Closes P0 gap #2 ("measurement is internal-only") in
docs/benchmark/STRATEGIC_LEADERSHIP_PLAN.md, whose gate is "a published
alignment report in docs/benchmark/ with the run fingerprint — the announced
result even if we lose rows".

Honesty invariants (tested in tests/test_alignment.py):
- The external facts are FROZEN in data/evaluation/external_alignment_v1.json,
  fingerprint-locked exactly like the golden eval (one canonical sha256 over
  the document minus its fingerprint field). Every number carries its source
  URL and access date, and the composition sentence is quoted verbatim from
  the upstream README so transcription drift is testable.
- We redistribute ZERO exam questions. The upstream dataset is Apache-2.0,
  but alignment is structural + measured-internal only: our platform has no
  generative MCQ track (ADR-0002), so no run against their questions is
  performed and no score is claimed — announcing what we did NOT run is part
  of the honesty contract.
- Every comparability row carries an explicit classification:
  comparable / partially_comparable / not_comparable / ours_unique /
  external_leads. The two rows where the external benchmark leads us
  (evaluation scale, source diversity) are declared in the frozen file, not
  buried in prose.
- The measured internal numbers come from the SAME deterministic audit the
  CI runs (run_audit over the fingerprint-verified golden set). No number in
  this report is an LLM accuracy score; the refusal gate is engineering
  integrity, never geological truth (fixed rule 2).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from geologia.evaluation.audit import (
    load_golden_eval,
    run_audit,
    sha256_of,
)

ALIGNMENT_VERSION = "1.0.0"
ALIGNMENT_SCHEMA = "geologia.alignment-report.v1"
EXTERNAL_ALIGNMENT_PATH = (
    Path(__file__).parent.parent / "data" / "evaluation"
    / "external_alignment_v1.json"
)
CLASSIFICATIONS = (
    "comparable",
    "partially_comparable",
    "not_comparable",
    "ours_unique",
    "external_leads",
)

TRUTH_NOTE_AR = (
    "تصنيف الحقيقة: هذا التقرير محاذاة منهجية وبنيوية وأرقام داخلية مقاسة — "
    "لا يعلن أي درجة دقة نموذج لغوي أمام GeoBench، ولا يمثل صحة جيولوجية "
    "أبداً (الثابت 2)."
)
TRUTH_NOTE_EN = (
    "Truth class: this report is methodological and structural alignment plus "
    "measured internal numbers — it announces no LLM accuracy score against "
    "GeoBench and never represents geological truth (fixed rule 2)."
)
LIMIT_NOTE_AR = (
    "الحد الصادق: لم نشغّل أسئلة GeoBench على منصتنا — لا مسار توليدي MCQ "
    "عندنا (ADR-0002) ولا إعادة توزيع للأسئلة؛ وصفّا الحجم وتنوع المصادر "
    "يُعلنان تقدّم المعيار الخارجي بصدق لا بورْي."
)
LIMIT_NOTE_EN = (
    "Honest limit: we did NOT run GeoBench questions on our platform — no "
    "generative MCQ track (ADR-0002) and no question redistribution; the "
    "scale and source-diversity rows announce the external benchmark's lead "
    "honestly, not rhetorically."
)


def load_external_alignment(path: Optional[Path] = None) -> dict:
    """Load the frozen external-alignment facts and verify the fingerprint.

    Raises a loud ValueError on any modification — regenerate via the
    documented procedure (scripts/make_alignment_data.py), never edit
    silently.
    """
    src = Path(path) if path else EXTERNAL_ALIGNMENT_PATH
    document = json.loads(src.read_text(encoding="utf-8"))
    without_fp = {k: v for k, v in document.items()
                  if k != "fingerprint_sha256"}
    actual = sha256_of(without_fp)
    expected = document.get("fingerprint_sha256")
    if actual != expected:
        raise ValueError(
            "external-alignment fingerprint mismatch: the frozen alignment "
            f"facts were modified (expected {expected}, computed {actual}) — "
            "regenerate via the documented procedure, never edit silently."
        )
    return document


def _classification_counts(rows: list) -> dict:
    counts: dict = {}
    for row in rows:
        cls = row["classification"]
        counts[cls] = counts.get(cls, 0) + 1
    return counts


def build_alignment_report(split: str = "both") -> dict:
    """Build the alignment report: frozen external facts + measured internal
    numbers from the same deterministic audit the CI runs."""
    if split not in ("both", "dev", "heldout"):
        raise ValueError(f"unknown split: {split!r}")
    ext = load_external_alignment()
    golden = load_golden_eval()
    audit = run_audit(split=split)

    rows = ext["comparability_rows"]
    for row in rows:  # structural guard: classifications stay honest
        if row["classification"] not in CLASSIFICATIONS:
            raise AssertionError(
                f"unknown classification {row['classification']!r} "
                f"in row {row['id']!r}")

    comp = ext["external_benchmark"]["composition"]
    internal_total = (
        len(golden["items"])
        + len(golden["negative_unanswerable"])
        + len(golden["negative_fake_references"])
    )
    if comp["external_total_items"] != (
        comp["objective_total"] + comp["subjective_npee_total"]
    ):  # structural guard on the frozen numbers themselves
        raise AssertionError("external composition arithmetic inconsistent")

    return {
        "schema": ALIGNMENT_SCHEMA,
        "alignment_version": ALIGNMENT_VERSION,
        "generated_from": (
            "external_alignment_v1.json (fingerprint-verified) + "
            "golden_eval_v1.json (fingerprint-verified) + run_audit"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "external_benchmark": {
            "name": ext["external_benchmark"]["name"],
            "introduced_in_paper": ext["external_benchmark"]["introduced_in_paper"],
            "composition": comp,
            "sources": ext["external_benchmark"]["sources"],
            "questions_copied": ext["external_benchmark"][
                "redistribution_posture"]["questions_copied"],
        },
        "internal_set": {
            "golden_questions": len(golden["items"]),
            "negative_unanswerable": len(golden["negative_unanswerable"]),
            "negative_fake_references": len(golden["negative_fake_references"]),
            "internal_total_items": internal_total,
            "fingerprint_sha256": golden["fingerprint_sha256"],
            "blocked_split_sha256": golden["blocked_split_sha256"],
        },
        "measured_audit": {
            "split": audit["split"],
            "counts": audit["counts"],
            "refusal_correctness_rate": audit["metrics"][
                "refusal_correctness_rate"]["value"],
            "citation_validity_rate": audit["metrics"][
                "citation_validity_rate"]["value"],
        },
        "scale_comparison": {
            "external_total_items": comp["external_total_items"],
            "internal_total_items": internal_total,
            "external_leads_ratio": round(
                comp["external_total_items"] / internal_total, 1),
        },
        "domain_mapping": ext["domain_mapping"],
        "unmapped_internal_domains": ext["unmapped_internal_domains"],
        "comparability_rows": rows,
        "classification_counts": _classification_counts(rows),
        "truth_class": {
            "classification": "documented",
            "note_ar": TRUTH_NOTE_AR,
            "note_en": TRUTH_NOTE_EN,
        },
        "limits_ar": LIMIT_NOTE_AR,
        "limits_en": LIMIT_NOTE_EN,
    }


def _print_report(report: dict) -> None:
    e = report["external_benchmark"]
    i = report["internal_set"]
    m = report["measured_audit"]
    s = report["scale_comparison"]
    print(f"GEOLOGIA external alignment v{report['alignment_version']} "
          f"— external={e['name']} — internal split={m['split']}")
    print(f"external composition: objective={e['composition']['objective_total']} "
          f"subjective={e['composition']['subjective_npee_total']} "
          f"total={e['composition']['external_total_items']} "
          f"(questions copied: {e['questions_copied']})")
    print(f"internal set: {i['internal_total_items']} items "
          f"(golden={i['golden_questions']}, "
          f"unanswerable={i['negative_unanswerable']}, "
          f"fake_refs={i['negative_fake_references']})")
    print(f"scale: external leads {s['external_leads_ratio']}x "
          f"({s['external_total_items']} vs {s['internal_total_items']})")
    print(f"measured: refusal={m['refusal_correctness_rate']} "
          f"(gated 1.0) citation_rate={m['citation_validity_rate']}")
    print("comparability rows:")
    for row in report["comparability_rows"]:
        print(f"  {row['id']:<32} {row['classification']}")
    print("classification counts:", report["classification_counts"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m geologia.evaluation.alignment",
        description=(
            "GeoBench-style external alignment report over the frozen "
            "golden set (measured internal numbers, honest comparability)."
        ),
    )
    parser.add_argument("--split", choices=("both", "dev", "heldout"),
                        default="both", help="which golden split to audit")
    parser.add_argument("--json", action="store_true",
                        help="print the raw JSON report")
    args = parser.parse_args(argv)
    try:
        report = build_alignment_report(split=args.split)
    except ValueError as exc:
        print(f"FINGERPRINT FAILURE: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    refusal = report["measured_audit"]["refusal_correctness_rate"]
    return 0 if refusal == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
