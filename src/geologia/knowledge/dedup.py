# The six-stage deduplication line (T2.3) — خط الجِدّة السداسي.
#
# Binding corrections from the approved plan (they are NOT optional):
# 1. Stage S4 AGGREGATES evidence onto one claim; it never deletes it.
#    Removing a duplicate document is not merging claims (Gap 5).
# 2. Quantitative claims are UNIT-HARMONIZED before matching (m vs cm is the
#    same measurement; g vs kg is the same measurement; unknown units are
#    never silently equated).
#
# Stage map (first decisive stage wins; every outcome is a testable code):
#   S1 byte identity        -> BYTE_DUPLICATE          (same source sha256 AND
#                                                        same normalized claim)
#   S2 near-duplicate       -> NEAR_DUPLICATE_VERSION  (preprint vs final: high
#                              text similarity, SAME topic+region, and NOT a
#                              quantitative pair - quantities are never
#                              text-matched; correction #2 forces their
#                              unit-harmonized path)
#   S3 claim match          -> (candidate merge; needs S4 to take effect)
#   S4 evidence aggregation -> MERGED_CLAIM_CUMULATIVE_EVIDENCE (peer survives,
#                                                        evidence accumulates)
#   S5 separation           -> NEW_REGION | NEW_METHOD (kept separate, honestly)
#   S6 lifecycle            -> CONFLICT_PRESERVED (kept, linked, never averaged)
#                             | CORRECTION_OF_PRIOR   (explicit supersession)
#                             | NEW_CLAIM             (fresh, kept)
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List

# Outcome codes (stable contract; tests assert them).
BYTE_DUPLICATE = "BYTE_DUPLICATE"
NEAR_DUPLICATE_VERSION = "NEAR_DUPLICATE_VERSION"
MERGED_CLAIM_CUMULATIVE_EVIDENCE = "MERGED_CLAIM_CUMULATIVE_EVIDENCE"
NEW_REGION = "NEW_REGION"
NEW_METHOD = "NEW_METHOD"
CORRECTION_OF_PRIOR = "CORRECTION_OF_PRIOR"
CONFLICT_PRESERVED = "CONFLICT_PRESERVED"
NEW_CLAIM = "NEW_CLAIM"

_STAGES = ("S1_byte_identity", "S2_near_duplicate", "S3_claim_match",
           "S4_evidence_aggregation", "S5_separation", "S6_lifecycle")

NEAR_DUP_SIMILARITY = 0.92     # preprint vs final wording drift tolerance
REL_VALUE_TOL = 1e-9

# Unit harmonization table (lengths + masses; deliberately small and explicit).
# Anything outside the table is UNKNOWN: claims with unknown units are never
# matched quantitatively - they fall through to separation or conflict stages.
UNIT_FACTORS: Dict[str, float] = {
    "m": 1.0, "meter": 1.0, "metre": 1.0,
    "cm": 0.01, "mm": 0.001, "km": 1000.0,
    "kg": 1.0, "g": 0.001, "mg": 1e-6, "t": 1000.0,
    "ma": 1.0,       # mega-annum (geologic time) baseline
    "ka": 1e-3, "ga": 1e9,
    "percent": 1.0, "%": 1.0,
}


class DedupError(ValueError):
    pass


def normalize_text(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[\W_]+", "", t, flags=re.UNICODE)
    return t


def harmonize_value(value: float, unit: str, target: str) -> float:
    """Convert value between known units; DedupError on unknown units."""
    if unit not in UNIT_FACTORS or target not in UNIT_FACTORS:
        raise DedupError(
            f"unknown unit(s) {unit!r}->{target!r}: refusing to equate "
            "quantities outside the harmonization table")
    return value * UNIT_FACTORS[unit] / UNIT_FACTORS[target]


def _quant_equal(a: dict, b: dict) -> bool:
    try:
        va = harmonize_value(float(a["value"]), str(a["unit"]),
                             str(b["unit"]))
    except (DedupError, KeyError, TypeError, ValueError):
        return False
    vb = float(b["value"])
    return abs(va - vb) <= REL_VALUE_TOL * max(abs(va), abs(vb), 1.0)


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def run_dedup_line(items: List[dict]) -> List[dict]:
    """Classify every item against all earlier KEPT items.

    Each item: {"unit": <schema-v1 unit dict>, "source_sha256": <str|None>}.
    Returns one decision per item in order:
      {"unit_id", "stage", "outcome", "peer_id", "action", "detail"}
    Decisions are pure data: applying them (dropping a byte-duplicate,
    appending an evidence ref to a survivor) is the caller's ledger job.
    """
    decisions: List[dict] = []
    kept: List[dict] = []
    for item in items:
        unit = item.get("unit")
        sha = item.get("source_sha256")
        if not isinstance(unit, dict) or "unit_id" not in unit:
            raise DedupError("item must carry a schema-v1 unit dict")
        decision = {"unit_id": unit["unit_id"], "stage": None,
                    "outcome": NEW_CLAIM, "peer_id": None,
                    "action": "keep", "detail": ""}
        norm = normalize_text(unit.get("claim", ""))

        for peer_entry in kept:
            peer = peer_entry["unit"]
            peer_norm = normalize_text(peer.get("claim", ""))
            qa, qb = unit.get("quantitative"), peer.get("quantitative")
            same_topic = unit.get("topic") == peer.get("topic")
            same_region = unit.get("region") == peer.get("region")
            text_sim = _sim(norm, peer_norm)

            # S1 - byte identity: same source bytes AND same claim wording.
            decision["stage"] = _STAGES[0]
            if (sha and peer_entry["source_sha256"] == sha
                    and norm == peer_norm):
                decision.update(outcome=BYTE_DUPLICATE,
                                peer_id=peer["unit_id"],
                                action="drop_duplicate",
                                detail="same source sha256 and identical "
                                       "normalized claim")
                break

            # S2 - near duplicate across different bytes (preprint vs final).
            # Scope-guarded: same topic and region, NEVER a quantitative pair,
            # and never a wording drift carrying different digits (numbers are
            # claim-bearing). Quantities unify units before matching.
            decision["stage"] = _STAGES[1]
            same_scope = same_topic and same_region
            quant_pair = bool(qa and qb)
            digits_differ = (norm != peer_norm) and any(
                ch.isdigit() for ch in norm + peer_norm)
            if (same_scope and not quant_pair
                    and (norm == peer_norm
                         or (text_sim >= NEAR_DUP_SIMILARITY
                             and not digits_differ))
                    and (not sha or not peer_entry["source_sha256"]
                         or peer_entry["source_sha256"] != sha)):
                detail = ("same wording from different source bytes"
                          if norm == peer_norm else
                          f"text similarity {text_sim:.3f} >= threshold "
                          "across different source bytes")
                decision.update(outcome=NEAR_DUPLICATE_VERSION,
                                peer_id=peer["unit_id"],
                                action="keep_linked", detail=detail)
                break

            # S3 - quantitative claim match after unit harmonization. Same
            # measurement METHOD is part of the match: the same quantity by a
            # different method is a separate finding, not a duplicate.
            decision["stage"] = _STAGES[2]
            quant_match = (quant_pair and same_topic and same_region
                           and qa.get("measurement_method")
                           == qb.get("measurement_method")
                           and _quant_equal(qa, qb))

            # S4 - evidence aggregation: one claim survives, evidence grows.
            # The text path never merges a quantitative pair: quantities
            # match only through the harmonized S3 gate (same units, same
            # method) — wording similarity alone proves nothing about numbers.
            decision["stage"] = _STAGES[3]
            if quant_match or ((not quant_pair) and same_scope
                               and text_sim >= 0.98):
                decision.update(
                    outcome=MERGED_CLAIM_CUMULATIVE_EVIDENCE,
                    peer_id=peer["unit_id"],
                    action="merge_evidence_into_peer",
                    detail="claim-level match: peer survives and the new "
                           "source joins its cumulative evidence (nothing "
                           "is deleted)")
                break

            # S5 - honest separation when scope differs.
            decision["stage"] = _STAGES[4]
            if text_sim >= 0.6 and not same_region:
                decision.update(outcome=NEW_REGION, peer_id=peer["unit_id"],
                                action="keep_separate",
                                detail="similar wording, different region: "
                                       "a new finding, not a duplicate")
                break
            if (same_topic and qa and qb
                    and qa.get("measurement_method")
                    != qb.get("measurement_method")):
                decision.update(outcome=NEW_METHOD, peer_id=peer["unit_id"],
                                action="keep_separate",
                                detail="same quantity, different measurement "
                                       "method: kept separate")
                break

            # S6 - explicit lifecycle relations only (never inferred).
            decision["stage"] = _STAGES[5]
            if peer["unit_id"] in (unit.get("contradicts") or []):
                decision.update(
                    outcome=CONFLICT_PRESERVED, peer_id=peer["unit_id"],
                    action="keep_both_linked",
                    detail="declared contradiction: both claims kept and "
                           "linked; no averaging, no silent winner")
                break
            if unit.get("superseded_by") == peer["unit_id"] \
                    or peer.get("superseded_by") == unit["unit_id"]:
                decision.update(
                    outcome=CORRECTION_OF_PRIOR, peer_id=peer["unit_id"],
                    action="keep_supersession_link",
                    detail="explicit correction: supersession link recorded "
                           "on both sides")
                break

        decisions.append(decision)
        if decision["action"] in ("keep", "keep_linked", "keep_separate",
                                  "keep_both_linked", "keep_supersession_link"):
            kept.append({"unit": unit, "source_sha256": sha})
        # drop_duplicate / merge_evidence_into_peer do NOT add a new kept unit
        # (S4 doctrine: the peer survives and accumulates evidence).
    return decisions


def summarize(decisions: List[dict]) -> dict:
    counts: Dict[str, int] = {}
    for d in decisions:
        counts[d["outcome"]] = counts.get(d["outcome"], 0) + 1
    return {"stages": list(_STAGES), "decisions": len(decisions),
            "outcomes": counts}
