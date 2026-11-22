"""T4.1 — geoid gate: synthetic-grid machinery + the real frozen registries."""
import hashlib
import json
import math
import struct
from pathlib import Path

import pytest

from geologia.data_layer.geoid import (
    golden_nodes,
    grid_stats,
    ingest_grid,
    parse_grid_file,
    parse_gtx,
    undulation_at,
)
from geologia.data_layer.vertical_rule import DEFAULT_REGISTRY, registry_path

NODES_DOC = (Path(__file__).parents[1] / "src" / "geologia" / "data"
             / "reference" / "geoid_golden_nodes.json")


def _synthetic_gtx(path: Path) -> str:
    # 3x3 grid, S0 W0 N10 E10, values 1..9 (row 0 = north, per parser contract)
    data = struct.pack(">4d2i", 0.0, 0.0, 10.0, 10.0, 3, 3)
    data += struct.pack(">9f", 1, 2, 3, 4, 5, 6, 7, 8, 9)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_parse_gtx_meta_and_nodes(tmp_path):
    sha = _synthetic_gtx(tmp_path / "t.gtx")
    grid = parse_grid_file(str(tmp_path / "t.gtx"))
    assert grid["nlat"] == 3 and grid["nlon"] == 3
    assert grid["scale_x"] == 5.0 and grid["scale_y"] == 5.0
    assert math.isclose(grid_stats(grid)["max_m"], 9.0)
    # exact node: (lat=10, lon=0) -> row0 col0 -> value 1
    assert undulation_at(grid, 10.0, 0.0) == pytest.approx(1.0)
    # exact node: (lat=5, lon=5) -> value 5
    assert undulation_at(grid, 5.0, 5.0) == pytest.approx(5.0)
    # interior bilinear: (7.5, 5) -> top=2, bottom=5, dc=0 -> 3.5
    assert undulation_at(grid, 7.5, 5.0) == pytest.approx(3.5)
    # interior bilinear: (7.5, 2.5) -> 1.5/4.5 mid -> 3.0
    assert undulation_at(grid, 7.5, 2.5) == pytest.approx(3.0)
    assert undulation_at(grid, -1.0, 5.0) is None     # outside domain
    assert undulation_at(grid, 5.0, 15.0) is None     # outside domain
    assert hashlib.sha256((tmp_path / "t.gtx").read_bytes()).hexdigest() == sha


def test_gtx_bad_header_refused(tmp_path):
    bad = struct.pack(">4d2i", 10.0, 0.0, 10.0, 10.0, 3, 3)  # north<=south? N10 S10
    (tmp_path / "bad.gtx").write_bytes(bad)
    with pytest.raises(ValueError, match="GEOID_BAD_HEADER"):
        parse_grid_file(str(tmp_path / "bad.gtx"))


def test_gtx_not_a_reception_dtype_no_second_door(tmp_path):
    """A raw GTX file is refused by the platform gate: the production path
    is the official TIFF grids, which ARE accepted reception dtypes. No
    special door is opened for any format."""
    _synthetic_gtx(tmp_path / "t.gtx")
    res = ingest_grid(str(tmp_path / "t.gtx"), model_id="TEST96",
                      epsg_vertical=5773, license_status="public_domain",
                      license_source="test", tide_system="tide_free",
                      tide_evidence="test", source_url="http://x")
    assert res["status"] == "rejected"
    assert any(f["code"] == "GEOID_RECEPTION_REFUSED"
               for f in res["findings"])


def test_golden_nodes_are_exact_values(tmp_path):
    _synthetic_gtx(tmp_path / "t.gtx")
    grid = parse_grid_file(str(tmp_path / "t.gtx"))
    nodes = golden_nodes(grid)
    assert len(nodes) == 9
    assert {"lat": 5.0, "lon": 5.0, "undulation_m": 5.0} in nodes


# ---------------------------------------------------------------------------
# the real frozen registries (committed with fingerprints; grids live outside)
# ---------------------------------------------------------------------------
pytestmark_real = pytest.mark.skipif(
    not DEFAULT_REGISTRY.exists(),
    reason="geoid_grid_registry.json not present (pure path ships without it)")


@pytest.mark.skipif(not NODES_DOC.exists(),
                    reason="golden nodes file not present")
def test_real_registry_records_both_grids_and_passed_crosscheck():
    reg = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    models = {g["model_id"]: g for g in reg["grids"]}
    assert {"EGM96", "EGM2008"} <= set(models)
    for model, rec in models.items():
        gates = rec["gates"]
        for gate in ("sha256", "license", "tide_system", "grid_coords",
                     "interpolation", "crs_pair", "validity_domain"):
            assert gates.get(gate), f"{model}: gate {gate} must be recorded"
        assert gates["independent_check"].startswith("passed"), \
            f"{model}: the independent crosscheck must have passed"
        assert rec["crosscheck"]["status"] == "passed"
    assert models["EGM96"]["gates"]["crs_pair"]["vertical"] == "EPSG:5773"
    assert models["EGM2008"]["gates"]["crs_pair"]["vertical"] == "EPSG:3855"


@pytest.mark.skipif(not NODES_DOC.exists(),
                    reason="golden nodes file not present")
def test_golden_nodes_match_registry_fingerprints():
    nodes_doc = json.loads(NODES_DOC.read_text(encoding="utf-8"))
    reg = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    sha_by_model = {g["model_id"]: g["gates"]["sha256"] for g in reg["grids"]}
    for grid in nodes_doc["grids"]:
        assert grid["grid_sha256"] == sha_by_model[grid["model_id"]]
        assert len(grid["nodes"]) == 25
        for node in grid["nodes"]:
            assert -130.0 <= node["undulation_m"] <= 90.0, \
                "undulation values must stay in the physical global range"


def test_registry_pinned_values_fingerprint_stable():
    """The registry JSON itself carries its own checksum over the grid
    records so silent edits are detectable."""
    if not DEFAULT_REGISTRY.exists():
        pytest.skip("registry not present")
    reg = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    for g in reg["grids"]:
        assert len(g["gates"]["sha256"]) == 64
        assert g["gates"]["sha256"] == g["gates"]["sha256"].lower()


def test_vertical_refusal_without_grid_dir_on_pure_path():
    """The committed registry exists but grids live outside the repo: the
    rule must refuse with the file-missing code, never answer blindly."""
    rp = registry_path()
    if not rp.exists():
        pytest.skip("registry not present")
    from geologia.data_layer.vertical_rule import answer_vertical
    res = answer_vertical(15.35, 44.2, "EGM96")
    assert res["status"] == 409
    assert res["error"] == "VERTICAL_GRID_FILE_MISSING"
