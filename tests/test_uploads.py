"""Library-level upload ingestion tests (no HTTP).

The upload gate is the bridge between the HTTP boundary (ADR-0007) and
everything proven in 0.5.0/0.6.0. These tests pin the contract: streaming
size cap, immutable content-addressed quarantine, security-verdict-first
ordering, no registration of rejected bytes, honest proof verdicts, and a
provenance record for EVERY verdict — including refusals.
"""
from pathlib import Path

import pytest

from geologia.data_layer import records as ds
from geologia.data_layer.provenance import ProvenanceLog
from geologia.data_layer.uploads import ingest_bytes, ingest_stream, uploads_dir

DATA = Path(__file__).parent / "data"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(tmp_path / "store"))
    return tmp_path / "store"


@pytest.fixture()
def prov(store):
    return ProvenanceLog()


def read(p):
    return Path(p).read_bytes()


# --- happy path -----------------------------------------------------------------
def test_valid_las_upload_is_quarantined_registered_proven(store, prov):
    payload = read(DATA / "golden_las_valid.las")
    res = ingest_bytes(payload, "بئر_تجريبي.las", declared_crs="local_depth",
                       provenance_log=prov)
    assert res["status"] in ("proven", "proven_with_unverified_claims")
    assert res["dataset_id"] == f"ds-{res['sha256'][:12]}"
    # raw quarantine is byte-identical: the raw upload is never modified
    assert read(res["quarantine_path"]) == payload
    assert res["stored_name"].endswith(".las")
    # dataset record carries the proof summary, honestly graded
    rec = ds.get_dataset(res["dataset_id"])
    assert rec["proof"]["proof_status"] == res["status"]
    assert rec["status"] == ("proven" if res["status"] == "proven"
                             else "proven_with_gaps")
    assert rec["validation"]["status"] == "pass"
    # every verdict entered the tamper-evident chain
    actions = [r["action"] for r in prov.records()]
    assert actions == ["upload_quarantined", "upload_registered",
                       "prove_file"] or set(actions) >= {
        "upload_quarantined", "prove_file"}
    assert prov.verify()["ok"] is True


def test_upload_without_declared_crs_keeps_gap_visible(store, prov):
    """A LAS upload carries NO geographic CRS by nature — the honest gap
    for a well log is the undeclared DEPTH datum (vertical trust boundary).
    The upload must surface it, never imply a datum was confirmed."""
    res = ingest_bytes(read(DATA / "golden_las_valid.las"), "well.las",
                       provenance_log=prov)
    assert res["status"] == "proven_with_unverified_claims"
    f_codes = [f["code"] for f in res["proof"]["findings"]]
    assert "VERT_DEPTH_DATUM_UNDECLARED" in f_codes  # silence is not certainty
    unv = {i["code"] for i in res["proof"]["evidence"]["unverifiable"]}
    assert len(unv) >= 1  # at least one concrete, reasoned gap is on record


def test_gpkg_upload_passes_reception_and_gets_proven(store, prov):
    """Regression: GeoPackages were rejected as SEC_UNKNOWN_MAGIC before the
    SQLite magic branch was added to sniff_content (v0.7.0)."""
    res = ingest_bytes(read(DATA / "reference" / "ref_gpkg_wells.gpkg"),
                       "wells.gpkg", provenance_log=prov)
    codes = [f["code"] for f in res["reception"]["findings"]]
    assert "SEC_UNKNOWN_MAGIC" not in codes
    assert res["status"] in ("proven", "proven_with_unverified_claims")
    assert res["proof"]["evidence"]["counts"]["read"] > 0


# --- security refusals -------------------------------------------------------------
def test_oversized_stream_is_refused_before_disk(store, prov, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_MAX_UPLOAD_BYTES", "64")
    before = sorted(p.name for p in uploads_dir().iterdir())
    res = ingest_stream((b"x" * 40, b"y" * 40), "too_big.las",
                        provenance_log=prov)
    assert res["status"] == "rejected"
    codes = [f["code"] for f in res["reception"]["findings"]]
    assert codes == ["SEC_TOO_LARGE"]
    assert res["dataset_id"] is None
    after = sorted(p.name for p in uploads_dir().iterdir())
    assert before == after  # nothing was quarantined
    assert [r["action"] for r in prov.records()] == ["upload_rejected"]
    assert prov.verify()["ok"] is True


def test_empty_upload_is_refused_and_never_quarantined(store, prov):
    res = ingest_bytes(b"", "empty.las", provenance_log=prov)
    assert res["status"] == "rejected"
    codes = [f["code"] for f in res["reception"]["findings"]]
    assert codes == ["SEC_EMPTY_FILE"]
    assert list(uploads_dir().iterdir()) == []


def test_empty_filename_is_refused(store, prov):
    res = ingest_bytes(b"data", "   ", provenance_log=prov)
    assert res["status"] == "rejected"
    assert res["review_reason"] == "empty filename"
    codes = [f["code"] for f in res["reception"]["findings"]]
    assert codes == ["SEC_NAME_REFUSED"]


def test_corrupt_las_gets_refused_verdict_never_usable(store, prov):
    """Security-clean but content-corrupt: registered, then honestly
    refused — the record can never pass a task gate."""
    from geologia.data_layer.records import dataset_is_validated_pass
    res = ingest_bytes(read(DATA / "golden_las_truncated.las"),
                       "truncated.las", provenance_log=prov)
    assert res["status"] == "refused"
    codes = [f["code"] for f in res["proof"]["findings"]
             if f["severity"] == "error"]
    assert "LAS_DATA_ROWS_MISMATCH" in codes
    rec = ds.get_dataset(res["dataset_id"])
    assert rec["status"] == "proof_refused"
    assert rec["validation"]["status"] == "fail"
    assert dataset_is_validated_pass(res["dataset_id"]) is False
    assert "prove_file" in [r["action"] for r in prov.records()]
    assert prov.verify()["ok"] is True


def test_path_traversal_and_bidi_names_are_sanitized(store, prov):
    evil = "\u202ewells\u200b.las"  # RLO + ZWSP: visual reordering attempt
    res = ingest_bytes(read(DATA / "golden_las_valid.las"), f"../{evil}",
                       provenance_log=prov)
    assert res["status"] in ("proven", "proven_with_unverified_claims")
    assert "/" not in res["stored_name"]
    assert ".." not in res["stored_name"]
    flags = [f["code"] for f in res["reception"]["findings"]]
    assert "SEC_NAME_SANITIZED" in flags
    # the declared client name is preserved verbatim in provenance —
    # sanitized in storage, honest in the audit trail
    quarantined = [r for r in prov.records()
                   if r["action"] == "upload_quarantined"][0]
    declared = [i for i in quarantined["inputs"]
                if i["name"] == "declared_name"][0]
    assert declared["value"] == f"../{evil}"


# --- archives: quarantine + review, never data --------------------------------------
def test_zip_archive_is_quarantined_but_never_registered(store, prov):
    res = ingest_bytes(read(DATA / "golden_archive_ok.zip"), "survey.zip",
                       provenance_log=prov)
    assert res["status"] == "needs_review"
    assert res["dataset_id"] is None
    assert Path(res["quarantine_path"]).exists()
    assert "ADR-0005" in res["review_reason"]
    assert ds.list_datasets() == []
    assert "upload_quarantined" in [r["action"] for r in prov.records()]


def test_malicious_archive_is_rejected(store, prov):
    res = ingest_bytes(read(DATA / "golden_archive_bomb.zip"), "bomb.zip",
                       provenance_log=prov)
    assert res["status"] == "rejected"
    codes = [f["code"] for f in res["reception"]["findings"]
             if f["severity"] == "error"]
    assert "SEC_ZIP_BOMB" in codes
    assert res["dataset_id"] is None


# --- idempotence & chain integrity ----------------------------------------------------
def test_same_bytes_uploaded_twice_map_to_one_dataset(store, prov):
    payload = read(DATA / "golden_las_valid.las")
    first = ingest_bytes(payload, "a.las", provenance_log=prov)
    second = ingest_bytes(payload, "a.las", provenance_log=prov)
    assert first["dataset_id"] == second["dataset_id"]
    # second registration is content-addressed: same id, and the record
    # notes the latest proof, not an accumulating lie
    assert ds.get_dataset(first["dataset_id"]) is not None
    assert prov.verify()["ok"] is True


def test_full_chain_verifies_after_mixed_verdicts(store, prov):
    ingest_bytes(read(DATA / "golden_las_valid.las"), "ok.las",
                 provenance_log=prov)
    ingest_bytes(read(DATA / "golden_las_truncated.las"), "bad.las",
                 provenance_log=prov)
    ingest_bytes(b"", "empty.las", provenance_log=prov)
    ingest_bytes(read(DATA / "golden_archive_ok.zip"), "pack.zip",
                 provenance_log=prov)
    v = prov.verify()
    assert v["ok"] is True, v["findings"]
    actions = {r["action"] for r in prov.records()}
    assert {"upload_quarantined", "upload_rejected", "upload_registered",
            "prove_file"} <= actions
