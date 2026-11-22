"""Evaluation integrity tests (T3.3's CI leg).

These tests are the zero-hallucination gate measured at claim level
(ADR-0002): the frozen golden set must stay fingerprint-locked, every
negative probe must be refused by the REAL KnowledgeBase, the heldout split
must stay hash-locked, the retrieval index must not index its own evaluation
or agent-card files, and the deterministic audit must honor the metric gates.
"""
import copy
import json

import pytest

from geologia.evaluation.audit import (
    GOLDEN_EVAL_PATH,
    canonical_bytes,
    load_golden_eval,
    run_audit,
    sha256_of,
    verify_fingerprint,
)
from geologia.knowledge.retrieval import KnowledgeBase
from geologia.normalize import normalize_text

ANALYTICAL_DOMAINS = {
    "exploration", "geochemistry", "geology3d", "geophysics", "gis",
    "hydrology", "remote_sensing", "seismology", "well_logs",
}
# Real doc_id namespaces observed in the KnowledgeBase (introspected once and
# pinned here): catalog entries, digest chunks, engine KB cards. Nothing else
# — in particular no "evaluation:" or "agent:" namespace may ever appear.
ALLOWED_DOC_ID_PREFIXES = {"cat", "digest", "engine"}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase()


@pytest.fixture(scope="module")
def golden() -> dict:
    return load_golden_eval()  # fingerprint verification happens inside


# -- fingerprints ---------------------------------------------------------------
def test_fingerprints_recompute():
    document = json.loads(GOLDEN_EVAL_PATH.read_text(encoding="utf-8"))
    without_fp = {k: v for k, v in document.items()
                  if k != "fingerprint_sha256"}
    assert sha256_of(without_fp) == document["fingerprint_sha256"]
    heldout = sorted(
        [i["qid"] for i in document["items"] if i["split"] == "heldout"]
        + [n["qid"] for n in document["negative_unanswerable"]]
        + [f["qid"] for f in document["negative_fake_references"]]
    )
    assert sha256_of(heldout) == document["blocked_split_sha256"]


def test_verify_fingerprint_detects_content_tampering(golden):
    tampered = copy.deepcopy(golden)
    tampered["items"][0]["qid"] = "ge-999"
    with pytest.raises(ValueError, match="never edit silently"):
        verify_fingerprint(tampered)


def test_verify_fingerprint_detects_split_tampering(golden):
    # Move a heldout item to dev, then re-stamp the content fingerprint so the
    # ONLY remaining mismatch is the blocked-split lock itself.
    tampered = copy.deepcopy(golden)
    heldout_idx = next(i for i, item in enumerate(tampered["items"])
                       if item["split"] == "heldout")
    tampered["items"][heldout_idx]["split"] = "dev"
    tampered["fingerprint_sha256"] = sha256_of(
        {k: v for k, v in tampered.items() if k != "fingerprint_sha256"})
    with pytest.raises(ValueError, match="blocked-split fingerprint mismatch"):
        verify_fingerprint(tampered)


# -- golden items shape -----------------------------------------------------------
def test_forty_unique_items_in_known_domains(golden):
    items = golden["items"]
    assert len(items) == 40
    qids = [i["qid"] for i in items]
    assert len(qids) == len(set(qids))
    assert all(i["qid"].startswith("ge-") for i in items)
    assert all(i["domain"] in ANALYTICAL_DOMAINS for i in items)
    assert all(i["expected_behavior"] in ("documented_retrieval",
                                          "conflict_reasoning")
               for i in items)
    assert all(i["split"] in ("dev", "heldout") for i in items)


def test_question_bilingual_mix(golden):
    items = golden["items"]
    with_ar = [i for i in items if i.get("question_ar")]
    with_en = [i for i in items if i.get("question_en")]
    assert len(with_ar) >= 15
    assert with_en, "at least some items carry English questions"


def test_expected_sources_resolve_to_real_indexed_docs(golden, kb):
    digest_base_ids = {d.doc_id.split("#", 1)[0].split(":", 1)[1]
                       for d in kb._index._docs
                       if d.payload["kind"] == "digest"}
    for item in golden["items"]:
        src = item["expected_source"]
        assert src["kind"] == "digest"
        assert src["id"] in digest_base_ids, item["qid"]


def test_required_terms_are_real_digest_vocabulary(golden, kb):
    text_by_base = {}
    for d in kb._index._docs:
        base = d.doc_id.split("#", 1)[0].split(":", 1)[1]
        text_by_base.setdefault(base, "")
        text_by_base[base] += " " + d.text
    for item in golden["items"]:
        terms = item["grader"]["required_terms"]
        assert len(terms) >= 2, item["qid"]
        digest_text = normalize_text(text_by_base[item["expected_source"]["id"]])
        for term in terms:
            assert normalize_text(term) in digest_text, (item["qid"], term)


def test_numeric_items_carry_tolerance(golden):
    numeric = [i for i in golden["items"] if "tolerance" in i]
    assert len(numeric) <= 2
    for item in numeric:
        tol = item["tolerance"]
        assert isinstance(tol["value"], (int, float))
        assert isinstance(tol["abs_tol"], (int, float)) and tol["abs_tol"] >= 0


# -- negatives: the zero-hallucination gate (ADR-0002) ----------------------------
def test_negative_counts(golden):
    assert len(golden["negative_unanswerable"]) == 10
    assert len(golden["negative_fake_references"]) == 5
    for group in (golden["negative_unanswerable"],
                  golden["negative_fake_references"]):
        assert all(n["split"] == "heldout" for n in group)
    for fake in golden["negative_fake_references"]:
        assert fake["expected"] == "no_generation_and_no_citation"
        assert fake["grader"]["forbidden_ids"]
        assert fake["fabricated_ref"].strip()


def test_unanswerable_probes_are_actually_refused(golden, kb):
    for probe in golden["negative_unanswerable"]:
        query = probe.get("question_ar") or probe["question_en"]
        res = kb.search(query)
        assert res["status"] == "not_in_library", probe["qid"]
        assert res["results"] == []
        assert "ليس في المكتبة" in res["message_ar"]


def test_fake_reference_probes_are_actually_refused(golden, kb):
    for probe in golden["negative_fake_references"]:
        query = probe.get("query_ar") or probe["query_en"]
        res = kb.search(query)
        assert res["status"] == "not_in_library", probe["qid"]
        # No forbidden id may appear anywhere if the index ever grows hits.
        forbidden = probe["grader"]["forbidden_ids"]
        for hit in res.get("results", []):
            for fid in forbidden:
                assert fid not in hit["payload"]["citation"], probe["qid"]


# -- blocked split lock -----------------------------------------------------------
def test_blocked_split_hash_lock(golden):
    heldout = sorted(
        [i["qid"] for i in golden["items"] if i["split"] == "heldout"]
        + [n["qid"] for n in golden["negative_unanswerable"]]
        + [f["qid"] for f in golden["negative_fake_references"]]
    )
    assert golden["blocked_split_sha256"] == sha256_of(heldout)
    assert canonical_bytes(heldout)  # deterministic canonical form exists


def test_split_policy_documented(golden):
    assert golden["schema"] == "geologia-golden-eval/1"
    assert golden["frozen"] == "2026-11-22"
    assert golden["split_policy_ar"].strip()
    assert golden["note_ar"].strip()


# -- index exclusion (the path check) ---------------------------------------------
def test_index_does_not_index_evaluation_or_agent_files(kb):
    doc_ids = [d.doc_id for d in kb._index._docs]
    for doc_id in doc_ids:
        prefix = doc_id.split(":", 1)[0]
        assert prefix in ALLOWED_DOC_ID_PREFIXES, doc_id
        assert "golden_eval" not in doc_id
        assert "agent-" not in doc_id
    for doc in kb._index._docs:
        assert "golden_eval" not in doc.text
        assert "golden-eval" not in doc.text
        assert "agent-card" not in doc.text


# -- deterministic audit run --------------------------------------------------------
def test_audit_dev_report_structure_and_gates(golden):
    report = run_audit(split="dev")
    assert report["generated_from"] == "golden_eval_v1.json + fingerprint verified"
    assert report["split"] == "dev"
    assert report["frozen"] == "2026-11-22"
    metrics = report["metrics"]
    expected_keys = {
        "citation_validity_rate", "evidence_traceability_rate",
        "refusal_correctness_rate", "fact_vs_hypothesis_rate",
        "duplication_detection_rate", "metadata_extraction_rate",
        "improvement_stability", "geoid_gate",
    }
    assert set(metrics) == expected_keys

    refusal = metrics["refusal_correctness_rate"]
    assert refusal["value"] == 1.0
    assert refusal["gated"] is True and refusal["target"] == 1.0

    citation = metrics["citation_validity_rate"]
    assert isinstance(citation["value"], float)
    assert 0.0 <= citation["value"] <= 1.0
    assert citation["target"] == 0.95
    assert citation["gated"] is False
    assert citation["value"] >= 0.95

    trace = metrics["evidence_traceability_rate"]
    assert isinstance(trace["value"], float)
    assert trace["target"] == 0.95 and trace["gated"] is False

    for key in ("fact_vs_hypothesis_rate", "duplication_detection_rate",
                "metadata_extraction_rate", "improvement_stability",
                "geoid_gate"):
        assert metrics[key]["value"] == "not_measurable_yet"
        assert metrics[key]["gated"] is False
        assert metrics[key]["note"].strip()

    counts = report["counts"]
    assert counts["golden_questions"] == counts["golden_dev"] == 27
    assert counts["unanswerable"] == 10 and counts["fake_references"] == 5
    assert counts["failed"] == 0 and not report["failures"]


def test_audit_heldout_split_consistent(golden):
    report = run_audit(split="heldout")
    counts = report["counts"]
    assert counts["golden_questions"] == counts["golden_heldout"]
    assert counts["golden_questions"] == sum(
        1 for i in golden["items"] if i["split"] == "heldout")
    assert report["metrics"]["refusal_correctness_rate"]["value"] == 1.0


def test_audit_rejects_unknown_split():
    with pytest.raises(ValueError):
        run_audit(split="everything")
