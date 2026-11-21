"""T1.1 institutions registry tests: portal linkage integrity + additive migration."""
import json

import pytest

from geologia.knowledge.catalog import _DATA_DIR as KNOWLEDGE_DIR

# The 16 corpus_portal entries of seed_catalog.json (0.3.0) that T1.1 must
# account for: 15 linked to institutions + 1 honestly declared unlinked.
PORTAL_ENTRY_IDS = {
    "portal-usgs-pubs", "portal-nasa-earthdata", "portal-cgs-china",
    "portal-zjuearthdata", "portal-saudi-sgs", "portal-egypt-egsma",
    "portal-yemen-ygsmrb", "portal-ajse-springer", "portal-ajos-sanaa",
    "portal-agu", "portal-gsa", "portal-seg", "portal-aapg",
    "portal-copernicus-egu", "portal-geolsoc-uk", "yemen-red-sea-rift-lit",
}

MANDATORY_FIELDS = [
    "institution_id", "name_en", "name_ar", "country", "institution_type",
    "departments", "research_groups", "repository_urls", "supported_languages",
    "geological_regions", "research_topics", "access_policy", "last_checked",
    "linked_portal_entry_ids", "metadata_confidence",
]

INSTITUTION_TYPES = {
    "survey", "agency", "university", "society", "publisher", "journal", "consortium",
}
ACCESS_POLICIES = {"open", "licensed", "restricted", "unknown"}
METADATA_CONFIDENCE = {"well_known", "to_verify"}

# Additive migration promise: the original 13 entry keys stay in place and in
# order; institution_id (when present) is appended as a 14th key.
ORIGINAL_ENTRY_KEYS = [
    "entry_id", "title_ar", "title_orig", "author", "year", "origin_type",
    "language", "region_scope", "source_url", "license_status", "confidence",
    "notes_ar", "keywords",
]


@pytest.fixture(scope="module")
def doc():
    return json.loads((KNOWLEDGE_DIR / "institutions.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed():
    return json.loads((KNOWLEDGE_DIR / "seed_catalog.json").read_text(encoding="utf-8"))


def test_schema_header_and_unique_ids(doc):
    assert doc["schema"] == "geologia-knowledge-institutions/1"
    assert doc["frozen"] == "2026-11-22"
    assert doc["catalog_version_linked"] == "0.3.0"
    assert isinstance(doc.get("note_ar"), str) and doc["note_ar"].strip()
    ids = [i["institution_id"] for i in doc["institutions"]]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("inst-") for i in ids)


def test_every_institution_has_all_mandatory_fields(doc):
    for inst in doc["institutions"]:
        for field in MANDATORY_FIELDS:
            assert field in inst, f"{inst.get('institution_id')} missing {field}"
        assert inst["institution_type"] in INSTITUTION_TYPES
        assert inst["access_policy"] in ACCESS_POLICIES
        assert inst["metadata_confidence"] in METADATA_CONFIDENCE
        assert len(inst["country"]) == 2 and inst["country"].isupper()
        assert inst["name_en"].strip() and inst["name_ar"].strip()
        assert inst["supported_languages"] and inst["linked_portal_entry_ids"]
        # an empty governed list must carry its documented reason
        gaps = inst.get("gaps_declared", {})
        for list_field in ("departments", "research_groups", "repository_urls"):
            assert isinstance(inst[list_field], list)
            if not inst[list_field]:
                assert isinstance(gaps.get(list_field), str) and gaps[list_field].strip(), (
                    f"{inst['institution_id']}: empty {list_field} without gaps_declared reason"
                )


def test_no_orphan_portal_links(doc, seed):
    catalog_ids = {e["entry_id"] for e in seed["entries"]}
    for inst in doc["institutions"]:
        assert len(inst["linked_portal_entry_ids"]) >= 1
        for portal_id in inst["linked_portal_entry_ids"]:
            assert portal_id in catalog_ids, (
                f"{inst['institution_id']} links unknown portal entry {portal_id}"
            )


def test_bidirectional_entry_to_institution_integrity(doc, seed):
    by_id = {i["institution_id"]: i for i in doc["institutions"]}
    for entry in seed["entries"]:
        inst_id = entry.get("institution_id")
        if inst_id is None:
            continue
        assert inst_id in by_id, f"entry {entry['entry_id']} points to unknown institution"
        linked = by_id[inst_id]["linked_portal_entry_ids"]
        assert entry["entry_id"] in linked


def test_exactly_16_portal_entries_accounted_for(doc, seed):
    portal_entries = {
        e["entry_id"] for e in seed["entries"] if e["origin_type"] == "corpus_portal"
    }
    assert portal_entries == PORTAL_ENTRY_IDS
    linked = {pid for i in doc["institutions"] for pid in i["linked_portal_entry_ids"]}
    unlinked = [u["entry_id"] for u in doc["unlinked_portal_entries"]]
    assert linked | set(unlinked) == portal_entries
    assert not (linked & set(unlinked))
    assert len(linked) == 15 and len(unlinked) == 1
    item = doc["unlinked_portal_entries"][0]
    assert item["entry_id"] == "yemen-red-sea-rift-lit"
    assert item["reason"] == "literature_collection_not_an_institution"


def test_seed_catalog_migration_is_additive(doc, seed):
    entries = seed["entries"]
    assert len(entries) == 71
    carried = [e for e in entries if "institution_id" in e]
    assert len(carried) == 15
    # only corpus_portal entries gained the field; no non-portal entry did
    assert all(e["origin_type"] == "corpus_portal" for e in carried)
    # original fields unchanged in place: same keys, same order, new key last
    for entry in entries:
        if "institution_id" in entry:
            assert list(entry.keys()) == ORIGINAL_ENTRY_KEYS + ["institution_id"]
        else:
            assert list(entry.keys()) == ORIGINAL_ENTRY_KEYS
    # the literature collection carries NO institution_id (honest declaration)
    lit = next(e for e in entries if e["entry_id"] == "yemen-red-sea-rift-lit")
    assert "institution_id" not in lit


def test_last_checked_stays_null_v1(doc):
    for inst in doc["institutions"]:
        assert inst["last_checked"] is None, (
            f"{inst['institution_id']}: last_checked flipped without a verification record"
        )
