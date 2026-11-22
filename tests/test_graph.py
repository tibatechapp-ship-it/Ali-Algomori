"""T2.4 — knowledge graph v1: typed entities, evidenced edges, closed pairs."""
import pytest

from geologia.knowledge.graph import (
    edge_fingerprint,
    validate_graph,
)

VALID = {
    "entities": [
        {"entity_id": "ge-ahwar-sst", "type": "geologic_unit",
         "labels": {"ar": "تكوين الأحور", "en": "Ahwar Formation"},
         "term_id": "term-fault"},
        {"entity_id": "ge-marib", "type": "place",
         "labels": {"en": "Marib"}},
        {"entity_id": "ge-sanaa-univ", "type": "institution",
         "labels": {"ar": "جامعة صنعاء", "en": "Sana'a University"}},
        {"entity_id": "ge-pro-doe", "type": "person",
         "labels": {"en": "Dr. Doe"}},
    ],
    "relations": [
        {"relation_id": "rel-1", "type": "located_in",
         "src": "ge-ahwar-sst", "dst": "ge-marib",
         "evidence_unit_id": "ku-abc", "source_id": "src-1"},
        {"relation_id": "rel-2", "type": "works_at",
         "src": "ge-pro-doe", "dst": "ge-sanaa-univ",
         "evidence_unit_id": "ku-def", "source_id": "src-2"},
    ],
}


def test_valid_graph_normalized_with_fingerprints():
    out = validate_graph(VALID)
    assert out["schema"] == "geologia-knowledge-graph/1"
    assert len(out["relations"]) == 2
    for rel in out["relations"]:
        assert len(rel["fingerprint"]) == 64
    assert len(out["graph_fingerprint"]) == 64
    # determinism: same graph -> same fingerprint
    assert validate_graph(VALID)["graph_fingerprint"] == \
        out["graph_fingerprint"]


def test_edge_fingerprint_changes_with_evidence():
    r1 = {"relation_id": "rel-1", "type": "located_in", "src": "a",
          "dst": "b", "evidence_unit_id": "ku-1", "source_id": "s"}
    r2 = dict(r1, evidence_unit_id="ku-2")
    assert edge_fingerprint(r1) != edge_fingerprint(r2)


def test_unauthorized_pair_refused():
    bad = {"entities": VALID["entities"],
           "relations": [{"relation_id": "rel-x", "type": "works_at",
                          "src": "ge-ahwar-sst", "dst": "ge-marib",
                          "evidence_unit_id": "ku-abc", "source_id": "src"}]}
    with pytest.raises(ValueError, match="GRAPH_UNAUTHORIZED_PAIR"):
        validate_graph(bad)


def test_edge_without_evidence_refused():
    bad = {"entities": VALID["entities"],
           "relations": [{"relation_id": "rel-y", "type": "located_in",
                          "src": "ge-ahwar-sst", "dst": "ge-marib",
                          "evidence_unit_id": "not-a-unit",
                          "source_id": "src"}]}
    with pytest.raises(ValueError, match="GRAPH_EDGE_NO_EVIDENCE"):
        validate_graph(bad)


def test_unknown_relation_and_missing_entity_refused():
    with pytest.raises(ValueError, match="GRAPH_UNKNOWN_RELATION"):
        validate_graph({"entities": VALID["entities"],
                        "relations": [{"relation_id": "rel-z",
                                       "type": "teleports_to",
                                       "src": "ge-marib", "dst": "ge-marib",
                                       "evidence_unit_id": "ku-abc",
                                       "source_id": "src"}]})
    with pytest.raises(ValueError, match="GRAPH_MISSING_ENTITY"):
        validate_graph({"entities": VALID["entities"],
                        "relations": [{"relation_id": "rel-w",
                                       "type": "located_in",
                                       "src": "ge-ghost", "dst": "ge-marib",
                                       "evidence_unit_id": "ku-abc",
                                       "source_id": "src"}]})


def test_unknown_entity_type_and_bad_ids_refused():
    with pytest.raises(ValueError, match="GRAPH_UNKNOWN_ENTITY_TYPE"):
        validate_graph({"entities": [{"entity_id": "ge-x",
                                      "type": "dragon",
                                      "labels": {"en": "Smaug"}}],
                        "relations": []})
    with pytest.raises(ValueError, match="GRAPH_BAD_ENTITY_ID"):
        validate_graph({"entities": [{"entity_id": "BAD ID!",
                                      "type": "place",
                                      "labels": {"en": "x"}}],
                        "relations": []})
    with pytest.raises(ValueError, match="GRAPH_BAD_TERM_ID"):
        validate_graph({"entities": [{"entity_id": "ge-x", "type": "place",
                                      "labels": {"en": "x"},
                                      "term_id": "BAD"}],
                        "relations": []})
