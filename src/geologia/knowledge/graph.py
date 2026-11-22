# Geoscience Knowledge Graph schema v1 (T2.4) — closes Gap 13.
#
# Design rules from the approved plan and ADR-0008:
# - Neutral IDs bound to the multilingual terms registry (T1.4): an entity may
#   carry a term_id; the ORIGINAL label and the translation coexist and the
#   translation never outweighs the original.
# - NO edge without evidence: every relation carries a knowledge-unit id
#   (schema v1) plus its source id, and an edge fingerprint so the edge itself
#   is tamper-evident.
# - Authorized type pairs are a CLOSED map: an unauthorized pair is a refusal,
#   not a warning (hallucination gate at the schema level).
from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List, Optional, Tuple

ENTITY_TYPES = frozenset({
    "person", "institution", "place", "geologic_unit", "method", "source",
})

# relation type -> allowed (source_type, destination_type) pairs (closed map)
RELATION_PAIRS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "works_at": (("person", "institution"),),
    "member_of": (("person", "institution"),),
    "located_in": (("geologic_unit", "place"), ("place", "place")),
    "part_of": (("geologic_unit", "geologic_unit"),
                ("institution", "institution")),
    "overlies": (("geologic_unit", "geologic_unit"),),
    "intrudes_into": (("geologic_unit", "geologic_unit"),),
    "measured_with": (("geologic_unit", "method"), ("place", "method")),
    "asserted_in": (("person", "source"), ("geologic_unit", "source"),
                    ("institution", "source")),
}

_ENTITY_ID_RE = re.compile(r"^ge-[a-z0-9-]+$")
_RELATION_ID_RE = re.compile(r"^rel-[a-z0-9-]+$")
_UNIT_ID_RE = re.compile(r"^ku-[0-9a-z-]+$")
_TERM_ID_RE = re.compile(r"^term-[a-z0-9-]+$")
_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def _fail(code: str, detail: str) -> None:
    raise ValueError(f"{code}: {detail}")


def edge_fingerprint(rel: dict) -> str:
    """Tamper-evident fingerprint of one edge (sha256 of its canonical core)."""
    core = {
        "relation_id": rel["relation_id"], "type": rel["type"],
        "src": rel["src"], "dst": rel["dst"],
        "evidence_unit_id": rel["evidence_unit_id"],
        "source_id": rel["source_id"],
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_entity(entity: dict) -> dict:
    if not isinstance(entity, dict):
        _fail("GRAPH_INVALID_ENTITY", "entity must be an object")
    eid = entity.get("entity_id")
    if not isinstance(eid, str) or not _ENTITY_ID_RE.match(eid):
        _fail("GRAPH_BAD_ENTITY_ID",
              f"entity_id must match ^ge-[a-z0-9-]+$, got {eid!r}")
    etype = entity.get("type")
    if etype not in ENTITY_TYPES:
        _fail("GRAPH_UNKNOWN_ENTITY_TYPE",
              f"type {etype!r} not in {sorted(ENTITY_TYPES)}")
    labels = entity.get("labels")
    if not isinstance(labels, dict) or not labels:
        _fail("GRAPH_INVALID_LABELS",
              "labels must be a non-empty {language: name} object")
    for lang, name in labels.items():
        if not _LANG_RE.match(str(lang)) or not isinstance(name, str) \
                or not name.strip():
            _fail("GRAPH_INVALID_LABELS",
                  f"label {lang!r} must map to a non-empty name string")
    term_id = entity.get("term_id")
    if term_id is not None and (not isinstance(term_id, str)
                                or not _TERM_ID_RE.match(term_id)):
        _fail("GRAPH_BAD_TERM_ID",
              f"term_id must match ^term-[a-z0-9-]+$, got {term_id!r}")
    out = {"entity_id": eid, "type": etype, "labels": dict(labels)}
    if term_id is not None:
        out["term_id"] = term_id
    return out


def _validate_relation(rel: dict, types: Dict[str, str]) -> dict:
    if not isinstance(rel, dict):
        _fail("GRAPH_INVALID_RELATION", "relation must be an object")
    rid = rel.get("relation_id")
    if not isinstance(rid, str) or not _RELATION_ID_RE.match(rid):
        _fail("GRAPH_BAD_EDGE_ID",
              f"relation_id must match ^rel-[a-z0-9-]+$, got {rid!r}")
    rtype = rel.get("type")
    if rtype not in RELATION_PAIRS:
        _fail("GRAPH_UNKNOWN_RELATION",
              f"relation type {rtype!r} not in {sorted(RELATION_PAIRS)}")
    src, dst = rel.get("src"), rel.get("dst")
    for node in (src, dst):
        if not isinstance(node, str) or node not in types:
            _fail("GRAPH_MISSING_ENTITY",
                  f"edge {rid!r} references unknown entity {node!r}")
    if (types[src], types[dst]) not in RELATION_PAIRS[rtype]:
        _fail("GRAPH_UNAUTHORIZED_PAIR",
              f"relation {rtype!r} does not allow "
              f"({types[src]!r} -> {types[dst]!r})")
    ev = rel.get("evidence_unit_id")
    if not isinstance(ev, str) or not _UNIT_ID_RE.match(ev):
        _fail("GRAPH_EDGE_NO_EVIDENCE",
              "every edge needs evidence_unit_id of a schema-v1 knowledge "
              "unit - an unevidenced relation is a refusal, not a warning")
    source_id = rel.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        _fail("GRAPH_EDGE_NO_EVIDENCE",
              "every edge needs the source_id that backs it")
    out = {"relation_id": rid, "type": rtype, "src": src, "dst": dst,
           "evidence_unit_id": ev, "source_id": source_id}
    out["fingerprint"] = edge_fingerprint(out)
    return out


def validate_graph(doc: dict) -> dict:
    """Validate {entities, relations}; return the normalized graph with
    per-edge fingerprints and a whole-graph fingerprint."""
    if not isinstance(doc, dict):
        _fail("GRAPH_INVALID_DOC", "graph must be a JSON object")
    entities_raw = doc.get("entities")
    relations_raw = doc.get("relations")
    if not isinstance(entities_raw, list) or not isinstance(relations_raw,
                                                           list):
        _fail("GRAPH_INVALID_DOC",
              "expected {'entities': [...], 'relations': [...]}")
    entities = [_validate_entity(e) for e in entities_raw]
    types = {e["entity_id"]: e["type"] for e in entities}
    if len(types) != len(entities):
        _fail("GRAPH_DUPLICATE_ENTITY_ID", "entity ids must be unique")
    relations = [_validate_relation(r, types) for r in relations_raw]
    seen = set()
    for r in relations:
        if r["relation_id"] in seen:
            _fail("GRAPH_DUPLICATE_EDGE_ID",
                  f"duplicate relation_id {r['relation_id']!r}")
        seen.add(r["relation_id"])
    blob = json.dumps({"entities": entities, "relations": relations},
                      sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return {
        "schema": "geologia-knowledge-graph/1",
        "entities": entities,
        "relations": relations,
        "graph_fingerprint": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
    }


def load_graph(path) -> dict:
    from pathlib import Path
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_graph(raw)
