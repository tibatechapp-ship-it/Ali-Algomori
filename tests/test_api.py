from fastapi.testclient import TestClient

from geologia.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engines_integrated"] == 0


def test_registry_honesty_gate():
    r = client.get("/api/v1/engines")
    assert r.status_code == 200
    engines = r.json()["engines"]
    assert len(engines) == 30
    for e in engines:
        assert e["status"] == "planned"
        assert e["license_status"] == "unverified"


def test_engine_detail_and_404():
    r = client.get("/api/v1/engines/gempy")
    assert r.status_code == 200
    assert r.json()["domain"] == "geology3d"
    assert client.get("/api/v1/engines/not-real").status_code == 404


def test_plan_groundwater_arabic():
    payload = {"request": "ادرس احتمالية المياه الجوفية حول هذه الإحداثيات"}
    r = client.post("/api/v1/plans", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["plan_only"] is True
    assert body["no_results_computed"] is True
    assert "hydrology" in body["matched_domains"]
    assert "modflow6" in body["steps"][0]["candidate_engines"]
    assert body["disclaimer"]


def test_plan_validation():
    assert client.post("/api/v1/plans", json={"request": "x"}).status_code == 422
    bad_lang = {"request": "حلل المنطقة", "language": "fr"}
    assert client.post("/api/v1/plans", json=bad_lang).status_code == 422
    bad_bbox = {"request": "حلل المنطقة", "bbox": [1.0, 2.0]}
    assert client.post("/api/v1/plans", json=bad_bbox).status_code == 422
