"""External-alignment integrity tests (v0.18.0, P0 gap #2).

The GeoBench-style alignment must stay honest by construction:
- the frozen external facts file is fingerprint-locked exactly like the
  golden eval, and every published number carries a source URL;
- the composition arithmetic is internally consistent and matches the
  verbatim upstream quote (183 + 1,395 objective, 939 subjective, 50
  human-eval subset);
- ZERO exam questions are redistributed (clean-methodology posture);
- every comparability row carries an explicit classification, and the rows
  where the external benchmark leads us are declared, not buried;
- the measured internal numbers come from the same deterministic audit the
  CI runs, with the refusal gate at 1.0;
- the report carries the truth class and the honest limits;
- the new data asset is declared in the ADR-0010 attestation.
"""
import json

import pytest

from geologia import attestation
from geologia.evaluation.alignment import (
    CLASSIFICATIONS,
    EXTERNAL_ALIGNMENT_PATH,
    build_alignment_report,
    load_external_alignment,
)
from geologia.evaluation.audit import load_golden_eval


@pytest.fixture(scope="module")
def ext() -> dict:
    return load_external_alignment()  # fingerprint verification happens inside


@pytest.fixture(scope="module")
def golden() -> dict:
    return load_golden_eval()


@pytest.fixture(scope="module")
def report() -> dict:
    return build_alignment_report(split="both")


# -- frozen external facts -------------------------------------------------------
def test_external_file_fingerprint_locked():
    doc = json.loads(EXTERNAL_ALIGNMENT_PATH.read_text(encoding="utf-8"))
    from geologia.evaluation.audit import sha256_of

    without_fp = {k: v for k, v in doc.items() if k != "fingerprint_sha256"}
    assert sha256_of(without_fp) == doc["fingerprint_sha256"]


def test_tampered_external_file_fails_loudly(tmp_path):
    doc = json.loads(EXTERNAL_ALIGNMENT_PATH.read_text(encoding="utf-8"))
    doc["external_benchmark"]["composition"]["objective_npee_mcq"] = 999
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_external_alignment(path=path)


def test_external_facts_carry_sources_and_access_dates(ext):
    sources = ext["external_benchmark"]["sources"]
    assert len(sources) >= 4
    for s in sources:
        assert s["url"].startswith("https://")
        assert s["accessed"] == "2026-11-23"
    urls = {s["url"] for s in sources}
    assert "https://arxiv.org/abs/2306.05064" in urls
    assert "https://github.com/davendw49/k2" in urls
    assert "https://huggingface.co/datasets/daven3/geobench" in urls


def test_composition_matches_published_facts(ext):
    comp = ext["external_benchmark"]["composition"]
    assert comp["objective_npee_mcq"] == 183
    assert comp["objective_ap_test_mcq"] == 1395
    assert comp["objective_total"] == comp["objective_npee_mcq"] + \
        comp["objective_ap_test_mcq"] == 1578
    assert comp["subjective_npee_total"] == 939
    assert comp["subjective_human_eval_subset"] == 50
    assert comp["external_total_items"] == comp["objective_total"] + \
        comp["subjective_npee_total"] == 2517
    # the verbatim quote is the transcription guard: the digits of the
    # upstream sentence must contain our four frozen numbers
    quote = comp["verbatim_quote_en"]
    for n in ("183", "1,395", "939", "50"):
        assert n in quote


def test_zero_question_redistribution(ext):
    posture = ext["external_benchmark"]["redistribution_posture"]
    assert posture["questions_copied"] == 0
    assert "apache-2.0" in posture["dataset_license_en"]
    raw = EXTERNAL_ALIGNMENT_PATH.read_text(encoding="utf-8")
    # no exam-question text blocks: the only verbatim content is the quoted
    # upstream composition sentence, and it contains no question marks
    assert "?" not in ext["external_benchmark"]["composition"]["verbatim_quote_en"]
    assert raw.count("?") == 0


def test_domain_mapping_covers_both_directions(ext):
    mapped_internal = set()
    for row in ext["domain_mapping"]:
        assert row["coverage"] == "partial"
        mapped_internal.update(row["internal_domains"])
    # our nine analytical domains; the unmapped ones are declared, not hidden
    assert ext["unmapped_internal_domains"] == ["exploration", "geology3d"]
    assert set(ext["unmapped_internal_domains"]) & mapped_internal == set()


# -- comparability honesty --------------------------------------------------------
def test_comparability_rows_classified_and_honest(ext):
    rows = ext["comparability_rows"]
    assert len(rows) >= 10
    classes = set()
    for row in rows:
        assert row["classification"] in CLASSIFICATIONS
        assert row["reason_en"].strip()
        classes.add(row["classification"])
    assert classes == set(CLASSIFICATIONS)
    by_id = {row["id"]: row for row in rows}
    # the gate demands announcing rows where the external benchmark leads
    assert by_id["evaluation_scale"]["classification"] == "external_leads"
    assert by_id["question_source_diversity"]["classification"] == "external_leads"
    # and the tracks we refuse to fake are explicit
    assert by_id["objective_mcq_accuracy"]["classification"] == "not_comparable"
    assert by_id["subjective_human_eval"]["classification"] == "not_comparable"
    assert by_id["refusal_zero_hallucination"]["classification"] == "ours_unique"


# -- measured report ---------------------------------------------------------------
def test_report_measured_numbers_match_audit_and_golden(report, golden):
    i = report["internal_set"]
    assert i["golden_questions"] == len(golden["items"]) == 40
    assert i["negative_unanswerable"] == 10
    assert i["negative_fake_references"] == 5
    assert i["internal_total_items"] == 55
    assert i["fingerprint_sha256"] == golden["fingerprint_sha256"]
    m = report["measured_audit"]
    assert m["split"] == "both"
    # the zero-hallucination gate is measured by the same audit the CI runs
    assert m["refusal_correctness_rate"] == 1.0
    s = report["scale_comparison"]
    assert s["external_total_items"] == 2517
    assert s["internal_total_items"] == 55
    assert s["external_leads_ratio"] == round(2517 / 55, 1)


def test_report_truth_class_and_limits(report):
    tc = report["truth_class"]
    assert tc["classification"] == "documented"
    assert "الثابت 2" in tc["note_ar"]
    assert "geological truth" in tc["note_en"]
    assert "did NOT run" in report["limits_en"]
    assert report["external_benchmark"]["questions_copied"] == 0
    assert report["generated_from"].startswith("external_alignment_v1.json")


def test_alignment_asset_declared_in_attestation():
    assert "evaluation/external_alignment_v1.json" in attestation.EVIDENCE_ASSETS
    hashes = attestation.collect_asset_hashes()
    assert "evaluation/external_alignment_v1.json" in hashes
