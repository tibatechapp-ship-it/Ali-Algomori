"""T4.2 — the agent-level vertical refusal rule, fully coded and tested."""
import hashlib
import json
import struct
from pathlib import Path

import pytest

from geologia.data_layer.vertical_rule import (
    VERT_GRID_FILE_MISSING,
    VERT_OUT_OF_DOMAIN,
    VERT_REF_UNAVAILABLE,
    VERT_REF_UNVERIFIED,
    answer_vertical,
)


def _gtx(path: Path) -> str:
    data = struct.pack(">4d2i", 0.0, 0.0, 10.0, 10.0, 3, 3)
    data += struct.pack(">9f", 1, 2, 3, 4, 5, 6, 7, 8, 9)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _registry(path: Path, sha: str, *, check="passed: max |ours - PROJ| = "
              "0.000000 m over 9 interior points", complete=True) -> Path:
    gates = {
        "sha256": sha,
        "license": {"status": "public_domain", "source": "test"},
        "tide_system": {"value": "tide_free", "evidence": "test"},
        "grid_coords": {"south": 0.0, "west": 0.0, "north": 10.0,
                        "east": 10.0, "resolution_deg": 5.0,
                        "nlat": 3, "nlon": 3},
        "interpolation": "bilinear (declared)",
        "crs_pair": {"horizontal": "EPSG:4326 (WGS 84)",
                     "vertical": "EPSG:5773"},
        "validity_domain": {"lat": [0.0, 10.0], "lon": [0.0, 10.0],
                            "undulation_m": [1.0, 9.0]},
        "independent_check": check,
    }
    if not complete:
        del gates["license"]
    doc = {"schema": "geologia-geoid-grid-registry/1",
           "grids": [{"status": "recorded", "model_id": "TEST96",
                      "file_name": "test.gtx", "gates": gates}]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _fixture(tmp_path, **kw):
    gdir = tmp_path / "grids"
    gdir.mkdir()
    sha = _gtx(gdir / "test.gtx")
    rp = _registry(tmp_path / "reg.json", sha, **kw)
    return rp, gdir


def test_no_registry_refusal(tmp_path):
    res = answer_vertical(5.0, 5.0, "TEST96",
                          registry_path_arg=str(tmp_path / "none.json"))
    assert res["status"] == 409
    assert res["error"] == VERT_REF_UNAVAILABLE
    assert res["message_ar"] and res["message_en"]


def test_incomplete_gates_refusal(tmp_path):
    rp, gdir = _fixture(tmp_path, complete=False)
    res = answer_vertical(5.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 409
    assert res["error"] == VERT_REF_UNAVAILABLE
    assert any("license" in m for m in res["missing"])


def test_unverified_grid_refusal(tmp_path):
    """Loaded is not enough: without a passed independent crosscheck the
    rule refuses — honest posture beats useful-looking nonsense."""
    rp, gdir = _fixture(tmp_path, check="pending")
    res = answer_vertical(5.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 409
    assert res["error"] == VERT_REF_UNVERIFIED


def test_grid_file_missing_refusal(tmp_path):
    rp, gdir = _fixture(tmp_path)
    (gdir / "test.gtx").unlink()
    res = answer_vertical(5.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 409
    assert res["error"] == VERT_GRID_FILE_MISSING


def test_fingerprint_change_refuses_silently_nothing(tmp_path):
    """If the grid bytes on disk stop matching the pinned fingerprint, the
    rule refuses — it never silently re-trusts a changed file."""
    rp, gdir = _fixture(tmp_path)
    data = (gdir / "test.gtx").read_bytes()
    (gdir / "test.gtx").write_bytes(data[:-1] + b"\x01")
    res = answer_vertical(5.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 409
    assert res["error"] == VERT_REF_UNAVAILABLE
    assert any("fingerprint changed" in m for m in res["missing"])


def test_out_of_domain_refusal(tmp_path):
    rp, gdir = _fixture(tmp_path)
    res = answer_vertical(50.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 409
    assert res["error"] == VERT_OUT_OF_DOMAIN
    assert "validity_domain" in res


def test_answer_inside_domain_returns_pinned_value(tmp_path):
    rp, gdir = _fixture(tmp_path)
    res = answer_vertical(5.0, 5.0, "TEST96", registry_path_arg=str(rp),
                          grid_dir=str(gdir))
    assert res["status"] == 200
    assert res["undulation_m"] == pytest.approx(5.0)
    assert res["grid_sha256"] and res["independent_check"].startswith("passed")
    interior = answer_vertical(7.5, 2.5, "TEST96",
                               registry_path_arg=str(rp), grid_dir=str(gdir))
    assert interior["status"] == 200
    assert interior["undulation_m"] == pytest.approx(3.0)


def test_api_endpoint_409_shape():
    """The API exposes the rule verbatim: 409 + coded reason (no registry
    dir configured by default => file-missing refusal, never a number)."""
    from fastapi.testclient import TestClient
    from geologia.api import app

    client = TestClient(app)
    res = client.get("/api/v1/vertical/answer", params={"lat": 5, "lon": 5})
    assert res.status_code in (409, 200)
    if res.status_code == 409:
        body = res.json()["detail"]
        assert body["error"] in (VERT_GRID_FILE_MISSING, VERT_REF_UNAVAILABLE,
                                 VERT_REF_UNVERIFIED)
        assert "message_ar" in body and "message_en" in body
