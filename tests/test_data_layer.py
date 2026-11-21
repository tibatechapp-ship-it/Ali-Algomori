"""Data verification layer tests: golden reference inputs + task gates.

Golden files live in tests/data/ (reference inputs); expected outcomes are
asserted here (reference results). Any behaviour change breaks these first.
"""
import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "geologia-store"
    d.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(d))
    return d


# ---------------------------------------------------------------------------
# Validators against golden reference files
# ---------------------------------------------------------------------------
def test_golden_las_valid_passes():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_las_valid.las"), "las")
    assert report["status"] == "pass"
    codes = [f["code"] for f in report["findings"]]
    assert "LAS_OK" in codes and "LAS_NO_VERSION" not in codes
    # 6 declared rows match 6 data rows: no false mismatch warning.
    assert "LAS_DATA_ROWS_MISMATCH" not in codes


def test_golden_las_missing_version_fails():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_las_no_version.las"), "las")
    assert report["status"] == "fail"
    assert "LAS_NO_VERSION" in [f["code"] for f in report["findings"]]


def test_golden_geojson_passes_with_crs_assumption():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden.geojson"), "geojson")
    assert report["status"] == "pass"
    codes = [f["code"] for f in report["findings"]]
    assert "GEOJSON_OK" in codes and "GEOJSON_NO_CRS" in codes


def test_golden_geojson_bad_coords_fails():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_geojson_bad_coords.json"), "geojson")
    assert report["status"] == "fail"
    assert "GEOJSON_BAD_COORDS" in [f["code"] for f in report["findings"]]


def test_golden_csv_passes_and_bad_csv_fails():
    from geologia.data_layer.validators import validate_file
    good = validate_file(str(DATA / "golden_wells.csv"), "csv")
    assert good["status"] == "pass"
    bad = validate_file(str(DATA / "golden_wells_bad.csv"), "csv")
    assert bad["status"] == "fail"
    codes = [f["code"] for f in bad["findings"]]
    assert "CSV_LATLON_RANGE" in codes
    assert "CSV_MISSING_VALUES" in codes
    assert "CSV_DUP_ROWS" in codes


def test_tiff_golden_tile_passes_with_geo_tags():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_dem_tile.tif"), "tiff")
    assert report["status"] == "pass"
    codes = [f["code"] for f in report["findings"]]
    assert "TIFF_OK" in codes and "TIFF_GEO_TAGS" in codes


def test_tiff_truncated_golden_fails():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_dem_truncated.tif"), "tiff")
    assert report["status"] == "fail"
    assert "TIFF_TRUNCATED" in [f["code"] for f in report["findings"]]


def test_tiff_fake_magic_no_longer_passes(tmp_path):
    # v0.3.0 accepted any II/MM magic; v0.4.0 hardening requires a real IFD
    # with the mandatory tags — a fake container must fail honestly.
    from geologia.data_layer.validators import validate_file
    tif = tmp_path / "fake.tif"
    tif.write_bytes(b"II*\x00" + b"\x00" * 64)
    report = validate_file(str(tif), "tiff")
    assert report["status"] == "fail"
    assert "TIFF_NO_IFD" in [f["code"] for f in report["findings"]]
    missing = validate_file(str(tmp_path / "nope.tif"))
    assert missing["status"] == "fail"
    assert missing["findings"][0]["code"] == "GEN_FILE_MISSING"


# ---------------------------------------------------------------------------
# Dataset records: content-addressed id + checksum verification
# ---------------------------------------------------------------------------
def test_register_and_checksum_roundtrip(store):
    from geologia.data_layer import records as ds
    src = DATA / "golden_las_valid.las"
    rec = ds.register_dataset("سجل بئر اختبار", str(src), dtype="las",
                              declared_crs="local_depth", declared_units="m; g/cm3",
                              license_status="test")
    assert rec["status"] == "registered"
    assert rec["id"] == f"ds-{rec['sha256'][:12]}"
    again = ds.register_dataset("نفس الملف باسم آخر", str(src), dtype="las")
    assert again["id"] == rec["id"]
    assert again["status"] == "already_registered"
    check = ds.verify_checksum(rec["id"])
    assert check["checksum_ok"] is True
    assert ds.get_dataset(rec["id"])["status"] == "verified"


def test_checksum_detects_tampering(store):
    from geologia.data_layer import records as ds
    f = store / "wells.csv"
    f.write_text("well_name,lat,lon\nd1,15.3,44.2\n", encoding="utf-8")
    rec = ds.register_dataset("آبار", str(f), dtype="csv")
    f.write_text("well_name,lat,lon\nd1,15.9,44.2\n", encoding="utf-8")  # tampered
    check = ds.verify_checksum(rec["id"])
    assert check["checksum_ok"] is False
    assert ds.get_dataset(rec["id"])["status"] == "checksum_mismatch"


def test_validate_dataset_persists_status(store):
    from geologia.data_layer import records as ds
    rec = ds.register_dataset("geojson سليم", str(DATA / "golden.geojson"), dtype="geojson")
    result = ds.validate_dataset(rec["id"])
    assert result["report"]["status"] == "pass"
    assert ds.get_dataset(rec["id"])["status"] == "validated_pass"


# ---------------------------------------------------------------------------
# Task ledger: mandatory gates refuse execution in foundation phase
# ---------------------------------------------------------------------------
def test_task_creation_requires_registry_engine_and_data(store):
    from geologia.data_layer import tasks as tl
    with pytest.raises(ValueError):
        tl.create_task("مهمة", "not-an-engine", ["ds-x"])
    with pytest.raises(ValueError):
        tl.create_task("مهمة بلا بيانات", "gempy", [])


def test_transition_to_ready_refused_engine_not_certified(store):
    from geologia.data_layer import tasks as tl
    task = tl.create_task("نمذجة حوض صنعاء", "gempy", ["ds-fake"],
                          isolation={"pinned_version": None})
    assert task["state"] == "planned"
    # State machine first: planned -> ready skips inputs_validated.
    with pytest.raises(tl.TaskGateError) as exc:
        tl.transition(task["id"], "ready")
    assert exc.value.gate == "state_machine"


def test_validation_gate_blocks_before_execution_gate(store):
    from geologia.data_layer import tasks as tl
    task = tl.create_task("تحليل LAS", "lasio", ["ds-does-not-exist"])
    with pytest.raises(tl.TaskGateError) as exc:
        tl.transition(task["id"], "inputs_validated")
    assert exc.value.gate == "data_validation"


def test_full_happy_path_reaches_inputs_validated_then_stops(store):
    from geologia.data_layer import records as ds
    from geologia.data_layer import tasks as tl
    rec = ds.register_dataset("آبار سليمة", str(DATA / "golden_wells.csv"), dtype="csv")
    ds.validate_dataset(rec["id"])
    task = tl.create_task("تحليل آبار", "pastas", [rec["id"]],
                          isolation={"pinned_version": "1.2.3", "cpu": 2,
                                     "memory_mb": 4096, "timeout_seconds": 600})
    moved = tl.transition(task["id"], "inputs_validated")
    assert moved["state"] == "inputs_validated"
    with pytest.raises(tl.TaskGateError) as exc:
        tl.transition(task["id"], "ready")
    assert exc.value.gate == "engine_certification"
    assert tl.get_task(task["id"])["state"] == "inputs_validated"


def test_rejection_closes_task_honestly(store):
    from geologia.data_layer import tasks as tl
    task = tl.create_task("مهمة مستحيلة", "gempy", ["ds-x"])
    moved = tl.transition(task["id"], "rejected", reason="بيانات غير متوفرة")
    assert moved["state"] == "rejected"
    with pytest.raises(tl.TaskGateError):
        tl.transition(task["id"], "planned")


def test_tasks_persist_across_store_reads(store):
    from geologia.data_layer import tasks as tl
    task = tl.create_task("دائمة", "obspy", ["ds-y"])
    reloaded = tl.get_task(task["id"])
    assert reloaded is not None
    assert (store / "tasks.json").exists()
    assert json.loads((store / "tasks.json").read_text(encoding="utf-8"))["tasks"]
