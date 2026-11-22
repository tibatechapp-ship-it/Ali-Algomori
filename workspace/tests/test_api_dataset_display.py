"""Display-gate tests: validated, integrity-checked, reference-matched map payload.

The Phase-2 display gate: upload a real file -> detect/declare CRS -> display
matching a frozen reference. Golden WGS 84 literals below were computed with
pyproj 3.7.2 (PROJ 9.6.1) on 2026-11-23 at the listed UTM 38N inputs; the
display endpoint must reproduce them (pyproj path) and the pyproj-free UTM
fallback must reproduce them within the documented series tolerance.

Structural verification and reference matching never certify that real-world
coordinates are scientifically correct; they certify the serving pipeline.
"""
import sys

from fastapi.testclient import TestClient

from geologia_workspace import store
from geologia_workspace.api import app

client = TestClient(app)

# Frozen golden reference: (lon, lat) -> (easting_m, northing_m) in EPSG:32638,
# computed with pyproj 3.7.2 on 2026-11-23 (see test module docstring).
GOLDEN_UTM38N_INPUTS = {
    (44.2, 15.35): (414133.1015027688, 1697196.8389235127),
    (44.25, 15.4): (419519.25330974074, 1702708.4364362634),
    (44.15, 15.3): (408744.4018885594, 1691686.3892644697),
    (44.3, 15.3): (424849.0997213437, 1691628.9043210722),
    (44.3, 15.45): (424902.8488377534, 1708221.1929174222),
    (44.15, 15.45): (408809.6722406504, 1708279.1862629254),
}

PYPROJ_TOLERANCE_DEG = 1e-9
SERIES_TOLERANCE_DEG = 2e-6


def _project(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(tmp_path / "uploads"))
    return client.post("/api/v1/projects", json={"name": "Display project"}).json()


def _utm38n_featurecollection() -> bytes:
    def point(lon, lat):
        easting, northing = GOLDEN_UTM38N_INPUTS[(lon, lat)]
        return {
            "type": "Feature",
            "properties": {"site": f"{lon},{lat}"},
            "geometry": {
                "type": "Point",
                "coordinates": [round(easting, 4), round(northing, 4)],
            },
        }

    ring = [
        GOLDEN_UTM38N_INPUTS[(44.15, 15.3)][:2],
        GOLDEN_UTM38N_INPUTS[(44.3, 15.3)][:2],
        GOLDEN_UTM38N_INPUTS[(44.3, 15.45)][:2],
        GOLDEN_UTM38N_INPUTS[(44.15, 15.45)][:2],
        GOLDEN_UTM38N_INPUTS[(44.15, 15.3)][:2],
    ]
    payload = {
        "type": "FeatureCollection",
        "features": [
            point(44.2, 15.35),
            point(44.25, 15.4),
            {
                "type": "Feature",
                "properties": {"kind": "aoi"},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            },
        ],
    }
    import json

    return json.dumps(payload).encode("utf-8")


def _upload_and_validate(tmp_path, monkeypatch, crs="EPSG:32638"):
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=_utm38n_featurecollection(),
        headers={
            "X-Dataset-Name": "Display input",
            "X-Filename": "sites-utm38n.geojson",
            "X-Data-Role": "data_layers",
            "X-CRS": crs,
        },
    )
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["id"]
    validated = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert validated.status_code == 200
    assert validated.json()["validation_status"] == "passed"
    return dataset_id


def test_display_refuses_before_structural_validation(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=_utm38n_featurecollection(),
        headers={
            "X-Dataset-Name": "Display input",
            "X-Filename": "sites-utm38n.geojson",
            "X-CRS": "EPSG:32638",
        },
    )
    dataset_id = uploaded.json()["id"]
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 409
    assert "display.refusal.not_validated" in refused.json()["detail"]


def test_display_refuses_after_failed_validation(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    # Structurally valid GeoJSON that violates the aoi_boundary schema profile
    # (points are not polygons), so validation fails while upload succeeds.
    body = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{},"geometry":{"type":"Point","coordinates":[44.2,15.35]}}]}'
    )
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=body,
        headers={
            "X-Dataset-Name": "Broken input",
            "X-Filename": "broken.geojson",
            "X-Data-Role": "aoi_boundary",
            "X-CRS": "EPSG:32638",
        },
    )
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["id"]
    report = client.post(f"/api/v1/datasets/{dataset_id}/validate").json()
    assert report["validation_status"] == "failed"
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 409
    assert "display.refusal.validation_failed" in refused.json()["detail"]


def test_display_refuses_on_integrity_mismatch(tmp_path, monkeypatch):
    dataset_id = _upload_and_validate(tmp_path, monkeypatch)
    content_path = store.get_dataset_content_path(dataset_id)
    with open(content_path, "wb") as handle:
        handle.write(b'{"type":"FeatureCollection","features":[]}')
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 409
    assert "display.refusal.integrity_mismatch" in refused.json()["detail"]


def test_display_refuses_vertical_crs(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=_utm38n_featurecollection(),
        headers={
            "X-Dataset-Name": "Vertical input",
            "X-Filename": "vertical.geojson",
            "X-CRS": "EPSG:3855",
        },
    )
    dataset_id = uploaded.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}/validate")
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 409
    assert "display.refusal.vertical_or_3d_crs" in refused.json()["detail"]


def test_display_refuses_non_geojson_format(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=b"well_id,water_level_m\nW-01,125.4\n",
        headers={
            "X-Dataset-Name": "CSV input",
            "X-Filename": "wells.csv",
            "X-Data-Role": "water_levels_timeseries",
        },
    )
    dataset_id = uploaded.json()["id"]
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 415


def test_display_matches_frozen_reference_after_reprojection(tmp_path, monkeypatch):
    dataset_id = _upload_and_validate(tmp_path, monkeypatch)
    served = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert served.status_code == 200
    payload = served.json()
    assert payload["truth_class"] == "verified_structural"
    assert payload["display_crs"] == "EPSG:4326"
    assert payload["declared_crs"] == "EPSG:32638"
    assert payload["reprojected"] is True
    assert payload["reprojection_engine"].startswith("pyproj")
    assert payload["feature_count"] == 3
    assert payload["validation"]["status"] == "passed"
    assert payload["validation"]["scientific_interpretation"] is False
    features = payload["geojson"]["features"]
    expected_points = [(44.2, 15.35), (44.25, 15.4)]
    served_points = [
        tuple(features[i]["geometry"]["coordinates"])
        for i in range(len(expected_points))
    ]
    for (lon, lat), (actual_lon, actual_lat) in zip(expected_points, served_points):
        assert abs(actual_lon - lon) < PYPROJ_TOLERANCE_DEG
        assert abs(actual_lat - lat) < PYPROJ_TOLERANCE_DEG
    ring = features[2]["geometry"]["coordinates"][0]
    expected_ring = [
        (44.15, 15.3),
        (44.3, 15.3),
        (44.3, 15.45),
        (44.15, 15.45),
        (44.15, 15.3),
    ]
    for (lon, lat), (actual_lon, actual_lat) in zip(expected_ring, ring):
        assert abs(actual_lon - lon) < PYPROJ_TOLERANCE_DEG
        assert abs(actual_lat - lat) < PYPROJ_TOLERANCE_DEG
    assert "not certify" in payload["classification_note"]
    reprojection = payload["reprojection"]
    assert reprojection["target_crs"] == "EPSG:4326"
    assert "no vertical datum conversion" in reprojection["vertical_coordinate_policy"]


def test_display_serves_native_4326_without_transform(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    body = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{},"geometry":{"type":"Point","coordinates":[44.2,15.35]}}]}'
    )
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=body,
        headers={
            "X-Dataset-Name": "Native input",
            "X-Filename": "native.geojson",
            "X-CRS": "EPSG:4326",
        },
    )
    dataset_id = uploaded.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}/validate")
    served = client.get(f"/api/v1/datasets/{dataset_id}/display").json()
    assert served["reprojected"] is False
    assert served["reprojection_engine"] == "native_epsg_4326_no_transform"
    assert served["reprojection"] is None
    assert served["geojson"]["features"][0]["geometry"]["coordinates"] == [44.2, 15.35]


def test_display_utm_fallback_matches_reference_without_pyproj(
    tmp_path, monkeypatch
):
    dataset_id = _upload_and_validate(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "pyproj", None)
    served = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert served.status_code == 200
    payload = served.json()
    assert payload["reprojected"] is True
    assert payload["reprojection_engine"] == "snyder_utm_equations_fallback"
    assert payload["reprojection"]["engine"].startswith("pyproj-free UTM fallback")
    assert len(payload["reprojection"]["reference_sha256"]) == 64
    features = payload["geojson"]["features"]
    served_points = [
        tuple(features[i]["geometry"]["coordinates"]) for i in range(2)
    ]
    for (lon, lat), (actual_lon, actual_lat) in zip(
        [(44.2, 15.35), (44.25, 15.4)], served_points
    ):
        assert abs(actual_lon - lon) < SERIES_TOLERANCE_DEG
        assert abs(actual_lat - lat) < SERIES_TOLERANCE_DEG
    ring = features[2]["geometry"]["coordinates"][0]
    for (lon, lat), (actual_lon, actual_lat) in zip(
        [
            (44.15, 15.3),
            (44.3, 15.3),
            (44.3, 15.45),
            (44.15, 15.45),
            (44.15, 15.3),
        ],
        ring,
    ):
        assert abs(actual_lon - lon) < SERIES_TOLERANCE_DEG
        assert abs(actual_lat - lat) < SERIES_TOLERANCE_DEG


def test_display_fallback_refuses_non_utm_crs_without_pyproj(
    tmp_path, monkeypatch
):
    project = _project(tmp_path, monkeypatch)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        content=_utm38n_featurecollection(),
        headers={
            "X-Dataset-Name": "Non-UTM input",
            "X-Filename": "sites.geojson",
            "X-CRS": "EPSG:20438",  # Hartebeesthoek / UTM 38S, not WGS 84
        },
    )
    dataset_id = uploaded.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}/validate")
    monkeypatch.setitem(sys.modules, "pyproj", None)
    refused = client.get(f"/api/v1/datasets/{dataset_id}/display")
    assert refused.status_code == 503
    assert "display.unavailable_without_pyproj" in refused.json()["detail"]
