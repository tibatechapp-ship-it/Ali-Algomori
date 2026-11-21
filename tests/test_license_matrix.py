"""T1.3 license x purpose matrix tests: coverage, truth table, refusal codes."""
import pytest

from geologia.knowledge.catalog import load_seed_catalog
from geologia.knowledge.licenses import (
    PURPOSES,
    assert_purpose_allowed,
    load_license_matrix,
    purpose_allowed,
)

# Fingerprint of the strictest-defensible default matrix (v1).
EXPECTED = {
    "public_domain": {"indexing": True, "retrieval": True,
                      "training": False, "redistribution": True},
    "open_source": {"indexing": True, "retrieval": True,
                    "training": False, "redistribution": True},
    "open_access": {"indexing": True, "retrieval": True,
                    "training": False, "redistribution": False},
    "open_data": {"indexing": True, "retrieval": True,
                  "training": False, "redistribution": False},
    "free_online": {"indexing": True, "retrieval": True,
                    "training": False, "redistribution": False},
    "company_publication": {"indexing": True, "retrieval": True,
                            "training": False, "redistribution": False},
    "licensed": {"indexing": True, "retrieval": True,
                 "training": False, "redistribution": False},
    "unknown": {"indexing": True, "retrieval": False,
                "training": False, "redistribution": False},
}


def test_matrix_fingerprint_and_schema():
    doc = load_license_matrix()
    assert doc["schema"] == "geologia-license-purpose-matrix/1"
    assert doc["frozen"] == "2026-11-22"
    assert doc["purposes"] == ["indexing", "retrieval", "training", "redistribution"]
    assert doc["overrides"] == {}  # no exceptions documented in v1
    assert doc["note_ar"].strip()


def test_matrix_covers_exactly_the_catalog_license_states():
    catalog_states = {e.license_status for e in load_seed_catalog()}
    assert catalog_states == set(EXPECTED)
    assert set(load_license_matrix()["matrix"]) == catalog_states


def test_every_cell_has_allowed_bool_and_reason():
    for state, cells in load_license_matrix()["matrix"].items():
        assert set(cells) == set(PURPOSES)
        for purpose, cell in cells.items():
            assert isinstance(cell["allowed"], bool), f"{state}/{purpose} allowed not bool"
            assert isinstance(cell["reason"], str) and cell["reason"].strip()


@pytest.mark.parametrize("state", sorted(EXPECTED))
@pytest.mark.parametrize("purpose", ["indexing", "retrieval", "training", "redistribution"])
def test_purpose_allowed_truth_table_matches_matrix(state, purpose):
    allowed, code = purpose_allowed(state, purpose)
    assert allowed is EXPECTED[state][purpose]
    if allowed:
        assert code == "ALLOWED"
    elif state == "unknown":
        assert code == "LICENSE_UNKNOWN_RESTRICTED"
    else:
        assert code == "LICENSE_PURPOSE_NOT_PERMITTED"


def test_training_is_false_for_every_state_in_v1():
    for state, cells in load_license_matrix()["matrix"].items():
        assert cells["training"]["allowed"] is False, (
            f"{state}: training flipped without the ADR-0008 gate record"
        )


def test_unknown_license_state_is_refused_for_every_purpose():
    for purpose in PURPOSES:
        assert purpose_allowed("some-unknown-state", purpose) == (
            False, "LICENSE_STATUS_UNKNOWN_STATE")


def test_unknown_license_retrieval_refused_with_dedicated_code():
    assert purpose_allowed("unknown", "retrieval") == (False, "LICENSE_UNKNOWN_RESTRICTED")
    with pytest.raises(PermissionError, match="LICENSE_UNKNOWN_RESTRICTED"):
        assert_purpose_allowed("unknown", "retrieval")


def test_assert_purpose_allowed_passes_or_raises_with_code():
    assert assert_purpose_allowed("public_domain", "retrieval") is None
    assert assert_purpose_allowed("public_domain", "redistribution") is None
    with pytest.raises(PermissionError, match="LICENSE_PURPOSE_NOT_PERMITTED"):
        assert_purpose_allowed("licensed", "training")
    with pytest.raises(PermissionError, match="LICENSE_PURPOSE_NOT_PERMITTED"):
        assert_purpose_allowed("open_access", "redistribution")


def test_invalid_purpose_is_a_programming_error():
    with pytest.raises(ValueError):
        purpose_allowed("public_domain", "mining")
