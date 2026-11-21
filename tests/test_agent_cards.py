"""Agent capability cards integrity tests (T3.4 / ADR-0008).

The nine role cards are the anti-hallucination contracts of the specialist
agents: a role without explicit refusal conditions is not a role, and the
aggregation rule must stay the declared Ali doctrine, verbatim, everywhere.
"""
import json
from pathlib import Path

import geologia

AGENTS_DIR = Path(geologia.__file__).parent / "data" / "agents"
ENGINES_PATH = Path(geologia.__file__).parent / "data" / "engines.json"

EXPECTED_SLUGS = {
    "stratigraphy", "tectonics", "mineralogy", "petrology", "geophysics",
    "geochemistry", "hydrogeology", "geoai_gis", "scientific_review",
}
GENERAL_TOOLS = {"kb_retrieval", "task_ledger", "reception_gate"}

# Ali's declared aggregation rule (ADR-0008) — must appear verbatim, identical
# in every card. Split only to respect the 100-char source line limit; the
# concatenated value is the exact doctrine string.
AGGREGATION_DOCTRINE_AR = (
    "خلاف الوكلاء يُعرض موثقاً بحجتيه "
    "ولا يُوسطط ولا يُحسم بالسلطة"
)
MODEL_POLICY_AR = (
    "أدوار فوق نموذج واحد أو أكثر — "
    "لا نماذج مدربة منفصلة (ADR-0008)"
)


def _load_cards() -> dict:
    cards = {}
    for path in sorted(AGENTS_DIR.glob("*.json")):
        cards[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return cards


def _engine_ids() -> set:
    registry = json.loads(ENGINES_PATH.read_text(encoding="utf-8"))
    return {e["engine_id"] for e in registry["engines"]}


def test_exactly_nine_cards_matching_filenames():
    cards = _load_cards()
    assert set(cards) == EXPECTED_SLUGS
    for slug, card in cards.items():
        assert card["schema"] == "geologia-agent-card/1"
        assert card["agent_id"] == f"agent-{slug}"
        assert len({c["agent_id"] for c in cards.values()}) == 9


def test_every_card_has_role_and_io():
    for card in _load_cards().values():
        assert card["role_ar"].strip()
        assert card["role_en"].strip()
        assert card["inputs"], card["agent_id"]
        assert card["outputs"], card["agent_id"]


def test_refusal_conditions_at_least_two_per_card():
    # Fingerprint of the anti-hallucination doctrine: a role without an
    # explicit refusal condition is a small hallucination gate (ADR-0008).
    for card in _load_cards().values():
        assert len(card["refusal_conditions"]) >= 2, card["agent_id"]
        assert all(isinstance(c, str) and c.strip()
                   for c in card["refusal_conditions"])


def test_aggregation_rule_identical_across_all_cards():
    cards = _load_cards()
    rules = {c["aggregation_rule_ar"] for c in cards.values()}
    assert rules == {AGGREGATION_DOCTRINE_AR}


def test_model_policy_and_adr_reference():
    for card in _load_cards().values():
        assert card["model_policy_ar"] == MODEL_POLICY_AR
        assert card["adr_reference"] == "ADR-0008"


def test_allowed_tools_subset_of_real_engines_and_general_tokens():
    allowed = _engine_ids() | GENERAL_TOOLS
    for card in _load_cards().values():
        tools = set(card["allowed_tools"])
        assert tools, card["agent_id"]
        assert tools <= allowed, (card["agent_id"], tools - allowed)
