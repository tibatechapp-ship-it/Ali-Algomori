"""Live HTTP interface tests: a REAL uvicorn server over real TCP.

The owner's binding order requires live-server interface tests (11 HTTP
tests). These spawn uvicorn as a subprocess on a random localhost port, wait
for /health, and exercise the API exactly like a real client — stdlib
urllib only, no in-process TestClient shortcuts.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("uvicorn", reason="live HTTP tests need uvicorn installed")

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    store = tmp_path_factory.mktemp("live-store")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = {**os.environ, "GEOLOGIA_DATA_DIR": str(store)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "geologia.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    up = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
                if r.status == 200:
                    up = True
                    break
        except Exception:
            time.sleep(0.2)
    if not up:
        proc.terminate()
        pytest.fail("live uvicorn server did not come up within 20s")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


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


# 1 -----------------------------------------------------------------------
def test_health_live(live_server):
    status, body = http_json(live_server, "/health", expect=200)
    assert body["status"] == "ok"
    assert body["service"] == "geologia"
    assert body["version"]
    assert body["acceptance_standard"]


# 2 -----------------------------------------------------------------------
def test_engines_registry_live(live_server):
    status, body = http_json(live_server, "/api/v1/engines", expect=200)
    third = [e for e in body["engines"] if e["family"] == "third_party"]
    first = [e for e in body["engines"] if e["family"] == "first_party"]
    assert len(third) == 30
    assert any(e["engine_id"] == "porosity_density_v1" for e in first)
    for e in third:
        assert e["status"] == "planned"
        assert e["license_status"] == "unverified"


# 3 -----------------------------------------------------------------------
def test_engine_detail_first_party_live(live_server):
    status, card = http_json(live_server, "/api/v1/engines/porosity_density_v1",
                             expect=200)
    assert card["family"] == "first_party"
    assert card["input_contract"]["dtype"] == "las"
    assert card["method_citations"]
    status, _ = http_json(live_server, "/api/v1/engines/not-real")
    assert status == 404


# 4 -----------------------------------------------------------------------
def test_domains_live(live_server):
    status, body = http_json(live_server, "/api/v1/domains", expect=200)
    assert body["count"] == 9
    assert "well_logs" in [d["domain"] for d in body["domains"]]


# 5 -----------------------------------------------------------------------
def test_plan_arabic_live(live_server):
    status, plan = http_json(live_server, "/api/v1/plans", method="POST",
                             payload={"request": "تحليل سجل LAS للبئر رقم 5"},
                             expect=200)
    assert plan["plan_only"] is True
    assert plan["no_results_computed"] is True
    assert plan["matched_domains"] == ["well_logs"]


# 6 -----------------------------------------------------------------------
def test_plan_unknown_422_live(live_server):
    status, body = http_json(live_server, "/api/v1/plans", method="POST",
                             payload={"request": "مرحبا"})
    assert status == 422
    assert body["detail"]["error"] == "unknown_domain"
    assert "gis" in body["detail"]["supported_domains"]


# 7 -----------------------------------------------------------------------
def test_knowledge_query_citation_live(live_server):
    status, body = http_json(live_server, "/api/v1/knowledge/query", method="POST",
                             payload={"query": "أين يبدأ علم الجيولوجيا في التاريخ؟"},
                             expect=200)
    assert body["status"] == "found"
    assert body["no_generated_content"] is True
    assert body["results"][0]["payload"]["citation"]
    status, body = http_json(live_server, "/api/v1/knowledge/query", method="POST",
                             payload={"query": "xxqq zzvv 12345"})
    assert body["status"] == "not_in_library"
    assert body["results"] == []


# 8 -----------------------------------------------------------------------
def test_dataset_register_validate_checksum_live(live_server):
    status, rec = http_json(live_server, "/api/v1/datasets", method="POST", payload={
        "name": "سجل بئر ذهبي حي", "path": str(DATA / "golden_las_valid.las"),
        "dtype": "las", "declared_crs": "local_depth",
    }, expect=200)
    assert rec["id"] == f"ds-{rec['sha256'][:12]}"
    status, val = http_json(live_server,
                            f"/api/v1/datasets/{rec['id']}/validate", method="POST",
                            expect=200)
    assert val["validation"]["status"] == "pass"
    status, chk = http_json(live_server,
                            f"/api/v1/datasets/{rec['id']}/verify-checksum",
                            method="POST", expect=200)
    assert chk["checksum_ok"] is True


# 9 -----------------------------------------------------------------------
def test_task_gated_409_live(live_server):
    status, rec = http_json(live_server, "/api/v1/datasets", method="POST", payload={
        "name": "آبار للحاجز", "path": str(DATA / "golden_wells.csv"),
        "dtype": "csv",
    }, expect=200)
    http_json(live_server, f"/api/v1/datasets/{rec['id']}/validate", method="POST",
              expect=200)
    status, task = http_json(live_server, "/api/v1/tasks", method="POST", payload={
        "title": "مهمة محرك غير معتمد", "engine_id": "pastas",
        "dataset_ids": [rec["id"]],
        "isolation": {"pinned_version": "1.0.0", "cpu": 1, "memory_mb": 256,
                      "timeout_seconds": 60},
    }, expect=200)
    http_json(live_server, f"/api/v1/tasks/{task['id']}/transition", method="POST",
              payload={"to_state": "inputs_validated"}, expect=200)
    status, body = http_json(live_server, f"/api/v1/tasks/{task['id']}/transition",
                             method="POST", payload={"to_state": "ready"})
    assert status == 409
    assert body["detail"]["error"] == "gate_refused"
    assert body["detail"]["gate"] == "engine_certification"


# 10 ----------------------------------------------------------------------
def test_certify_endpoint_live(live_server):
    # third-party: refused 409 with policy reasons
    status, body = http_json(live_server, "/api/v1/engines/gempy/certify",
                             method="POST")
    assert status == 409
    assert body["detail"]["error"] == "certification_refused"
    # first-party: certified via pinned reference test
    status, body = http_json(live_server,
                             "/api/v1/engines/porosity_density_v1/certify",
                             method="POST", expect=200)
    assert body["certified"] is True
    assert body["record"]["max_abs_error"] <= body["record"]["tolerance"]
    assert body["record"]["citations"]


# 11 ----------------------------------------------------------------------
def test_certified_execution_evidence_live(live_server):
    http_json(live_server, "/api/v1/engines/porosity_density_v1/certify",
              method="POST", expect=200)  # idempotent re-certification
    status, rec = http_json(live_server, "/api/v1/datasets", method="POST", payload={
        "name": "سجل للتنفيذ الحي", "path": str(DATA / "golden_las_valid.las"),
        "dtype": "las",
    }, expect=200)
    http_json(live_server, f"/api/v1/datasets/{rec['id']}/validate", method="POST",
              expect=200)
    status, task = http_json(live_server, "/api/v1/tasks", method="POST", payload={
        "title": "تنفيذ حي موثق", "engine_id": "porosity_density_v1",
        "dataset_ids": [rec["id"]],
        "isolation": {"pinned_version": "1.0.0", "cpu": 1, "memory_mb": 256,
                      "timeout_seconds": 60},
    }, expect=200)
    http_json(live_server, f"/api/v1/tasks/{task['id']}/transition", method="POST",
              payload={"to_state": "inputs_validated"}, expect=200)
    http_json(live_server, f"/api/v1/tasks/{task['id']}/transition", method="POST",
              payload={"to_state": "ready"}, expect=200)
    status, done = http_json(live_server, f"/api/v1/tasks/{task['id']}/execute",
                             method="POST", expect=200)
    assert done["state"] == "executed"
    status, report = http_json(live_server, f"/api/v1/tasks/{task['id']}/report",
                               expect=200)
    assert report["method"]["citations"]
    assert report["uncertainty"]["sigma_phi_vv"] > 0
    assert any(i["code"] == "NEGATIVE_POROSITY" for i in report["issues"])
    assert report["validity_limits_ar"]
    status, ver = http_json(live_server, f"/api/v1/tasks/{task['id']}/transition",
                            method="POST", payload={"to_state": "verified"},
                            expect=200)
    assert ver["state"] == "verified"
