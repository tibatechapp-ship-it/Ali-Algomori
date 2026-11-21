"""Evidence-model tests: the honesty contract must be mechanically enforced.

The binding rule: the layer must prove what it read, what it verified, and
what it cannot confirm. A report that claims "verified" without naming the
check, or "unverifiable" without a reason, is a bug — these tests make the
bug class impossible.
"""
from pathlib import Path

import pytest

from geologia.data_layer.evidence import (compile_evidence, ev_read,
                                          ev_unverifiable, ev_verified,
                                          prove_file)

DATA = Path(__file__).parent / "data"
REF = DATA / "reference"


# --- shape enforcement ---------------------------------------------------------
def test_verified_claim_without_named_check_is_rejected():
    with pytest.raises(ValueError, match="without named check"):
        compile_evidence([{"code": "X", "level": "verified",
                           "detail": "looks fine"}])


def test_unverifiable_claim_without_reason_is_rejected():
    with pytest.raises(ValueError, match="without reason"):
        compile_evidence([{"code": "Y", "level": "unverifiable",
                           "detail": "probably fine"}])


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="malformed"):
        compile_evidence([{"code": "Z", "level": "assumed", "detail": "..."}])


def test_empty_detail_is_rejected():
    with pytest.raises(ValueError):
        compile_evidence([{"code": "W", "level": "read", "detail": ""}])


def test_compile_buckets_and_counts():
    out = compile_evidence([
        ev_read("A", "read something"),
        ev_verified("B", "checked something", check="recomputation"),
        ev_unverifiable("C", "cannot check", reason="engine absent"),
    ])
    assert out["counts"] == {"read": 1, "verified": 1, "unverifiable": 1}
    assert out["verified"][0]["check"] == "recomputation"
    assert out["unverifiable"][0]["reason"] == "engine absent"


def test_compiled_evidence_can_be_recompiled():
    out = compile_evidence([ev_read("A", "x")])
    again = compile_evidence(out["read"])
    assert again["counts"]["read"] == 1


# --- prove_file verdicts --------------------------------------------------------
def test_prove_file_refuses_failing_file():
    rep = prove_file(str(DATA / "golden_las_truncated.las"), "las")
    assert rep["status"] == "fail"
    assert rep["proof_status"] == "refused"


def test_prove_file_reports_gaps_for_undeclared_crs():
    rep = prove_file(str(DATA / "golden_wells.csv"), "csv")
    assert rep["status"] == "pass"
    unv = {i["code"] for i in rep["evidence"]["unverifiable"]}
    assert "CRS_NONE_DECLARED" in unv
    assert rep["proof_status"] == "proven_with_unverified_claims"


def test_prove_file_fully_proven_when_everything_is_checkable():
    rep = prove_file(str(DATA / "golden_csv_utm_valid.csv"), "csv",
                     declared_crs="EPSG:32638")
    assert rep["status"] == "pass"
    assert rep["proof_status"] == "proven"
    verified = {i["code"] for i in rep["evidence"]["verified"]}
    assert "CRS_DECLARED_OK" in verified
    assert rep["evidence"]["counts"]["unverifiable"] == 0


def test_prove_file_carries_file_identity_in_read_level():
    rep = prove_file(str(DATA / "golden_wells.csv"), "csv")
    read_codes = {i["code"] for i in rep["evidence"]["read"]}
    assert "FILE_SHA256" in read_codes and "FILE_SIZE" in read_codes


def test_prove_file_appends_to_provenance(tmp_path):
    from geologia.data_layer.provenance import ProvenanceLog
    log = ProvenanceLog(str(tmp_path / "prov.jsonl"))
    rep = prove_file(str(DATA / "golden_wells.csv"), "csv", provenance=log)
    assert rep["proof_status"] == "proven_with_unverified_claims"
    recs = log.records()
    assert len(recs) == 1
    assert recs[0]["action"] == "prove_file"
    assert recs[0]["verdict"]["proof_status"] == "proven_with_unverified_claims"
    assert log.verify()["ok"] is True


def test_reader_absence_yields_gaps_not_false_proof(monkeypatch):
    from geologia.data_layer import readers as R
    empty = {"lasio": None, "tifffile": None, "pyproj": None,
             "numpy": None, "sqlite3": "3.0"}
    monkeypatch.setattr(R, "capabilities", lambda: empty)
    rep = prove_file(str(REF / "ref_las_valid.las"), "las")
    assert rep["proof_status"] == "proven_with_unverified_claims"
    unv = {i["code"] for i in rep["evidence"]["unverifiable"]}
    assert "READER_LIB_ABSENT" in unv
