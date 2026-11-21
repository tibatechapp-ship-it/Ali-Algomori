"""Reference corpus tests: every golden file against its FROZEN expected
results from dataset_manifest.json.

This is the "reference dataset with expected results" the data layer is
required to prove itself against: not just "does it fail", but "does it
return exactly the reading we pinned at construction time". The manifest
pins: sha256 + size of every file, validator status, mandatory codes,
reader facts (shape/CRS/extent/rows) and vertical classification.

CI green does NOT certify geological validity — these tests certify that
the code does what the reference says it must do, byte for byte.

Regenerate the corpus only with scripts/make_reference_corpus.py.
"""
import json
import math
from pathlib import Path

import pytest

from geologia.data_layer.evidence import prove_file
from geologia.data_layer.readers import capabilities
from geologia.data_layer.reference import verify_reference_dir

REF = Path(__file__).parent / "data" / "reference"
MANIFEST = json.loads((REF / "dataset_manifest.json").read_text(
    encoding="utf-8"))
DTYPE = {"geotiff": "tiff", "gpkg": "gpkg", "las": "las"}

_ENGINES = capabilities()
_MISSING = [k for k in ("lasio", "tifffile", "pyproj") if not _ENGINES[k]]
pytestmark = pytest.mark.skipif(
    bool(_MISSING),
    reason="specialized engines missing: " + ", ".join(_MISSING)
    + " — real-reader verification cannot run and will NOT be claimed")


def codes(report):
    return {f["code"] for f in report["findings"]}


def evidence_codes(report):
    ev = report.get("evidence") or {}
    return {i["code"] for lvl in ("read", "verified", "unverifiable")
            for i in ev.get(lvl, [])}


# --- corpus integrity: the reference itself must not drift -------------------
# (also covered engine-free by test_transformations.test_reference_dir_intact;
#  this variant runs inside the engine gate so a full pass asserts BOTH the
#  bytes and the readings together)
def test_reference_corpus_files_are_byte_identical_to_manifest():
    result = verify_reference_dir(str(REF))
    assert result["ok"], result["findings"]
    assert result["checked"] == len(MANIFEST["files"])


# --- the core: every file vs its frozen expectations -------------------------
@pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
def test_file_matches_frozen_expected_results(name):
    entry = MANIFEST["files"][name]
    rep = prove_file(str(REF / name), dtype=DTYPE[entry["kind"]])
    exp = entry["expected"]

    assert rep["status"] == exp["status"], (
        f"{name}: status {rep['status']} != {exp['status']}, "
        f"codes={sorted(codes(rep))}")

    got = codes(rep) | evidence_codes(rep)
    missing = set(exp["codes_min"]) - got
    assert not missing, f"{name}: mandatory codes missing: {missing}"

    if exp.get("reader"):
        _assert_reader_subset(name, rep.get("reader"), exp["reader"])


def _assert_reader_subset(name, reader, expected):
    assert reader is not None, f"{name}: reader produced no data"
    for key, want in expected.items():
        if key == "features":
            for table, tfacts in want.items():
                for fkey, fval in tfacts.items():
                    got_val = reader["features"][table][fkey]
                    assert got_val == fval, (
                        f"{name}: {table}.{fkey} = {got_val} != {fval}")
        elif key == "extent":
            for corner, cval in want.items():
                assert math.isclose(reader["extent"][corner], cval,
                                    abs_tol=1e-9), (
                    f"{name}: extent.{corner} = {reader['extent'][corner]} "
                    f"!= {cval}")
        else:
            assert reader[key] == want, (
                f"{name}: reader.{key} = {reader[key]!r} != {want!r}")


# --- vertical expectations pinned in the manifest ----------------------------
@pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
def test_vertical_classification_matches_manifest(name):
    entry = MANIFEST["files"][name]
    want = entry["expected"].get("vertical")
    if want is None:
        pytest.skip(f"{name}: no vertical expectation pinned")
    # vertical classification is re-derived from the raw GeoKeys
    from geologia.data_layer.vertical import classify_vertical_geokeys
    from geologia.data_layer.readers import parse_geokeys
    if entry["kind"] != "geotiff":
        pytest.skip("vertical geokeys only apply to GeoTIFF")
    import tifffile
    with tifffile.TiffFile(str(REF / name)) as tf:
        page = tf.pages[0]
        raw = page.tags[34735].value
    gk = parse_geokeys(raw)
    v = classify_vertical_geokeys(gk)
    assert v is not None
    assert v["cs"] == want["cs"], f"{name}: vertical cs {v['cs']} != {want['cs']}"
    assert v["datum"] == want["datum"]
    assert v["units"] == want["units"]


# --- honesty invariants on the corpus ----------------------------------------
def test_valid_files_are_proven_or_gapped_never_refused():
    for name, entry in MANIFEST["files"].items():
        if entry["expected"]["status"] != "pass":
            continue
        rep = prove_file(str(REF / name), dtype=DTYPE[entry["kind"]])
        assert rep["proof_status"] in ("proven", "proven_with_unverified_claims")


def test_invalid_files_are_refused():
    for name, entry in MANIFEST["files"].items():
        if entry["expected"]["status"] == "fail":
            rep = prove_file(str(REF / name), dtype=DTYPE[entry["kind"]])
            assert rep["proof_status"] == "refused", name


def test_las_files_always_report_unverifiable_crs_and_datum():
    """LAS 1.2/2.0 carries no CRS and no depth datum — the layer must SAY so."""
    from geologia.data_layer.readers import read_las
    r = read_las(str(REF / "ref_las_valid.las"))
    unv = {i["code"] for i in r["evidence"]["unverifiable"]}
    assert "CRS_NONE_DECLARED" in unv
    assert "VERT_DEPTH_DATUM_UNDECLARED" in unv
