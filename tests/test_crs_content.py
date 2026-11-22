"""Content-side CRS detection tests (v0.20.0, governing sequence step 4).

«اكتشاف CRS من المحتوى الفعلي لا من الإعلان» — detection from the actual
content, not from the announcement. The module's whole claim is tested here:
magnitude classification proves CLASS only, a UTM zone is never claimed from
content alone, and the resolved truth classification states exactly what the
content proves versus what rests on the declaration.
"""
from __future__ import annotations

from geologia.data_layer.crs_content import (
    CLASS_GEOGRAPHIC,
    CLASS_UNKNOWN,
    CLASS_UTM,
    TRUTH_CONTRADICTED,
    TRUTH_DECLARED_ONLY,
    TRUTH_UNDETERMINED,
    TRUTH_VERIFIED_CONTENT,
    classify_content_points,
    detect_point_class,
    resolve_declared_vs_content,
    verify_wgs84_ranges,
)

# San'a-area WGS84 degrees (the zone-38 lesson, in geographic form).
GEO_PAIRS = [(44.2, 15.35), (44.25, 15.4), (44.15, 15.3)]
# UTM 38N metres (easting, northing) — golden literals from the workspace
# frozen reference (pyproj 3.7.2), reused here as magnitude fixtures only.
UTM_PAIRS = [(414133.1015, 1697196.8389), (419519.2533, 1702708.4364)]


def test_detect_point_class_geographic():
    assert detect_point_class(44.2, 15.35) == CLASS_GEOGRAPHIC
    assert detect_point_class(-179.9, 89.9) == CLASS_GEOGRAPHIC


def test_detect_point_class_utm():
    for x, y in UTM_PAIRS:
        assert detect_point_class(x, y) == CLASS_UTM


def test_detect_point_class_unknown():
    assert detect_point_class(50_000.0, 12_000_000.0) == CLASS_UNKNOWN
    assert detect_point_class(999_999.0, -5.0) == CLASS_UNKNOWN


def test_classify_empty_sample_undetermined():
    report = classify_content_points([])
    assert report["detected_class"] == CLASS_UNKNOWN
    assert report["truth_class"] == TRUTH_UNDETERMINED
    assert report["n_points_checked"] == 0


def test_classify_geographic_sample_verified_content():
    report = classify_content_points(GEO_PAIRS)
    assert report["detected_class"] == CLASS_GEOGRAPHIC
    assert report["truth_class"] == TRUTH_VERIFIED_CONTENT
    assert report["n_points_checked"] == 3
    assert report["n_ambiguous"] == 0


def test_classify_utm_sample_verified_content():
    report = classify_content_points(UTM_PAIRS)
    assert report["detected_class"] == CLASS_UTM
    assert report["truth_class"] == TRUTH_VERIFIED_CONTENT


def test_classify_mixed_sample_never_guesses():
    report = classify_content_points([(44.2, 15.35), *UTM_PAIRS])
    assert report["detected_class"] == CLASS_UNKNOWN
    assert report["truth_class"] == TRUTH_UNDETERMINED
    assert report["n_geographic"] == 1
    assert report["n_utm"] == 2


def test_classify_respects_sample_cap():
    many = [(44.0 + i * 0.001, 15.0) for i in range(500)]
    report = classify_content_points(many, max_points=10)
    assert report["n_points_checked"] == 10


def test_verify_wgs84_ranges_ok():
    report = verify_wgs84_ranges(GEO_PAIRS)
    assert report is not None
    assert report["in_wgs84_range"] is True
    assert report["truth_class"] == TRUTH_VERIFIED_CONTENT
    assert report["n_outside"] == 0


def test_verify_wgs84_ranges_contradicted():
    report = verify_wgs84_ranges([(414133.1015, 1697196.8389)])
    assert report["in_wgs84_range"] is False
    assert report["truth_class"] == TRUTH_CONTRADICTED
    assert report["first_outside"] == [414133.1015, 1697196.8389]


def test_verify_wgs84_ranges_empty_is_none():
    assert verify_wgs84_ranges([]) is None


def test_resolve_declaration_agrees_with_content():
    final, codes = resolve_declared_vs_content(
        CLASS_GEOGRAPHIC, TRUTH_VERIFIED_CONTENT, "EPSG:4326")
    assert final == TRUTH_VERIFIED_CONTENT
    assert "CRS_DECLARATION_AGREES_WITH_CONTENT" in codes


def test_resolve_declaration_contradicted_by_content():
    final, codes = resolve_declared_vs_content(
        CLASS_UTM, TRUTH_VERIFIED_CONTENT, "EPSG:4326")
    assert final == TRUTH_CONTRADICTED
    assert "CRS_DECLARATION_CONTRADICTED_BY_CONTENT" in codes


def test_resolve_undetermined_content_falls_to_declared():
    final, _ = resolve_declared_vs_content(
        CLASS_UNKNOWN, TRUTH_UNDETERMINED, "EPSG:32638")
    assert final == TRUTH_DECLARED_ONLY


def test_resolve_no_declaration_content_only():
    final, codes = resolve_declared_vs_content(
        CLASS_UTM, TRUTH_VERIFIED_CONTENT, None)
    assert final == TRUTH_VERIFIED_CONTENT
    assert "CRS_CONTENT_ONLY" in codes


# --- validator integration ---------------------------------------------------

def _write(tmp_path, name: str, body: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(body)
    return str(p)


def test_geojson_validator_emits_content_detection_verified(tmp_path):
    import json

    from geologia.data_layer.validators import validate_file
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [44.2, 15.35]}},
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [44.25, 15.4]}},
    ]}
    path = _write(tmp_path, "sites.geojson",
                  json.dumps(doc).encode("utf-8"))
    report = validate_file(path, "geojson", declared_crs="EPSG:4326")
    codes = [f["code"] for f in report["findings"]]
    assert "CRS_CONTENT_DETECTED" in codes
    detected = next(f for f in report["findings"]
                    if f["code"] == "CRS_CONTENT_DETECTED")
    assert "detected_class=geographic_degrees" in detected["message"]
    assert "truth_class=verified_content" in detected["message"]


def test_geojson_validator_flags_utm_magnitudes_as_contradicted(tmp_path):
    import json

    from geologia.data_layer.validators import validate_file
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point",
                      "coordinates": [414133.1015, 1697196.8389]}},
    ]}
    path = _write(tmp_path, "utm_as_geo.geojson",
                  json.dumps(doc).encode("utf-8"))
    report = validate_file(path, "geojson", declared_crs="EPSG:4326")
    codes = [f["code"] for f in report["findings"]]
    # the existing error-level code still owns the contradiction...
    assert "GEOJSON_BAD_COORDS" in codes
    # ...and the detection statement carries the honest resolution.
    detected = next(f for f in report["findings"]
                    if f["code"] == "CRS_CONTENT_DETECTED")
    assert "truth_class=contradicted_declared" in detected["message"]


def test_csv_validator_detects_utm_columns(tmp_path):
    from geologia.data_layer.validators import validate_file
    body = (b"easting,northing,z\n"
            b"414133.1015,1697196.8389,100.5\n"
            b"419519.2533,1702708.4364,101.5\n")
    path = _write(tmp_path, "utm.csv", body)
    report = validate_file(path, "csv", declared_crs="EPSG:32638")
    detected = next(f for f in report["findings"]
                    if f["code"] == "CRS_CONTENT_DETECTED")
    assert "detected_class=utm_projected_metres" in detected["message"]
    assert "truth_class=verified_content" in detected["message"]


def test_csv_validator_detects_geographic_columns(tmp_path):
    from geologia.data_layer.validators import validate_file
    body = (b"lon,lat,temp_c\n"
            b"44.20,15.35,26.1\n"
            b"44.25,15.40,26.4\n")
    path = _write(tmp_path, "geo.csv", body)
    report = validate_file(path, "csv", declared_crs="EPSG:4326")
    detected = next(f for f in report["findings"]
                    if f["code"] == "CRS_CONTENT_DETECTED")
    assert "detected_class=geographic_degrees" in detected["message"]
    assert "truth_class=verified_content" in detected["message"]


def test_csv_validator_empty_coordinates_undetermined(tmp_path):
    from geologia.data_layer.validators import validate_file
    body = b"name,note\nA,B\n"
    path = _write(tmp_path, "nocoords.csv", body)
    report = validate_file(path, "csv", declared_crs="EPSG:32638")
    detected = next(f for f in report["findings"]
                    if f["code"] == "CRS_CONTENT_DETECTED")
    assert "truth_class=declared_unverified" in detected["message"]
