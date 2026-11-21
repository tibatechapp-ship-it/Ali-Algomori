"""v0.5.0 validation hardening tests: corrupted files + declared-vs-observed CRS.

Every corrupted golden file must be refused with its SPECIFIC code — a generic
"fail" is not enough. These files are the refusal reference corpus; regenerate
with scripts/make_corrupt_corpus.py. CI green does NOT certify geological
validity — these tests only prove the reception/verification contract.
"""
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "geologia-store"
    d.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(d))
    return d


def codes(report):
    return [f["code"] for f in report["findings"]]


# ---------------------------------------------------------------------------
# corrupted-file corpus: each damage has one exact refusal code
# ---------------------------------------------------------------------------
def test_las_truncated_data_rows_is_an_error():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_las_truncated.las"), "las")
    assert report["status"] == "fail"
    # v0.5.0: row-count mismatch is corruption (truncation/tamper) -> error
    assert "LAS_DATA_ROWS_MISMATCH" in codes(report)
    sev = next(f for f in report["findings"]
               if f["code"] == "LAS_DATA_ROWS_MISMATCH")
    assert sev["severity"] == "error"


def test_las_nul_byte_refused_as_corruption():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_las_nul.las"), "las")
    assert report["status"] == "fail"
    assert "LAS_CONTROL_CHARS" in codes(report)


def test_csv_nul_byte_refused_as_corruption():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_csv_nul.csv"), "csv")
    assert report["status"] == "fail"
    assert "CSV_CONTROL_CHARS" in codes(report)


def test_csv_identifier_conflict_is_an_error():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_csv_id_conflict.csv"), "csv")
    assert report["status"] == "fail"
    assert "CSV_ID_CONFLICT" in codes(report)


# ---------------------------------------------------------------------------
# declared-vs-observed CRS consistency (EPSG, units, magnitudes)
# ---------------------------------------------------------------------------
def test_geojson_declared_projected_crs_contradicts_rfc7946_content():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_geojson_crs_utm.json"), "geojson",
                           declared_crs="EPSG:32638")
    assert report["status"] == "fail"
    assert "CRS_GEOJSON_NON_WGS84" in codes(report)


def test_geojson_declared_wgs84_is_consistent_with_axis_order_note():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden.geojson"), "geojson",
                           declared_crs="EPSG:4326")
    assert report["status"] == "pass"
    assert "CRS_DECLARED_OK" in codes(report)
    assert "CRS_AXIS_ORDER_NOTE" in codes(report)


def test_geojson_unrecognized_declared_crs_is_a_warning_not_a_refusal():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden.geojson"), "geojson",
                           declared_crs="mystery_grid_v7")
    assert report["status"] == "pass"
    assert "CRS_GEOJSON_CRS_UNRECOGNIZED" in codes(report)


def test_csv_declared_utm_but_columns_hold_degrees_is_refused():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_csv_utm_degrees.csv"), "csv",
                           declared_crs="EPSG:32638")
    assert report["status"] == "fail"
    assert "CRS_MISMATCH_PROJECTED_GEO" in codes(report)


def test_csv_declared_geographic_but_values_look_projected_is_refused():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_csv_geo_utmvals.csv"), "csv",
                           declared_crs="EPSG:4326")
    assert report["status"] == "fail"
    assert "CRS_MISMATCH_GEO_PROJECTED" in codes(report)


def test_csv_declared_utm_with_utm_magnitudes_passes():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_csv_utm_valid.csv"), "csv",
                           declared_crs="EPSG:32638")
    assert report["status"] == "pass"
    assert "CRS_DECLARED_OK" in codes(report)


def test_csv_declared_local_crs_warns_no_pinned_transform():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_wells.csv"), "csv",
                           declared_crs="local_site_grid")
    assert report["status"] == "pass"
    assert "CRS_LOCAL_NO_TRANSFORM" in codes(report)


def test_csv_without_declaration_records_honest_assumption():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_wells.csv"), "csv")
    assert report["status"] == "pass"
    assert "CRS_NONE_DECLARED" in codes(report)


def test_las_units_magnitude_mismatch_is_flagged(tmp_path):
    from geologia.data_layer.validators import validate_file
    las = tmp_path / "deep_ft_as_m.las"
    las.write_text(
        "~Version Information\nVERS.  2.0 :   CWLS LOG ASCII STANDARD\n"
        "~Well Information\nWELL.  X :   Well\nNULL.  -999.25 :   Null\n"
        "STRT.  9800.000 :   Start Depth (m)\nSTOP.  9850.000 :   Stop Depth (m)\n"
        "STEP.  1.0000 :   Step Depth (m)\n"
        "~Curve Information\nDEPT.  m :   Depth\n~A\n" +
        "\n".join(f"{9800 + i:.3f}  2.5" for i in range(51)) + "\n",
        encoding="utf-8")
    report = validate_file(str(las), "las", declared_units="m")
    assert report["status"] == "pass"  # warning, not refusal — but recorded
    assert "CRS_UNITS_SUSPECT" in codes(report)


def test_validate_file_reports_declared_fields():
    from geologia.data_layer.validators import validate_file
    report = validate_file(str(DATA / "golden_wells.csv"), "csv",
                           declared_crs="EPSG:4326", declared_units="m")
    assert report["declared_crs"] == "EPSG:4326"
    assert report["declared_units"] == "m"


# ---------------------------------------------------------------------------
# integration: the dataset record carries declared CRS into validation
# ---------------------------------------------------------------------------
def test_validate_dataset_applies_declared_crs_from_record(store):
    from geologia.data_layer import records as ds
    # ids are content-addressed: the declaration lives WITH the record, so a
    # wrong declaration fails that record, and a correctly-declared record of
    # consistent bytes passes.
    rec = ds.register_dataset(
        "آبار بصيغة CRS خاطئة", str(DATA / "golden_csv_utm_degrees.csv"),
        dtype="csv", declared_crs="EPSG:32638")
    result = ds.validate_dataset(rec["id"])
    assert result["report"]["status"] == "fail"
    assert "CRS_MISMATCH_PROJECTED_GEO" in codes(result["report"])
    assert ds.get_dataset(rec["id"])["status"] == "validated_fail"
    rec2 = ds.register_dataset(
        "آبار بإعلان متوافق", str(DATA / "golden_csv_utm_valid.csv"),
        dtype="csv", declared_crs="EPSG:32638")
    result2 = ds.validate_dataset(rec2["id"])
    assert result2["report"]["status"] == "pass"
    assert ds.get_dataset(rec2["id"])["status"] == "validated_pass"


def test_golden_valid_files_still_pass_after_hardening():
    from geologia.data_layer.validators import validate_file
    assert validate_file(str(DATA / "golden_wells.csv"), "csv")["status"] == "pass"
    assert validate_file(str(DATA / "golden_las_valid.las"), "las")["status"] == "pass"
    assert validate_file(str(DATA / "golden.geojson"), "geojson")["status"] == "pass"
    assert validate_file(str(DATA / "golden_dem_tile.tif"), "tiff")["status"] == "pass"
