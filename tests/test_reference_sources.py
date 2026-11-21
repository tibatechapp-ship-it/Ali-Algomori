"""Reference source & geoid-model registry tests (PR #7 mirror).

The registries define the OFFICIAL sources and the acceptance gates a
vertical datum grid must pass before ANY vertical-transformation claim
can exist in GEOLOGIA. These tests protect two things:

1. integrity: schema, unique ids, mandatory fields, cross-links between
   the two registries, gate completeness;
2. honesty: grids NOT embedded, transformations NOT implemented, no
   independent verification values yet. Flipping any of those claims
   without shipping the real evidence must fail CI — never pass silently.

CI green does NOT certify geological validity: the EPSG codes re-proved
here (when pyproj is present) are registry labels, not geoid values.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from geologia.data_layer.readers import capabilities

REF = (Path(__file__).parent.parent / "src" / "geologia" / "data"
       / "reference")
SOURCES = json.loads((REF / "reference_sources.json").read_text(
    encoding="utf-8"))
GEOID = json.loads((REF / "geoid_model_reference.json").read_text(
    encoding="utf-8"))

_cap = capabilities()
req_pyproj = pytest.mark.skipif(
    not _cap["pyproj"],
    reason="pyproj absent — EPSG re-proof against the shipped database "
           "cannot run and will NOT be claimed")

REQUIRED_SOURCE_FIELDS = ("id", "authority", "organization", "url",
                          "hosts", "languages", "last_checked", "policy")
VALID_AUTHORITIES = {"primary", "secondary_distribution", "literature"}
REQUIRED_GATES = ("grid_file_sha256", "grid_license", "tide_system",
                  "grid_geometry", "interpolation_method", "crs_pair",
                  "validity_domain", "independent_verification_values")


# --- integrity ----------------------------------------------------------------
def test_source_registry_parses_with_unique_ids_and_fields():
    assert SOURCES["schema"] == "geologia-reference-sources/1"
    ids = [s["id"] for s in SOURCES["sources"]]
    assert len(ids) == len(set(ids)), f"duplicate source ids: {ids}"
    for s in SOURCES["sources"]:
        missing = [f for f in REQUIRED_SOURCE_FIELDS if f not in s]
        assert not missing, f"{s.get('id')}: missing fields {missing}"
        assert s["authority"] in VALID_AUTHORITIES
    authorities = {s["authority"] for s in SOURCES["sources"]}
    assert "primary" in authorities, "the hierarchy must name a primary"


def test_source_registry_keeps_the_reception_gate_absolute():
    policy = SOURCES["intake_policy"]["gate"]
    assert "check_upload" in policy and "prove_file" in policy
    # no trusted-site exception: the policy must forbid shortcuts explicitly
    assert "no exceptions" in policy


def test_geoid_registry_parses_with_gate_completeness():
    assert GEOID["schema"] == "geologia-reference-geoid-models/1"
    gates = {g["gate"] for g in GEOID["acceptance_gates"]}
    assert gates == set(REQUIRED_GATES), (
        f"gate set drift: missing={set(REQUIRED_GATES) - gates}, "
        f"extra={gates - set(REQUIRED_GATES)}")
    for g in GEOID["acceptance_gates"]:
        assert g["current_status"], f"gate {g['gate']}: no status"


def test_model_ids_unique_and_sources_cross_linked():
    ids = [m["id"] for m in GEOID["models"]]
    assert len(ids) == len(set(ids)), f"duplicate model ids: {ids}"
    known = {s["id"] for s in SOURCES["sources"]}
    for m in GEOID["models"]:
        assert m["primary_source"] in known, (
            f"{m['id']}: unknown primary source {m['primary_source']}")
        assert m["distribution_source"] in known, (
            f"{m['id']}: unknown distribution source")


def test_epsg_pairings_pinned_against_drift():
    """The exact pairing verified from proj.db on 2026-11-22. If these
    change, the change must be a new verification — not silent drift."""
    by_id = {m["id"]: m for m in GEOID["models"]}
    assert by_id["egm96"]["crs_epsg"] == 5773
    assert by_id["egm96"]["datum_epsg"] == 5171
    assert by_id["egm2008"]["crs_epsg"] == 3855
    assert by_id["egm2008"]["datum_epsg"] == 1027
    assert by_id["egm96"]["grid_resolution_arcmin"] == 15
    assert by_id["egm2008"]["grid_resolution_arcmin"] == 2.5


def test_honesty_fingerprint_no_grid_no_values_no_transform():
    """THE test of this file: the registries must CLAIM NOTHING they do
    not have. A future PR that flips grid_embedded to True, or fills a
    sha256, or marks the transformation implemented — without shipping
    the actual grid, its license, and independent verification values —
    fails here first."""
    for m in GEOID["models"]:
        assert m["status"] == "documented_not_embedded", m["id"]
        assert m["grid_embedded"] is False, m["id"]
        assert m["grid_file_sha256"] is None, m["id"]
        assert m["grid_license"] is None, m["id"]
        assert m["tide_system"] is None, m["id"]
        assert m["independent_verification_values"] == [], m["id"]
    impl = GEOID["implementation_status"]
    assert impl["vertical_transformation"] == "not_implemented"
    assert "refusal" in impl["agent_rule"] or "refuse" in impl["agent_rule"]


def test_mirror_note_protects_the_merge_wins_rule():
    for doc, name in ((SOURCES, "reference_sources"),
                      (GEOID, "geoid_model_reference")):
        note = doc.get("mirror_note", "")
        assert "PR #7" in note, f"{name}: mirror provenance removed"
        assert "المرجع" in note, f"{name}: merge-wins rule removed"


# --- re-proof from the live EPSG database (pyproj-gated) -----------------------
@req_pyproj
def test_epsg_codes_reproved_from_shipped_proj_database():
    from pyproj import CRS

    for m in GEOID["models"]:
        crs = CRS.from_epsg(m["crs_epsg"])
        assert crs.name == m["crs_name_verified"], m["id"]
        assert crs.type_name == "Vertical CRS", m["id"]
        assert crs.datum.name == m["datum_name_verified"], m["id"]
        axis = crs.axis_info[0]
        assert axis.unit_name == "metre", m["id"]


@req_pyproj
def test_datum_entities_reproved_from_proj_db_tables():
    """Datum ENTITY codes are a different table than CRS codes — the same
    query family that proved EPSG:1027 (EGM2008 geoid) is not 5171."""
    import pyproj.datadir
    db = Path(pyproj.datadir.get_data_dir()) / "proj.db"
    with sqlite3.connect(str(db)) as con:
        datum_rows = {(a, c, n) for a, c, n in con.execute(
            "SELECT auth_name, code, name FROM vertical_datum")}
        crs_codes = {(a, c) for a, c in con.execute(
            "SELECT auth_name, code FROM vertical_crs")}
    assert ("EPSG", 5171, "EGM96 geoid") in datum_rows
    assert ("EPSG", 1027, "EGM2008 geoid") in datum_rows
    # the datum/entity distinction is structural, not cosmetic: a datum
    # code must never appear as a CRS code in the same registry
    assert ("EPSG", 5171) not in crs_codes
    assert ("EPSG", 1027) not in crs_codes
