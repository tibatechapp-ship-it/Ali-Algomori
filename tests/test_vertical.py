"""Vertical reference + units tests.

A height without a datum is a number, not a measurement. These tests pin
the recognition table, the honest unknown/missing handling, and the
WKT-vs-GeoTIFF conflict detection.
"""

from geologia.data_layer.vertical import (check_vertical_consistency,
                                          classify_vertical_geokeys,
                                          las_depth_datum, vertical_evidence,
                                          vertical_findings, wkt_vertical,
                                          wkt_vertical_evidence)


def finding_codes(findings):
    return [f["code"] for f in findings]


# --- classification ---------------------------------------------------------------
def test_recognized_vertical_cs():
    v = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9001})
    assert v["cs_name"] == "MSL height (EPSG:5714)"
    assert v["datum_name"] == "mean sea level datum"
    assert v["units_name"] == "metre"
    assert finding_codes(vertical_findings(v)) == ["VERT_DATUM_OK"]


def test_ellipsoidal_vertical_is_recognized():
    v = classify_vertical_geokeys({4096: 4979, 4097: 2, 4098: 9001})
    assert "ellipsoidal" in v["cs_name"]
    assert finding_codes(vertical_findings(v)) == ["VERT_DATUM_OK"]


def test_unknown_vertical_cs_is_flagged_not_accepted():
    v = classify_vertical_geokeys({4096: 62000, 4097: 3, 4098: 9001})
    codes_ = finding_codes(vertical_findings(v))
    assert "VERT_DATUM_UNKNOWN" in codes_
    assert "VERT_DATUM_OK" not in codes_
    sev = next(f for f in vertical_findings(v)
               if f["code"] == "VERT_DATUM_UNKNOWN")
    assert sev["severity"] == "warning"


def test_missing_vertical_keys_is_missing():
    assert finding_codes(vertical_findings(None)) == ["VERT_DATUM_MISSING"]
    ev = vertical_evidence(None)
    assert ev["counts"]["unverifiable"] == 1


def test_missing_vertical_units_is_flagged():
    v = classify_vertical_geokeys({4096: 5714, 4097: 3})
    assert "VERT_UNITS_MISSING" in finding_codes(vertical_findings(v))


def test_foot_units_are_flagged_not_converted():
    v = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9002})
    codes_ = finding_codes(vertical_findings(v))
    assert "VERT_UNITS_NOT_METRE" in codes_
    unv = {i["code"] for i in vertical_evidence(v)["unverifiable"]}
    assert "VERT_UNITS_NOT_METRE" in unv


def test_vertical_evidence_recognized_is_verified():
    v = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9001})
    ev = vertical_evidence(v)
    assert ev["counts"]["verified"] == 1
    assert ev["verified"][0]["check"]  # the check must be named


# --- WKT vertical -------------------------------------------------------------------
def test_wkt_vertical_extraction():
    wkt = ('PROJCS["WGS 84 / UTM zone 38N", ... , VERTCS["mean sea level",'
           'VDATUM["Mean Sea Level"],...]]')
    v = wkt_vertical(wkt)
    assert v is not None
    assert v["name"] == "mean sea level"
    assert v["msl_hint"] is True


def test_wkt_without_vertcs_returns_none():
    assert wkt_vertical('PROJCS["WGS 84 / UTM zone 38N", ...]') is None


def test_wkt_vertical_evidence_is_honestly_unverifiable():
    ev = wkt_vertical_evidence(wkt_vertical(
        'VERTCS["MSL", VDATUM["Mean Sea Level"]]'))
    assert ev["counts"]["verified"] == 0
    assert ev["counts"]["unverifiable"] == 1


# --- conflict detection ---------------------------------------------------------------
def test_wkt_ellipsoidal_vs_geotiff_msl_is_conflict():
    gk = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9001})
    wkt_v = wkt_vertical('VERTCS["WGS84 ellipsoid", VDATUM["Ellipsoid"]]')
    assert wkt_v["ellipsoidal_hint"] is True
    codes_ = finding_codes(check_vertical_consistency(gk, wkt_v))
    assert "VERT_DATUM_CONFLICT" in codes_
    assert check_vertical_consistency(gk, wkt_v)[0]["severity"] == "error"


def test_consistent_vertical_claims_produce_no_conflict():
    gk = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9001})
    wkt_v = wkt_vertical('VERTCS["MSL", VDATUM["Mean Sea Level"]]')
    assert check_vertical_consistency(gk, wkt_v) == []


def test_missing_either_side_produces_no_conflict():
    gk = classify_vertical_geokeys({4096: 5714, 4097: 3, 4098: 9001})
    assert check_vertical_consistency(gk, None) == []
    assert check_vertical_consistency(None, {"name": "x",
                                             "ellipsoidal_hint": True,
                                             "msl_hint": False}) == []


# --- LAS depth datum -------------------------------------------------------------------
def test_las_without_datum_hints_is_undeclared():
    findings, ev = las_depth_datum(["DEPT", "RHOB", "NPHI"])
    assert finding_codes(findings) == ["VERT_DEPTH_DATUM_UNDECLARED"]
    assert findings[0]["severity"] == "warning"
    assert ev["counts"]["unverifiable"] == 1


def test_las_datum_hint_stays_unverifiable():
    findings, ev = las_depth_datum(["DEPT", "KB"])
    assert finding_codes(findings) == ["VERT_DEPTH_DATUM_UNDECLARED"]
    read_items = [i for i in ev["read"] if i["code"] == "VERT_LAS_DATUM_HINT"]
    assert read_items and "KB" in read_items[0]["detail"]
    unv = ev["unverifiable"][0]
    assert unv["reason"]  # free-text hint can never become "verified"
