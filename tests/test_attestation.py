"""Reproducible attestation tests — the P1 "honesty fingerprint" product gate.

Gate (STRATEGIC_LEADERSHIP_PLAN.md, P1 row 4): one command, identical chain
fingerprint across two independent systems on the same repo state, and local
tamper detection against the committed reference — offline, no network, no
trust assumptions.
"""
import json
import shutil

import pytest

from geologia.attestation import (
    DATA_DIR,
    REFERENCE_PATH,
    build_chain_payload,
    chain_fingerprint,
    verify_attestation,
)
from geologia.evaluation.audit import sha256_of

EXPECTED_CHAIN_FP = (
    "8994ab873b1879bf0549ee81c9c6b3434a02c9980e584be7e0cbff18455c6c19"
)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "geologia-store"
    d.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(d))
    return d


@pytest.fixture()
def data_copy(tmp_path):
    dest = tmp_path / "data-copy"
    shutil.copytree(DATA_DIR, dest)
    return dest


def test_chain_fingerprint_deterministic_across_systems(data_copy):
    """Two independent trees with identical content → identical fingerprint."""
    a = chain_fingerprint()
    b = chain_fingerprint(data_copy)
    assert a == b
    assert len(a) == 64


def test_verify_passes_on_clean_tree(store):
    report = verify_attestation()
    assert report["status"] == "pass"
    assert report["mismatches"] == []
    assert report["chain_fingerprint_matches"] is True
    assert report["compared_assets"] >= 30
    assert report["truth_class"]["classification"] == "documented"
    assert "geological truth" in report["truth_class"]["note_en"]
    assert report["runtime_checks"]["engine_porosity_density_v1"][
        "excluded_from_fingerprint"] is True


def test_verify_detects_asset_tampering(data_copy, store):
    target = data_copy / "reference" / "reference_sources.json"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = verify_attestation(base_dir=data_copy, include_runtime_checks=False)
    assert report["status"] == "broken"
    kinds = {m["asset"]: m["kind"] for m in report["mismatches"]}
    assert kinds["reference/reference_sources.json"] == "tampered"
    assert report["chain_fingerprint_matches"] is False


def test_verify_detects_missing_and_undeclared_assets(data_copy, store):
    (data_copy / "knowledge" / "institutions.json").unlink()
    (data_copy / "agents" / "rogue_card.json").write_text("{}", encoding="utf-8")
    report = verify_attestation(base_dir=data_copy, include_runtime_checks=False)
    assert report["status"] == "broken"
    kinds = {m["asset"]: m["kind"] for m in report["mismatches"]}
    assert kinds["knowledge/institutions.json"] == "missing"
    assert kinds["agents/rogue_card.json"] == "undeclared"


def test_verify_detects_broken_golden_eval_fingerprints(data_copy, store):
    target = data_copy / "evaluation" / "golden_eval_v1.json"
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["fingerprint_sha256"] = "0" * 64  # pretend the frozen set was edited
    target.write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    report = verify_attestation(base_dir=data_copy, include_runtime_checks=False)
    assert report["status"] == "broken"
    kinds = {m["kind"] for m in report["mismatches"]}
    assert "internal_fingerprints" in kinds


def test_committed_reference_matches_current_tree(store):
    """Editing any evidence asset without regenerating breaks this test."""
    ref = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    payload = build_chain_payload()
    assert ref["chain_fingerprint_sha256"] == sha256_of(payload)
    assert ref["assets"] == payload["assets"]
    assert ref["golden_eval"] == payload["golden_eval"]


def test_reference_self_integrity_against_pinned_fingerprint(store):
    """The reference file itself is pinned in this test (release evidence)."""
    ref = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    assert ref["schema"] == "geologia.attestation.reference.v1"
    assert ref["chain_fingerprint_sha256"] == EXPECTED_CHAIN_FP


def test_cli_certify_without_engine_attests_the_chain(store, capsys):
    from geologia.cli import main
    assert main(["certify"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pass"
    assert report["schema"] == "geologia.attestation.report.v1"


def test_cli_certify_engine_still_works(store):
    from geologia.cli import main
    assert main(["certify", "porosity_density_v1"]) == 0
