"""T1.4 multilingual terms registry tests: sources resolve, names stay unique."""
import json

import pytest

from geologia.knowledge.catalog import (
    _DATA_DIR as KNOWLEDGE_DIR,
    load_digest_documents,
    load_seed_catalog,
)
from geologia.normalize import normalize_text


@pytest.fixture(scope="module")
def doc():
    return json.loads((KNOWLEDGE_DIR / "terms_multilingual.json").read_text(encoding="utf-8"))


def test_schema_and_unique_entity_ids(doc):
    assert doc["schema"] == "geologia-terms-multilingual/1"
    assert doc["frozen"] == "2026-11-22"
    assert isinstance(doc.get("note_ar"), str) and doc["note_ar"].strip()
    ids = [t["entity_id"] for t in doc["terms"]]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("term-") for i in ids)
    assert len(doc["terms"]) == 12


def test_copy_standards_map_is_referenced_only_as_defined(doc):
    standards = doc["copy_standards"]
    assert standards and all(isinstance(v, str) and v.strip() for v in standards.values())
    for term in doc["terms"]:
        for eq in term["equivalences"]:
            assert eq["copy_standard"] == "direct" or eq["copy_standard"] in standards


def test_every_equivalence_has_required_keys_and_confidence(doc):
    for term in doc["terms"]:
        assert term["concept"].strip()
        assert term.get("metadata_confidence") in {"well_known", "to_verify"}
        assert term["equivalences"], f"{term['entity_id']} has no equivalences"
        for eq in term["equivalences"]:
            for key in ("language", "name", "source_id", "copy_standard"):
                assert key in eq and isinstance(eq[key], str) and eq[key].strip()


def test_every_source_id_resolves_to_stored_docs_or_catalog(doc):
    digest_ids = {d["doc_id"] for d in load_digest_documents()}
    catalog_ids = {e.entry_id for e in load_seed_catalog()}
    for term in doc["terms"]:
        for eq in term["equivalences"]:
            assert eq["source_id"] in digest_ids | catalog_ids, (
                f"{term['entity_id']}: {eq['source_id']} does not resolve"
            )


def test_no_two_entities_share_a_normalized_name_per_language(doc):
    seen = {}
    for term in doc["terms"]:
        for eq in term["equivalences"]:
            key = (eq["language"], normalize_text(eq["name"]))
            assert key not in seen, (
                f"{term['entity_id']} duplicates {key} already used by {seen[key]}"
            )
            seen[key] = term["entity_id"]


def test_every_term_is_multilingual(doc):
    for term in doc["terms"]:
        languages = {eq["language"] for eq in term["equivalences"]}
        assert len(languages) >= 2, f"{term['entity_id']} is not multilingual"


def test_seed_terms_present(doc):
    concepts = {t["concept"] for t in doc["terms"]}
    assert {"fault", "fold", "stratigraphy", "geoid", "aquifer", "porosity",
            "permeability", "earthquake", "mineral", "ore", "well log",
            "tectonics"} == concepts


def test_well_known_confidence_requires_verbatim_pairing_in_one_source(doc):
    # only the explicitly bilingual attested pairing may claim well_known
    well_known = [t for t in doc["terms"] if t["metadata_confidence"] == "well_known"]
    assert [t["entity_id"] for t in well_known] == ["term-well-log"]
