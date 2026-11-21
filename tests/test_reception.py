"""v0.5.0 file-reception security tests: the gate before a byte becomes data.

Four dimensions, each with exact refusal codes:
  size limits / content sniffing / archive safety / hygiene (names, NUL,
  giant lines, TIFF metadata). Reception answers "is this safe to accept?",
  NOT "is the science right?" — that stays behind the certification gate.
"""
import stat
import zipfile
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
# 1. filename sanitization (incl. bidi marks — an Arabic-platform must)
# ---------------------------------------------------------------------------
def test_sanitize_strips_path_components():
    from geologia.data_layer.reception import sanitize_filename
    safe, flags = sanitize_filename("..\\..\\etc\\wells.csv")
    assert safe == "wells.csv"
    assert "path_components_removed" in flags


def test_sanitize_strips_bidi_and_hidden_marks():
    from geologia.data_layer.reception import sanitize_filename
    # LRM + RLO inside the name: visual reordering is impossible after intake
    tricky = "we\u202ells\u200f.csv"
    safe, flags = sanitize_filename(tricky)
    assert safe == "wells.csv"
    assert "bidi_or_hidden_marks_removed" in flags


def test_sanitize_prefixes_reserved_windows_names():
    from geologia.data_layer.reception import sanitize_filename
    safe, flags = sanitize_filename("con.las")
    assert safe == "_con.las"
    assert "reserved_name_prefixed" in flags


def test_sanitize_refuses_names_that_reduce_to_nothing():
    from geologia.data_layer.reception import sanitize_filename
    safe, flags = sanitize_filename("\u200b\u200c\u200f")
    assert safe == ""
    assert "refused_empty_after_sanitization" in flags


def test_sanitize_truncates_giant_names_but_keeps_extension():
    from geologia.data_layer.reception import sanitize_filename
    safe, _ = sanitize_filename("x" * 400 + ".las")
    assert len(safe.encode("utf-8")) <= 120
    assert safe.endswith(".las")


def test_sanitize_leaves_clean_names_untouched():
    from geologia.data_layer.reception import sanitize_filename
    safe, flags = sanitize_filename("sanaa_wells_2026.csv")
    assert safe == "sanaa_wells_2026.csv"
    assert flags == []


# ---------------------------------------------------------------------------
# 2. content sniffing — the extension is never trusted
# ---------------------------------------------------------------------------
def test_sniff_identifies_magic_bytes(tmp_path):
    from geologia.data_layer.reception import sniff_content
    tif = tmp_path / "a.tif"
    tif.write_bytes(b"II*\x00" + b"\x00" * 32)
    assert sniff_content(tif)[0] == "tiff"
    zp = tmp_path / "b.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("x.csv", "a,b\n1,2\n")
    assert sniff_content(zp)[0] == "zip"
    txt = tmp_path / "c.las"
    txt.write_text("~Version Information\n", encoding="utf-8")
    assert sniff_content(txt)[0] == "text"
    junk = tmp_path / "d.las"
    junk.write_bytes(b"\xde\xad\xbe\xef" * 16)
    assert sniff_content(junk)[0] == "binary_unknown"


def test_check_upload_refuses_binary_junk_claiming_to_be_las(tmp_path):
    from geologia.data_layer.reception import check_upload
    junk = tmp_path / "junk.las"
    junk.write_bytes(b"\xde\xad\xbe\xef" * 64)
    report = check_upload(str(junk), dtype="las")
    assert report["status"] == "rejected"
    assert "SEC_UNKNOWN_MAGIC" in codes(report)


def test_check_upload_refuses_text_content_declared_as_tiff(tmp_path):
    from geologia.data_layer.reception import check_upload
    fake = tmp_path / "fake.tif"
    fake.write_text("this is not a tiff", encoding="utf-8")
    report = check_upload(str(fake), dtype="tiff")
    assert report["status"] == "rejected"
    assert "SEC_EXT_MISMATCH" in codes(report)


def test_check_upload_refuses_html_svg_in_data_upload(tmp_path):
    from geologia.data_layer.reception import check_upload
    evil = tmp_path / "profile.csv"
    evil.write_text("<svg onload=alert(1)></svg>", encoding="utf-8")
    report = check_upload(str(evil), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_HTML_EMBEDDED" in codes(report)


def test_check_upload_flags_nul_in_text(tmp_path):
    from geologia.data_layer.reception import check_upload
    bad = tmp_path / "wells.csv"
    bad.write_bytes(b"well,lat,lon\na,15.3\x00,44.2\n")
    report = check_upload(str(bad), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_CONTROL_CHARS" in codes(report)


def test_check_upload_flags_giant_line(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_MAX_LINE_BYTES", "1024")
    from geologia.data_layer.reception import check_upload
    big = tmp_path / "wells.csv"
    big.write_text("well,lat,lon\n" + "x" * 4096 + ",15.3,44.2\n",
                   encoding="utf-8")
    report = check_upload(str(big), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_LINE_TOO_LONG" in codes(report)


# ---------------------------------------------------------------------------
# 3. size limits
# ---------------------------------------------------------------------------
def test_check_upload_enforces_per_file_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_MAX_UPLOAD_BYTES", "100")
    from geologia.data_layer.reception import check_upload
    f = tmp_path / "wells.csv"
    f.write_text("well,lat,lon\n" + "sanaa-01,15.35,44.20\n" * 20,
                 encoding="utf-8")  # > 100 bytes, valid CSV content
    report = check_upload(str(f), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_TOO_LARGE" in codes(report)
    assert report["sha256"] is None  # oversized content is not even hashed


def test_check_upload_refuses_empty_file(tmp_path):
    from geologia.data_layer.reception import check_upload
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    report = check_upload(str(f), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_EMPTY_FILE" in codes(report)


# ---------------------------------------------------------------------------
# 4. archive safety — structural analysis only, never extracted to disk
# ---------------------------------------------------------------------------
def test_zip_bomb_corpus_is_refused():
    from geologia.data_layer.reception import check_upload
    report = check_upload(str(DATA / "golden_archive_bomb.zip"), dtype="zip")
    assert report["status"] == "rejected"
    assert "SEC_ZIP_BOMB" in codes(report)


def test_path_traversal_member_is_refused():
    from geologia.data_layer.reception import check_upload
    report = check_upload(str(DATA / "golden_archive_traversal.zip"), dtype="zip")
    assert report["status"] == "rejected"
    assert "SEC_PATH_TRAVERSAL" in codes(report)


def test_clean_archive_passes_scan_as_needs_review():
    from geologia.data_layer.reception import check_upload
    report = check_upload(str(DATA / "golden_archive_ok.zip"), dtype="zip")
    # archive structure is safe, but member CONTENT was not validated:
    # honest status is needs_review, not accepted
    assert report["status"] == "needs_review"
    assert "SEC_ARCHIVE_OK" in codes(report)


def test_symlink_member_is_refused(tmp_path):
    from geologia.data_layer.reception import check_upload
    zp = tmp_path / "link.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        info = zipfile.ZipInfo("danger_link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    report = check_upload(str(zp), dtype="zip")
    assert report["status"] == "rejected"
    assert "SEC_ARCHIVE_SYMLINK" in codes(report)


def test_corrupt_zip_is_refused_not_crashed(tmp_path):
    from geologia.data_layer.reception import check_upload
    zp = tmp_path / "broken.zip"
    zp.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    report = check_upload(str(zp), dtype="zip")
    assert report["status"] == "rejected"
    assert "SEC_ARCHIVE_CORRUPT" in codes(report)


def test_entry_cap_refuses_many_member_archives(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_MAX_ARCHIVE_ENTRIES", "2")
    from geologia.data_layer.reception import check_upload
    zp = tmp_path / "many.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.csv", "a,b\n1,2\n")
    report = check_upload(str(zp), dtype="zip")
    assert report["status"] == "rejected"
    assert "SEC_ZIP_BOMB" in codes(report)


# ---------------------------------------------------------------------------
# 5. TIFF metadata: presence reporting + structural stripping
# ---------------------------------------------------------------------------
def test_scan_tiff_metadata_reports_or_reports_none():
    from geologia.data_layer.reception import scan_tiff_metadata
    present, findings = scan_tiff_metadata(DATA / "golden_dem_with_meta.tif")
    assert set(present.values()) == {"Software", "Copyright"}
    assert findings[0]["code"] == "META_PRESENT"
    clean, findings2 = scan_tiff_metadata(DATA / "golden_dem_tile.tif")
    assert clean == {}
    assert findings2[0]["code"] == "META_NONE"


def test_strip_tiff_drops_metadata_keeps_geo_and_stays_valid(tmp_path):
    from geologia.data_layer.reception import strip_tiff_auxiliary_tags
    from geologia.data_layer.validators import validate_file
    out = tmp_path / "stripped.tif"
    result = strip_tiff_auxiliary_tags(DATA / "golden_dem_with_meta.tif", out)
    assert result["dropped_tags"] == ["305:Software", "33432:Copyright"]
    assert result["kept_geo"] is True
    report = validate_file(str(out), "tiff")
    assert report["status"] == "pass"
    assert "TIFF_GEO_TAGS" in codes(report)


def test_strip_raises_on_non_tiff(tmp_path):
    from geologia.data_layer.reception import strip_tiff_auxiliary_tags
    not_tiff = tmp_path / "x.tif"
    not_tiff.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        strip_tiff_auxiliary_tags(not_tiff, tmp_path / "out.tif")


# ---------------------------------------------------------------------------
# 6. end-to-end: accepted reception -> registered -> validated
# ---------------------------------------------------------------------------
def test_accepted_upload_carries_full_evidence(store):
    from geologia.data_layer import records as ds
    from geologia.data_layer.reception import check_upload
    report = check_upload(str(DATA / "golden_wells.csv"), dtype="csv",
                          declared_crs="EPSG:4326")
    assert report["status"] == "accepted"
    assert report["sanitized_name"] == "golden_wells.csv"
    assert report["content_report"]["status"] == "pass"
    assert len(report["sha256"]) == 64
    # the accepted byte stream registers and validates with the same hash
    rec = ds.register_dataset("آبار مقبولة", str(DATA / "golden_wells.csv"),
                              dtype="csv", declared_crs="EPSG:4326")
    assert rec["sha256"] == report["sha256"]


def test_corrupted_upload_is_rejected_before_registration(store):
    from geologia.data_layer.reception import check_upload
    report = check_upload(str(DATA / "golden_csv_id_conflict.csv"), dtype="csv")
    assert report["status"] == "rejected"
    assert "SEC_CONTENT_INVALID" in codes(report)
