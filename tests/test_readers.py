"""Real-reader tests: lasio / tifffile / sqlite3 against golden files.

The structural validators prove format validity; these tests prove the
readers actually parse CONTENT and agree (or explicitly disagree) with the
byte-level checks. Each corrupted file must produce its SPECIFIC reader
code — a generic failure is not enough.
"""
import warnings
from pathlib import Path

import pytest


from geologia.data_layer.evidence import compile_evidence
from geologia.data_layer.readers import (capabilities, parse_geokeys,
                                         read_geopackage, read_geotiff,
                                         read_las)

warnings.simplefilter("ignore")

DATA = Path(__file__).parent / "data"
REF = DATA / "reference"


def codes(reader_result):
    return [f["code"] for f in reader_result["findings"]]


# Honest engine gates: a direct reader test without its engine SKIPS with a
# named reason (visible in CI output) — it never fails and never pretends.
_cap = capabilities()
req_lasio = pytest.mark.skipif(
    not _cap["lasio"],
    reason="lasio absent — LAS deep-read verification cannot run and will "
           "NOT be claimed")
req_tifffile = pytest.mark.skipif(
    not _cap["tifffile"],
    reason="tifffile absent — GeoTIFF deep-read verification cannot run and "
           "will NOT be claimed")
req_pyproj = pytest.mark.skipif(
    not _cap["pyproj"],
    reason="pyproj absent — SRS definition verification cannot run and will "
           "NOT be claimed")


# --- capabilities: the layer must state its engines honestly ------------------
def test_capabilities_lists_all_engines_even_when_absent():
    cap = capabilities()
    for key in ("lasio", "tifffile", "pyproj", "numpy", "sqlite3"):
        assert key in cap
    assert cap["sqlite3"]  # stdlib: always present


def test_unavailable_engine_never_fakes_a_reading(monkeypatch):
    from geologia.data_layer import readers as R
    empty = {"lasio": None, "tifffile": None, "pyproj": None,
             "numpy": None, "sqlite3": "3.0"}
    monkeypatch.setattr(R, "capabilities", lambda: empty)
    r = R.read_las(str(REF / "ref_las_valid.las"))
    assert r["ok"] is False and r["data"] is None
    assert codes(r) == ["READER_LIB_ABSENT"]
    unv = [i["code"] for i in r["evidence"]["unverifiable"]]
    assert "READER_LIB_ABSENT" in unv
    t = R.read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"))
    assert codes(t) == ["READER_LIB_ABSENT"]


# --- GeoKey parser -------------------------------------------------------------
def test_parse_geokeys_inline_single_short_values():
    gk = parse_geokeys((1, 1, 0, 2, 1024, 0, 1, 2, 3072, 0, 1, 32638))
    assert gk == {1024: 2, 3072: 32638}
    assert parse_geokeys(None) is None
    assert parse_geokeys((1, 1, 0)) is None


# --- LAS via lasio --------------------------------------------------------------
@req_lasio
def test_las_valid_read_matches_reference():
    r = read_las(str(REF / "ref_las_valid.las"))
    assert r["ok"] is True
    d = r["data"]
    assert d["engine"] == "lasio"
    assert d["rows"] == 6
    assert d["curves"] == ["DEPT", "RHOB", "NPHI"]
    assert d["units"] == ["m", "g/cm3", "v/v"]
    assert d["null"] == -999.25
    verified = {i["code"] for i in r["evidence"]["verified"]}
    assert "LAS_READER_ROWS_VERIFIED" in verified
    assert "LAS_READER_NULL_HONORED" in verified


@req_lasio
def test_las_row_count_lie_is_caught_independently():
    r = read_las(str(REF / "ref_las_rows_lie.las"))
    assert "LAS_READER_ROWS_MISMATCH" in codes(r)
    sev = next(f for f in r["findings"]
               if f["code"] == "LAS_READER_ROWS_MISMATCH")
    assert sev["severity"] == "error"


@req_lasio
def test_las_truncated_partial_last_row_is_caught():
    r = read_las(str(REF / "ref_las_truncated.las"))
    assert "LAS_READER_ROWS_MISMATCH" in codes(r)


@req_lasio
def test_las_missing_curve_unit_is_flagged():
    r = read_las(str(REF / "ref_las_no_units.las"))
    assert "LAS_CURVE_UNIT_MISSING" in codes(r)
    sev = next(f for f in r["findings"]
               if f["code"] == "LAS_CURVE_UNIT_MISSING")
    assert sev["severity"] == "warning"


@req_lasio
def test_las_nul_bytes_become_non_numeric_refusal():
    r = read_las(str(DATA / "golden_las_nul.las"))
    assert "LAS_READER_NON_NUMERIC" in codes(r)
    assert all(f["severity"] == "error" for f in r["findings"]
               if f["code"] == "LAS_READER_NON_NUMERIC")


@req_lasio
def test_las_reader_agrees_with_text_validator_on_truncated_rows():
    from geologia.data_layer.validators import validate_file
    rep = validate_file(str(DATA / "golden_las_truncated.las"), "las")
    got = {f["code"] for f in rep["findings"]}
    # two independent implementations must BOTH catch the truncation
    assert "LAS_DATA_ROWS_MISMATCH" in got      # text-level
    assert "LAS_READER_ROWS_MISMATCH" in got    # lasio-level


# --- GeoTIFF via tifffile --------------------------------------------------------
@req_tifffile
@req_pyproj
def test_geotiff_valid_read_matches_reference():
    r = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"))
    assert r["ok"] is True
    d = r["data"]
    assert d["shape"] == [4, 4] and d["dtype"] == "float32"
    assert d["crs_epsg"] == 32638
    assert d["scale"] == [25.0, 25.0, 1.0]
    ext = d["extent"]
    assert ext["minx"] == 305000.0 and ext["maxx"] == 305100.0
    assert ext["maxy"] == 2740000.0 and ext["miny"] == 2739900.0
    verified = {i["code"] for i in r["evidence"]["verified"]}
    assert "TIFF_EXTENT_RECOMPUTED" in verified
    assert "TIFF_CRS_ENGINE_VERIFIED" in verified


@req_tifffile
def test_geotiff_extent_arithmetic_is_independent_recomputation():
    """The extent must come from tiepoint+scale math, not from a tag."""
    r = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"))
    d = r["data"]
    x0, y0 = d["tiepoint"][3], d["tiepoint"][4]
    sx, sy = d["scale"][0], d["scale"][1]
    h, w = d["shape"]
    assert d["extent"]["maxx"] == x0 + sx * w
    assert d["extent"]["miny"] == y0 - sy * h


@req_tifffile
def test_geotiff_declared_crs_contradiction_is_an_error():
    r = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"),
                     declared_crs="EPSG:32637")
    assert "CRS_READER_MISMATCH" in codes(r)
    r2 = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"),
                      declared_crs="EPSG:32638")
    verified = {i["code"] for i in r2["evidence"]["verified"]}
    assert "CRS_READER_MATCH" in verified


@req_tifffile
def test_geotiff_nodata_read():
    r = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"))
    assert r["data"]["nodata"] == -9999.0


def test_geotiff_without_geokeys_reports_missing_not_guesses(tmp_path):
    import tifffile
    import numpy as np
    p = tmp_path / "plain.tif"
    tifffile.imwrite(p, np.zeros((2, 2), dtype="uint8"))
    r = read_geotiff(str(p))
    assert "TIFF_GEOKEYS_MISSING" in codes(r)
    unv = {i["code"] for i in r["evidence"]["unverifiable"]}
    assert "TIFF_GEOKEYS_MISSING" in unv


# --- GeoPackage via sqlite3 -------------------------------------------------------
@req_pyproj
def test_gpkg_valid_read_matches_reference():
    r = read_geopackage(str(REF / "ref_gpkg_wells.gpkg"))
    assert r["ok"] is True
    wells = r["data"]["features"]["wells"]
    assert wells["count"] == 4 and wells["null_geoms"] == 0
    assert wells["bbox"]["minx"] == 305000.0
    assert wells["bbox"]["maxy"] == 2740100.0
    verified = {i["code"] for i in r["evidence"]["verified"]}
    assert "GPKG_FEATURE_COUNT_VERIFIED" in verified
    assert "GPKG_CONTENTS_BBOX_VERIFIED" in verified
    assert "GPKG_SRS_ENGINE_VERIFIED" in verified


def test_gpkg_not_a_gpkg_rejected_by_application_id(tmp_path):
    import sqlite3
    p = tmp_path / "fake.gpkg"
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA application_id = 1337")
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    r = read_geopackage(str(p))
    assert r["ok"] is False
    assert "GPKG_NOT_GPKG" in codes(r)


def test_gpkg_declared_crs_mismatch_is_an_error():
    r = read_geopackage(str(REF / "ref_gpkg_wells.gpkg"),
                        declared_crs="EPSG:4326")
    assert "CRS_READER_MISMATCH" in codes(r)


def test_gpkg_srs_definition_mismatch_detected(tmp_path):
    """organization says EPSG:X but the WKT parses as EPSG:Y -> error."""
    import sqlite3
    import pyproj
    p = tmp_path / "liar.gpkg"
    conn = sqlite3.connect(p)
    conn.execute(f"PRAGMA application_id = {0x47504B47}")
    conn.execute("""CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT, srs_id INTEGER PRIMARY KEY, organization TEXT,
        organization_coordsys_id INTEGER, definition TEXT, description TEXT)""")
    conn.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY,"
                 " data_type TEXT, identifier TEXT, description TEXT,"
                 " last_change DATETIME, min_x DOUBLE, min_y DOUBLE,"
                 " max_x DOUBLE, max_y DOUBLE, srs_id INTEGER)")
    conn.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT,"
                 " column_name TEXT, geometry_type_name TEXT, srs_id INTEGER,"
                 " z TINYINT, m TINYINT)")
    wkt_utm = pyproj.CRS("EPSG:32638").to_wkt(version="WKT1_GDAL")
    # lie: registered as 4326, but the definition is UTM 38N
    conn.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
                 ("lie", 4326, "EPSG", 4326, wkt_utm, ""))
    conn.commit()
    conn.close()
    r = read_geopackage(str(p))
    assert "CRS_SRS_DEFINITION_MISMATCH" in codes(r)


def test_gpkg_corrupt_sqlite_is_reported(tmp_path):
    p = tmp_path / "corrupt.gpkg"
    p.write_bytes(b"SQLite format 3\x00" + b"\x11" * 200)
    r = read_geopackage(str(p))
    assert "GPKG_CORRUPT_DB" in codes(r)


# --- compile_evidence re-validation ------------------------------------------------
def test_reader_evidence_survives_recompilation():
    r = read_geotiff(str(REF / "ref_dem_utm38n_msl.tif"))
    ev = r["evidence"]
    recompiled = compile_evidence(ev["read"], ev["verified"],
                                  ev["unverifiable"])
    assert recompiled["counts"]["read"] == ev["counts"]["read"]
