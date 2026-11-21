"""T1.2 knowledge unit schema tests: rules, trust inheritance, loader round-trip."""
import json

import pytest

from geologia.knowledge.units import (
    ALLOWED_CONFIDENCE,
    ALLOWED_REVIEW_STATUS,
    KnowledgeUnit,
    load_knowledge_units,
    validate_unit,
)


def valid_unit(**overrides):
    unit = {
        "unit_id": "ku-example-fault-growth",
        "claim": "Example claim tied to a stored structural geology reference.",
        "source_id": "classic-twiss-moores-2007",
        "page_or_section": "chapter 2, faults",
        "doi_or_url": None,
        "language": "en",
        "region": "global",
        "topic": "structural_geology",
        "confidence": "well_known",
        "review_status": "read",
        "license": "licensed",
        "extracted_at_utc": "2026-11-22T10:00:00Z",
        "license_per_purpose": {
            "indexing": True,
            "retrieval": True,
            "training": False,
            "redistribution": False,
        },
    }
    unit.update(overrides)
    return {k: v for k, v in unit.items() if v is not None}


def test_valid_unit_passes_and_returns_normalized_dict():
    out = validate_unit(valid_unit())
    assert out["contradicts"] == []
    model = KnowledgeUnit(**out)
    assert model.unit_id == "ku-example-fault-growth"
    assert model.license_per_purpose["retrieval"] is True


def test_verified_requires_a_recheck_path():
    with pytest.raises(ValueError, match="KU_VERIFIED_NO_RECHECK_PATH"):
        validate_unit(valid_unit(review_status="verified"))
    validate_unit(valid_unit(review_status="verified", doi_or_url="https://example.org/a"))
    validate_unit(valid_unit(
        review_status="verified",
        permanent_ids=[{"id_type": "doi", "id": "10.1000/xyz123"}],
    ))


@pytest.mark.parametrize("field,value,code", [
    ("confidence", "confirmed", "KU_INVALID_CONFIDENCE"),
    ("review_status", "approved", "KU_INVALID_REVIEW_STATUS"),
    ("license", "all_rights_reserved", "KU_INVALID_LICENSE"),
    ("unit_id", "KU_Bad_ID", "KU_INVALID_UNIT_ID"),
    ("claim", "", "KU_INVALID_CLAIM"),
    ("source_id", "", "KU_INVALID_SOURCE_ID"),
    ("page_or_section", "", "KU_INVALID_PAGE_OR_SECTION"),
    ("language", "e", "KU_INVALID_LANGUAGE"),
    ("extracted_at_utc", "2026-11-22 10:00:00", "KU_INVALID_EXTRACTED_AT"),
    ("topic", "  ", "KU_INVALID_TOPIC"),
])
def test_single_field_violations(field, value, code):
    with pytest.raises(ValueError, match=code):
        validate_unit(valid_unit(**{field: value}))


def test_quantitative_without_unit_or_method_is_rejected():
    base = {"value": 1.5, "uncertainty": 0.1}
    with pytest.raises(ValueError, match="KU_INVALID_QUANTITATIVE"):
        validate_unit(valid_unit(quantitative=dict(base)))
    with pytest.raises(ValueError, match="KU_INVALID_QUANTITATIVE"):
        validate_unit(valid_unit(quantitative={**base, "unit": "m"}))
    ok = validate_unit(valid_unit(
        quantitative={**base, "unit": "m", "measurement_method": "field tape"}))
    assert ok["quantitative"]["measurement_method"] == "field tape"


def test_permanent_id_format_rules():
    with pytest.raises(ValueError, match="KU_INVALID_DOI"):
        validate_unit(valid_unit(permanent_ids=[{"id_type": "doi", "id": "not-a-doi"}]))
    with pytest.raises(ValueError, match="KU_INVALID_ORCID"):
        validate_unit(valid_unit(permanent_ids=[{"id_type": "orcid", "id": "1234-5678"}]))
    with pytest.raises(ValueError, match="KU_INVALID_PERMANENT_IDS"):
        validate_unit(valid_unit(permanent_ids=[{"id_type": "isbn", "id": "x"}]))
    validate_unit(valid_unit(
        permanent_ids=[{"id_type": "orcid", "id": "0000-0002-1825-0097"}]))


def test_quote_over_300_chars_is_rejected():
    with pytest.raises(ValueError, match="KU_INVALID_QUOTE"):
        validate_unit(valid_unit(quote={"text": "x" * 301, "page_or_section": "p. 1"}))
    validate_unit(valid_unit(quote={"text": "short stored quote", "page_or_section": "p. 1"}))


def test_license_purpose_more_permissive_than_matrix_is_rejected():
    with pytest.raises(ValueError, match="KU_LICENSE_PURPOSE_EXCEEDS_MATRIX"):
        validate_unit(valid_unit(license="licensed", license_per_purpose={
            "indexing": True, "retrieval": True, "training": True,
            "redistribution": False}))
    with pytest.raises(ValueError, match="KU_LICENSE_PURPOSE_EXCEEDS_MATRIX"):
        validate_unit(valid_unit(license="unknown", license_per_purpose={
            "indexing": True, "retrieval": True, "training": False,
            "redistribution": False}))
    # a documented override is the only honest way through
    validate_unit(valid_unit(
        license="licensed",
        override_source="written grant reference pending verification",
        license_per_purpose={
            "indexing": True, "retrieval": True, "training": True,
            "redistribution": False}))


def test_license_per_purpose_shape_is_enforced():
    with pytest.raises(ValueError, match="KU_INVALID_LICENSE_PER_PURPOSE"):
        validate_unit(valid_unit(license_per_purpose={"indexing": True}))
    with pytest.raises(ValueError, match="KU_INVALID_LICENSE_PER_PURPOSE"):
        validate_unit(valid_unit(license_per_purpose={
            "indexing": True, "retrieval": True, "training": "no",
            "redistribution": False}))


def test_contradicts_and_superseded_by_id_patterns():
    with pytest.raises(ValueError, match="KU_INVALID_CONTRADICTS"):
        validate_unit(valid_unit(contradicts=["not-a-unit-id"]))
    with pytest.raises(ValueError, match="KU_INVALID_SUPERSEDED_BY"):
        validate_unit(valid_unit(superseded_by="ku-BAD"))
    validate_unit(valid_unit(contradicts=["ku-other-claim"], superseded_by="ku-newer-claim"))


def test_unknown_fields_are_rejected():
    with pytest.raises(ValueError, match="KU_INVALID_UNKNOWN_FIELD"):
        validate_unit(valid_unit(rumor="invented content"))


def test_trust_inheritance_is_pinned():
    # fingerprint: widening these sets silently must fail here
    assert ALLOWED_CONFIDENCE == {"well_known", "to_verify"}
    assert ALLOWED_REVIEW_STATUS == {"read", "verified", "unverifiable"}


def test_load_knowledge_units_roundtrip(tmp_path):
    doc = {
        "units": [
            valid_unit(),
            valid_unit(unit_id="ku-example-second", claim="Second stored claim."),
        ]
    }
    path = tmp_path / "units.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    units = load_knowledge_units(path)
    assert [u["unit_id"] for u in units] == [
        "ku-example-fault-growth", "ku-example-second"]
    assert all(u["contradicts"] == [] for u in units)

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps({"units": [valid_unit(unit_id="bad id")]}), encoding="utf-8")
    with pytest.raises(ValueError, match="KU_INVALID_"):
        load_knowledge_units(bad_path)

    wrong_path = tmp_path / "wrong.json"
    wrong_path.write_text(json.dumps({"nope": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="KU_INVALID_FILE"):
        load_knowledge_units(wrong_path)
