"""API integration: CRS-from-content gates on display + crs-content-verify.

The display gate now tests a declared UTM zone for plausibility against the
actual content through bounded analysis workers: garbage under a UTM
declaration is a classified refusal (409 crs_content_mismatch), not a
silently wrong map. The dedicated verify endpoint returns the full
truth-classified envelope. Zone-number limits are carried on the verdicts
(a zone label is not falsifiable from easting/northing alone).
"""
import json

from fastapi.testclient import TestClient

from geologia_workspace.api import app

client = TestClient(app)


def _project(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(tmp_path / "uploads"))
    return client.post("/api/v1/projects", json={"name": "CRS verify"}).json()


def _utm38n_bytes() -> bytes:
    # Golden EPSG:32638 literals (pyproj 3.7.2; same frozen reference as the
    # display tests) — sites around Sana'a, zone 38.
    points = [
        (414133.1015027688, 1697196.8389235127),
        (419519.25330974074, 1702708.4364362634),
        (408744.4018885594, 1691686.3892644697),
    ]
    payload = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"site": str(i)},
         "geometry": {"type": "Point", "coordinates": [e, n]}}
        for i, (e, n) in enumerate(points)
    ]}
    return json.dumps(payload).encode("utf-8")


def _upload_and_validate(project, crs, content=None, name="sites.geojson"):
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=content if content is not None else _utm38n_bytes(),
        headers={
            "X-Dataset-Name": "CRS content input",
            "X-Filename": name,
            "X-Data-Role": "data_layers",
            "X-CRS": crs,
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["id"]
    validated = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert validated.status_code == 200
    return dataset_id


def test_display_refuses_degree_content_under_utm_declaration(
        tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    body = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [44.2, 15.35]}},
    ]}).encode("utf-8")
    dataset_id = _upload_and_validate(project, "EPSG:32638", content=body)
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 409
    assert "display.refusal.crs_content_mismatch" in refused.json()["detail"]
    assert "UTM_ZONE_CONTENT_MISMATCH" in refused.json()["detail"]


def test_display_accepts_self_consistent_utm_content(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    dataset_id = _upload_and_validate(project, "EPSG:32638")
    served = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert served.status_code == 200, served.text
    body = served.json()
    assert body["truth_class"] == "verified_structural"
    verification = body["crs_content_verification"]
    assert verification["verdict_code"] == "UTM_ZONE_CONTENT_VERIFIED"
    assert verification["truth_class"] == "verified_content"
    assert verification["declared_zone"] == 38
    assert verification["n_points_checked"] == 3


def test_display_skips_verification_when_no_positions(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    body = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": None},
    ]}).encode("utf-8")
    dataset_id = _upload_and_validate(project, "EPSG:32638", content=body)
    served = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert served.status_code == 200, served.text
    assert served.json()["crs_content_verification"] is None


def test_verify_endpoint_zone_content_verified(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    dataset_id = _upload_and_validate(project, "EPSG:32638")
    report = client.post(
        f"/api/v1/datasets/{dataset_id}/crs-content-verify")
    assert report.status_code == 200, report.text
    envelope = report.json()
    assert envelope["truth_class"] == "verified_content"
    assert envelope["executed_in"] == "analysis_worker"
    assert envelope["n_positions_sampled"] == 3
    assert envelope["content_detection"]["detected_class"] == \
        "utm_projected_metres"
    verdict = envelope["zone_verification"]
    assert verdict["verdict_code"] == "UTM_ZONE_CONTENT_VERIFIED"
    # the honest limit is carried on the verdict itself
    assert "not confirmable" in verdict["note_en"]
    assert "not confirmable" in envelope["classification_note"] or \
        "never certifies" in envelope["classification_note"]


def test_verify_endpoint_contradicted_envelope(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    body = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [44.2, 15.35]}},
    ]}).encode("utf-8")
    dataset_id = _upload_and_validate(project, "EPSG:32638", content=body)
    envelope = client.post(
        f"/api/v1/datasets/{dataset_id}/crs-content-verify").json()
    assert envelope["truth_class"] == "contradicted_declared"
    assert envelope["zone_verification"]["verdict_code"] == \
        "UTM_ZONE_CONTENT_MISMATCH"


def test_verify_endpoint_geographic_declared(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    body = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [44.2, 15.35]}},
    ]}).encode("utf-8")
    dataset_id = _upload_and_validate(project, "EPSG:4326", content=body)
    envelope = client.post(
        f"/api/v1/datasets/{dataset_id}/crs-content-verify").json()
    assert envelope["truth_class"] == "verified_content"
    assert envelope["zone_verification"] is None
    assert envelope["content_detection"]["detected_class"] == \
        "geographic_degrees"


def test_verify_endpoint_default_declaration_contradicted_by_utm_content(
        tmp_path, monkeypatch):
    """GeoJSON uploads without X-CRS default to EPSG:4326 (api-side
    default). UTM-magnitude content under that default is a contradiction
    the envelope must carry loudly."""
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=_utm38n_bytes(),
        headers={
            "X-Dataset-Name": "Undeclared CRS input",
            "X-Filename": "sites.geojson",
            "X-Data-Role": "data_layers",
        },
    )
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}/validate")
    envelope = client.post(
        f"/api/v1/datasets/{dataset_id}/crs-content-verify")
    assert envelope.status_code == 200
    data = envelope.json()
    assert data["declared_crs"] == "EPSG:4326"
    assert data["truth_class"] == "contradicted_declared"
    assert data["zone_verification"] is None
    assert data["content_detection"]["detected_class"] == \
        "utm_projected_metres"


def test_verify_endpoint_refuses_non_geojson(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    csv_body = (b"easting,northing\n"
                b"414133.1015,1697196.8389\n")
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=csv_body,
        headers={
            "X-Dataset-Name": "CSV input",
            "X-Filename": "sites.csv",
            "X-Data-Role": "data_layers",
            "X-CRS": "EPSG:32638",
        },
    )
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["id"]
    refused = client.post(
        f"/api/v1/datasets/{dataset_id}/crs-content-verify")
    assert refused.status_code == 415
