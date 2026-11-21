"""Frozen transformation + reference-integrity tests.

The control points in geologia/data/reference/transformations.json were
computed once and frozen by hand. If the installed engine disagrees beyond
tolerance, that is XFORM_MISMATCH — a hard refusal to trust transformations,
never a silent recalibration of the reference.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

from geologia.data_layer.reference import (load_transformations,
                                           transformations_fingerprint,
                                           verify_reference_dir,
                                           verify_transformations)

REF = Path(__file__).parent / "data" / "reference"
PKG_REF = Path(__file__).parents[1] / "src" / "geologia" / "data" / "reference"


def _has_pyproj():
    try:
        import pyproj  # noqa: F401
        return True
    except ImportError:
        return False


requires_pyproj = pytest.mark.skipif(
    not _has_pyproj(),
    reason="pyproj absent — transformation validity cannot be re-proven "
           "and will NOT be claimed")


# --- frozen reference structure -------------------------------------------------
def test_transformations_file_is_wellformed():
    ref = load_transformations()
    assert ref["schema"] == "geologia-reference-transformations/1"
    assert len(ref["transformations"]) >= 4
    for t in ref["transformations"]:
        for key in ("name", "from_crs", "to_crs", "x", "y",
                    "expected_x", "expected_y", "tol", "tol_unit"):
            assert key in t, f"{t.get('name')} missing {key}"


def test_fingerprint_is_stable_sha256():
    fp1 = transformations_fingerprint()
    fp2 = transformations_fingerprint()
    assert fp1 == fp2 and len(fp1) == 64


@requires_pyproj
def test_all_frozen_control_points_reproven():
    res = verify_transformations()
    assert res["ok"], res["findings"]
    assert res["checked"] == res["total"]
    assert res["checked"] >= 4
    verified = [i for i in res["evidence"]["verified"]
                if i["code"] == "XFORM_OK"]
    assert len(verified) == res["total"]
    for i in verified:
        assert "pyproj" in i["check"]


@requires_pyproj
def test_engine_disagreement_is_a_hard_error():
    ref = load_transformations()
    broken = json.loads(json.dumps(ref))
    broken["transformations"][0]["expected_x"] += 100.0  # lie about Riyadh
    res = verify_transformations(transformations=broken)
    assert res["ok"] is False
    codes_ = [f["code"] for f in res["findings"]]
    assert "XFORM_MISMATCH" in codes_


@requires_pyproj
def test_engine_failure_is_not_silently_swallowed():
    ref = load_transformations()
    broken = json.loads(json.dumps(ref))
    broken["transformations"][0]["from_crs"] = "EPSG:NOTACRS"
    res = verify_transformations(transformations=broken)
    assert res["ok"] is False


def test_engine_absence_is_unverifiable_not_pass(monkeypatch):
    """Without pyproj the layer must SAY it cannot confirm, never claim ok
    as if the checks ran."""
    monkeypatch.setitem(sys.modules, "pyproj", None)
    res = verify_transformations()
    assert res["checked"] == 0
    unv = [i["code"] for i in res["evidence"]["unverifiable"]]
    assert "XFORM_ENGINE_ABSENT" in unv
    codes_ = [f["code"] for f in res["findings"]]
    assert "XFORM_MISMATCH" not in codes_


# --- reference dir integrity ------------------------------------------------------
def test_reference_dir_intact():
    res = verify_reference_dir(str(REF))
    assert res["ok"] is True
    assert res["checked"] == len(json.loads(
        (REF / "dataset_manifest.json").read_text(encoding="utf-8"))["files"])


def test_reference_dir_detects_missing_manifest(tmp_path):
    res = verify_reference_dir(str(tmp_path))
    assert res["ok"] is False
    codes_ = [f["code"] for f in res["findings"]]
    assert "REF_MANIFEST_INVALID" in codes_


def test_reference_dir_detects_tampered_file(tmp_path):
    shutil.copytree(REF, tmp_path / "ref")
    victim = tmp_path / "ref" / "ref_las_valid.las"
    data = bytearray(victim.read_bytes())
    data[0] = (data[0] + 1) % 256  # flip one byte
    victim.write_bytes(bytes(data))
    res = verify_reference_dir(str(tmp_path / "ref"))
    assert res["ok"] is False
    codes_ = [f["code"] for f in res["findings"]]
    assert "REF_HASH_MISMATCH" in codes_


def test_reference_dir_detects_missing_file(tmp_path):
    shutil.copytree(REF, tmp_path / "ref")
    (tmp_path / "ref" / "ref_las_valid.las").unlink()
    res = verify_reference_dir(str(tmp_path / "ref"))
    assert res["ok"] is False
    codes_ = [f["code"] for f in res["findings"]]
    assert "REF_FILE_MISSING" in codes_


def test_reference_honesty_about_scope():
    """The corpus certifies code paths, NOT geology — this must be stated."""
    res = verify_reference_dir(str(REF))
    unv = [i for i in res["evidence"]["unverifiable"]
           if i["code"] == "REF_CORPUS_SCOPE"]
    assert unv and "geology" in unv[0]["reason"]
