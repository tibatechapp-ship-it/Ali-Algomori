"""API integration tests for the knowledge and data-verification endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from geologia.api import app

client = TestClient(app)
DATA = Path(__file__).parent / "data"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "geologia-store"
    d.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(d))
    return d


def test_knowledge_stats_endpoint():
    r = client.get("/api/v1/knowledge/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["retrieval_only"] is True
    assert body["engine_kb_cards"] == 30


def test_knowledge_catalog_endpoint():
    r = client.get("/api/v1/knowledge/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 60
    sample = body["entries"][0]
    for key in ("entry_id", "title_ar", "confidence", "origin_type"):
        assert key in sample


def test_knowledge_query_found_with_citation():
    payload = {"query": "أين يبدأ علم الجيولوجيا في التاريخ؟", "top_k": 3}
    r = client.post("/api/v1/knowledge/query", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "found"
    assert body["no_generated_content"] is True
    assert body["results"][0]["payload"]["citation"]


def test_knowledge_query_honest_miss():
    r = client.post("/api/v1/knowledge/query", json={"query": "xxqq zzvv 12345"})
    assert r.status_code == 200  # honest empty result, not fabricated
    body = r.json()
    assert body["status"] == "not_in_library"
    assert body["results"] == []


def test_knowledge_query_scope_validation():
    r = client.post("/api/v1/knowledge/query", json={"query": "anything", "scope": "bad"})
    assert r.status_code == 422


def test_dataset_register_validate_flow(store):
    payload = {
        "name": "سجل بئر ذهبي", "path": str(DATA / "golden_las_valid.las"),
        "dtype": "las", "declared_crs": "local_depth", "declared_units": "m; g/cm3",
    }
    r = client.post("/api/v1/datasets", json=payload)
    assert r.status_code == 200
    rec = r.json()
    assert rec["status"] == "registered"

    r = client.post(f"/api/v1/datasets/{rec['id']}/validate")
    assert r.status_code == 200
    body = r.json()
    assert body["validation"]["status"] == "pass"
    assert body["status"] == "validated_pass"

    r = client.post(f"/api/v1/datasets/{rec['id']}/verify-checksum")
    assert r.status_code == 200
    assert r.json()["checksum_ok"] is True


def test_dataset_register_missing_file_422(store):
    r = client.post("/api/v1/datasets", json={"name": "x", "path": "/no/such/file.csv"})
    assert r.status_code == 422


def test_dataset_list_and_detail(store):
    rec = client.post("/api/v1/datasets", json={
        "name": "geojson", "path": str(DATA / "golden.geojson"), "dtype": "geojson"
    }).json()
    r = client.get("/api/v1/datasets")
    assert r.json()["count"] >= 1
    r = client.get(f"/api/v1/datasets/{rec['id']}")
    assert r.status_code == 200
    assert client.get("/api/v1/datasets/ds-does-not-exist").status_code == 404


def test_task_create_and_gated_transition(store):
    rec = client.post("/api/v1/datasets", json={
        "name": "wells", "path": str(DATA / "golden_wells.csv"), "dtype": "csv"
    }).json()
    # The dataset must pass validation before the task can use it (gate).
    validated = client.post(f"/api/v1/datasets/{rec['id']}/validate").json()
    assert validated["status"] == "validated_pass"
    r = client.post("/api/v1/tasks", json={
        "title": "تحليل مناسيب آبار صنعاء", "engine_id": "pastas",
        "dataset_ids": [rec["id"]],
        "isolation": {"pinned_version": "1.0.0", "cpu": 2, "memory_mb": 2048,
                      "timeout_seconds": 300},
    })
    assert r.status_code == 200
    task = r.json()
    assert task["state"] == "planned"

    r = client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_state": "inputs_validated"})
    assert r.status_code == 200

    # The binding gate: no certified engine exists -> execution refused 409.
    r = client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_state": "ready"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "gate_refused"
    assert detail["gate"] == "engine_certification"


def test_task_create_with_unknown_engine_422(store):
    r = client.post("/api/v1/tasks", json={
        "title": "مهمة", "engine_id": "ghost", "dataset_ids": ["ds-1"]})
    assert r.status_code == 422


def test_health_reports_acceptance_standard():
    r = client.get("/health")
    body = r.json()
    assert body["engines_integrated"] == 0
    assert body["acceptance_standard"] == "digest_10_acceptance_standard.md"
