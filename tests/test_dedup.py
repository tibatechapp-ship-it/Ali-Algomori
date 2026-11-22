"""T2.3 — the six-stage deduplication line on a crafted duplicate set."""
import pytest

from geologia.knowledge.dedup import (
    BYTE_DUPLICATE,
    CONFLICT_PRESERVED,
    CORRECTION_OF_PRIOR,
    MERGED_CLAIM_CUMULATIVE_EVIDENCE,
    NEW_CLAIM,
    NEW_METHOD,
    NEW_REGION,
    NEAR_DUPLICATE_VERSION,
    DedupError,
    harmonize_value,
    run_dedup_line,
    summarize,
)


def _unit(uid, claim, *, topic="stratigraphy", region="Marib",
          quant=None, sha=None, version=None, contradicts=None,
          superseded_by=None):
    u = {
        "unit_id": uid,
        "claim": claim,
        "source_id": "src-x",
        "page_or_section": "p.1",
        "language": "en",
        "region": region,
        "topic": topic,
        "confidence": "to_verify",
        "review_status": "read",
        "license": "public_domain",
        "extracted_at_utc": "2026-11-22T00:00:00Z",
        "license_per_purpose": {"research": True, "education": True,
                                "commercial": False, "redistribution": False},
    }
    if quant:
        u["quantitative"] = quant
    if contradicts:
        u["contradicts"] = contradicts
    if superseded_by:
        u["superseded_by"] = superseded_by
    return {"unit": u, "source_sha256": sha}


def test_unit_harmonization():
    assert harmonize_value(180, "m", "cm") == pytest.approx(18000)
    assert harmonize_value(1, "km", "m") == pytest.approx(1000)
    with pytest.raises(DedupError):
        harmonize_value(5, "furlongs", "m")


def test_s1_byte_duplicate():
    a = _unit("ku-a", "The unit is Miocene.", sha="aa" * 32)
    b = _unit("ku-b", "The unit is Miocene.", sha="aa" * 32)
    d = run_dedup_line([a, b])
    assert d[0]["outcome"] == NEW_CLAIM
    assert d[1]["outcome"] == BYTE_DUPLICATE
    assert d[1]["stage"] == "S1_byte_identity"
    assert d[1]["action"] == "drop_duplicate"


def test_s2_near_duplicate_version_keeps_both_linked():
    a = _unit("ku-a", "The formation reaches 180 m thickness near Marib.",
              sha="11" * 32, version="preprint")
    b = _unit("ku-b", "The formation reaches 180 m  thickness near Marib!",
              sha="22" * 32, version="final")
    d = run_dedup_line([a, b])
    assert d[1]["outcome"] == NEAR_DUPLICATE_VERSION
    assert d[1]["action"] == "keep_linked"


def test_s4_evidence_accumulates_and_nothing_is_deleted():
    a = _unit("ku-a", "The unit reaches 180 m thickness.",
              quant={"value": 180, "unit": "m",
                     "measurement_method": "measured_section"})
    b = _unit("ku-b", "The unit reaches 18000 cm thickness.",
              quant={"value": 18000, "unit": "cm",
                     "measurement_method": "measured_section"})
    d = run_dedup_line([a, b])
    assert d[1]["outcome"] == MERGED_CLAIM_CUMULATIVE_EVIDENCE
    assert d[1]["stage"] == "S4_evidence_aggregation"
    assert d[1]["peer_id"] == "ku-a"


def test_s5_region_and_method_separation():
    a = _unit("ku-a", "Basement uplift measured along the profile.",
              quant={"value": 100, "unit": "m", "measurement_method": "gravity"})
    b = _unit("ku-b", "Basement uplift measured along the profile.",
              region="Hadramawt",
              quant={"value": 100, "unit": "m", "measurement_method": "gravity"})
    c = _unit("ku-c", "Basement uplift measured along the profile.",
              quant={"value": 100, "unit": "m", "measurement_method": "seismic"})
    d = run_dedup_line([a, b, c])
    assert d[1]["outcome"] == NEW_REGION
    assert d[2]["outcome"] == NEW_METHOD


def test_s6_conflict_preserved_and_correction():
    a = _unit("ku-a", "The conglomerate age is 30 Ma.")
    b = _unit("ku-b", "The conglomerate age is 55 Ma.",
              contradicts=["ku-a"])
    c = _unit("ku-c", "Revised age of the conglomerate is 55 Ma.",
              superseded_by="ku-a")
    d = run_dedup_line([a, b, c])
    assert d[1]["outcome"] == CONFLICT_PRESERVED
    assert d[1]["action"] == "keep_both_linked"
    assert d[2]["outcome"] == CORRECTION_OF_PRIOR


def test_summary_counts_every_decision():
    a = _unit("ku-a", "Claim one.", sha="aa" * 32)
    b = _unit("ku-b", "Claim one.", sha="aa" * 32)
    c = _unit("ku-c", "An entirely different claim about karst springs.",
              topic="hydrogeology")
    s = summarize(run_dedup_line([a, b, c]))
    assert s["decisions"] == 3
    assert s["outcomes"].get(NEW_CLAIM) == 2
    assert s["outcomes"].get(BYTE_DUPLICATE) == 1
    assert len(s["stages"]) == 6


def test_items_must_carry_units():
    with pytest.raises(DedupError):
        run_dedup_line([{"no_unit": True}])
