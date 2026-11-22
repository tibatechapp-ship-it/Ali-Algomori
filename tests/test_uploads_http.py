"""Live HTTP upload-boundary tests: the reception gate over real TCP.

These extend the live-server contract (test_http_live.py) to the upload
boundary (ADR-0007): real uvicorn subprocess, real TCP, stdlib urllib —
no in-process TestClient shortcuts. What must be proven over HTTP:

- the transport cap refuses oversized bodies with 413 BEFORE reading them;
- every verdict of the reception gate travels to the client as EVIDENCE
  (exact codes), never as an opaque error;
- GeoPackages pass reception (SQLite magic) and get a real proof verdict;
- archives are quarantined with needs_review — never registered as data;
- raw-body PUT semantics: application/octet-stream, filename in query.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("uvicorn", reason="live HTTP tests need uvicorn installed")

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).resolve().parents[1]


def _spawn_server(tmp_dir, extra_env=None):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = {**os.environ, "GEOLOGIA_DATA_DIR": str(tmp_dir), **(extra_env or {})}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "geologia.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
                if r.status == 200:
                    return base, proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    pytest.fail("live uvicorn server did not come up within 20s")


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    base, proc = _spawn_server(tmp_path_factory.mktemp("uploads-live"))
    yield base
    _stop(proc)


@pytest.fixture(scope="module")
def tiny_cap_server(tmp_path_factory):
    """Server with GEOLOGIA_MAX_UPLOAD_BYTES=2048 to prove the 413 path."""
    base, proc = _spawn_server(tmp_path_factory.mktemp("uploads-tiny"),
                               {"GEOLOGIA_MAX_UPLOAD_BYTES": "2048"})
    yield base
    _stop(proc)


@pytest.fixture(scope="module")
def gated_server(tmp_path_factory):
    """Server with GEOLOGIA_UPLOAD_CONCURRENCY=1: uploads fully serialize."""
    base, proc = _spawn_server(
        tmp_path_factory.mktemp("uploads-gated"),
        {"GEOLOGIA_UPLOAD_CONCURRENCY": "1"})
    yield base
    _stop(proc)


def http_json(base, path, method="GET", payload=None, expect=None):
    req = urllib.request.Request(base + path, method=method)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as r:
            status, body = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = json.loads(exc.read().decode("utf-8"))
    if expect is not None:
        assert status == expect, (status, body)
    return status, body


def http_upload(base, filename, raw, expect=None, extra_query=""):
    req = urllib.request.Request(
        f"{base}/api/v1/uploads?filename={urllib.parse.quote(filename)}"
        f"{extra_query}", method="POST", data=raw)
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status, body = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = json.loads(exc.read().decode("utf-8"))
    if expect is not None:
        assert status == expect, (status, body)
    return status, body


# 12 -------------------------------------------------------------------------
def test_upload_policy_live(live_server):
    status, pol = http_json(live_server, "/api/v1/uploads/policy", expect=200)
    assert pol["max_upload_bytes"] == 100 * (1 << 20)
    assert "octet-stream" in pol["body"]
    assert "GEOLOGIA_MAX_UPLOAD_BYTES" == pol["cap_env"]


# 13 -------------------------------------------------------------------------
def test_upload_valid_las_then_reproof_live(live_server):
    raw = (DATA / "golden_las_valid.las").read_bytes()
    status, res = http_upload(live_server, "بئر_حي.las", raw, expect=200)
    assert res["status"] in ("proven", "proven_with_unverified_claims")
    assert res["dataset_id"] == f"ds-{res['sha256'][:12]}"
    assert res["proof"]["evidence"]["counts"]["read"] > 0
    # dataset is now visible through the standard ledger endpoint
    status, listing = http_json(live_server, "/api/v1/datasets", expect=200)
    assert any(d["id"] == res["dataset_id"] for d in listing["datasets"])
    # re-proof on demand: fresh evidence + a new provenance record
    status, proof = http_json(
        live_server, f"/api/v1/datasets/{res['dataset_id']}/proof", expect=200)
    assert proof["proof_status"] == res["status"]
    assert proof["evidence"]["counts"] == res["proof"]["evidence"]["counts"]


# 14 -------------------------------------------------------------------------
def test_upload_corrupt_las_is_422_with_exact_codes_live(live_server):
    raw = (DATA / "golden_las_truncated.las").read_bytes()
    status, body = http_upload(live_server, "truncated.las", raw)
    assert status == 422
    assert body["detail"]["error"] == "upload_refused"
    assert body["detail"]["status"] == "refused"
    assert "LAS_DATA_ROWS_MISMATCH" in body["detail"]["codes"]
    # the refused record exists with an honest proof_refused status
    status, rec = http_json(live_server,
                            f"/api/v1/datasets/{body['detail']['dataset_id']}",
                            expect=200)
    assert rec["status"] == "proof_refused"


# 15 -------------------------------------------------------------------------
def test_upload_gpkg_passes_reception_live(live_server):
    """Regression for the SQLite-magic gap: GeoPackages used to be refused
    as SEC_UNKNOWN_MAGIC at reception."""
    raw = (DATA / "reference" / "ref_gpkg_wells.gpkg").read_bytes()
    status, res = http_upload(live_server, "wells.gpkg", raw, expect=200)
    codes = [f["code"] for f in res["reception"]["findings"]]
    assert "SEC_UNKNOWN_MAGIC" not in codes
    assert "SEC_MAGIC_MATCH" in codes
    assert res["status"] in ("proven", "proven_with_unverified_claims")


# 16 -------------------------------------------------------------------------
def test_upload_zip_archive_is_needs_review_never_data_live(live_server):
    raw = (DATA / "golden_archive_ok.zip").read_bytes()
    status, res = http_upload(live_server, "survey.zip", raw, expect=200)
    assert res["status"] == "needs_review"
    assert res["dataset_id"] is None
    assert "ADR-0005" in res["review_reason"]
    status, body = http_upload(live_server, "bomb.zip",
                               (DATA / "golden_archive_bomb.zip").read_bytes())
    assert status == 422
    assert "SEC_ZIP_BOMB" in body["detail"]["codes"]


# 17 -------------------------------------------------------------------------
def test_upload_empty_and_missing_filename_live(live_server):
    status, body = http_upload(live_server, "empty.las", b"")
    assert status == 422
    assert "SEC_EMPTY_FILE" in body["detail"]["codes"]
    # missing required query param -> FastAPI validation error
    req = urllib.request.Request(f"{live_server}/api/v1/uploads",
                                 method="POST", data=b"abc")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 422


# 18 -------------------------------------------------------------------------
def test_upload_declared_crs_recorded_not_verified_beyond_content(live_server):
    """A declaration is recorded as a declaration: the layer checks it
    against observed content, but never upgrades it into a confirmation
    the file did not carry."""
    raw = (DATA / "golden_csv_utm_valid.csv").read_bytes()
    q = "&declared_crs=EPSG%3A32638&declared_units=m"
    status, res = http_upload(live_server, "wells_utm.csv", raw,
                              expect=200, extra_query=q)
    assert res["status"] in ("proven", "proven_with_unverified_claims")
    f_codes = [f["code"] for f in res["proof"]["findings"]]
    assert "CRS_DECLARED_OK" in f_codes  # declared matches observed magnitudes


# 19 -------------------------------------------------------------------------
def test_upload_traversal_and_bidi_name_is_sanitized_live(live_server):
    raw = (DATA / "golden_wells.csv").read_bytes()  # unique bytes: fresh ds id
    evil = "../\u202eevil\u200b.csv"
    status, res = http_upload(live_server, evil, raw, expect=200)
    assert "/" not in res["stored_name"]
    assert ".." not in res["stored_name"]
    flags = [f["code"] for f in res["reception"]["findings"]]
    assert "SEC_NAME_SANITIZED" in flags
    assert res["stored_name"].endswith(".csv")
    # the sanitized name, not the hostile one, became the dataset name
    status, rec = http_json(live_server,
                            f"/api/v1/datasets/{res['dataset_id']}",
                            expect=200)
    assert rec["name"] == res["stored_name"]


# 20 -------------------------------------------------------------------------
def test_upload_oversize_413_before_reading_body_live(tiny_cap_server):
    raw = b"z" * 4096  # > 2048-byte cap
    status, body = http_upload(tiny_cap_server, "big.las", raw)
    assert status == 413
    assert body["detail"]["codes"] == ["SEC_TOO_LARGE"]
    assert "body not read" in body["detail"]["message"]
    status, listing = http_json(tiny_cap_server, "/api/v1/datasets",
                                expect=200)
    assert listing["datasets"] == []  # nothing registered, nothing quarantined


# 21 -------------------------------------------------------------------------
def test_upload_gate_limit_one_serves_sequentially(gated_server):
    """The concurrency gate (v0.15.1) at its hard minimum must not
    deadlock or leak: distinct valid uploads succeed one after the
    other, each fully processed under the serialized gate."""
    status, pol = http_json(gated_server, "/api/v1/uploads/policy",
                            expect=200)
    assert pol["concurrency_env"] == "GEOLOGIA_UPLOAD_CONCURRENCY"
    assert pol["max_concurrent_uploads"] == 1
    raw_las = (DATA / "golden_las_valid.las").read_bytes()
    status, first = http_upload(gated_server, "gate_1.las", raw_las,
                                expect=200)
    assert first["status"] in ("proven", "proven_with_unverified_claims")
    raw_csv = (DATA / "golden_wells.csv").read_bytes()
    status, second = http_upload(gated_server, "gate_2.csv", raw_csv,
                                 expect=200)
    assert second["status"] in ("proven", "proven_with_unverified_claims")
