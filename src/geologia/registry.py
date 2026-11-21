# GEOLOGIA engine registry loader (foundation phase).
# Two families, one read-only contract:
#   - third_party: external tools cataloged in data/engines.json (all "planned";
#     cannot be certified until sandboxed -> integrated per the integration policy)
#   - first_party : stdlib-only deterministic engines in data/first_party_engines.json;
#     certifiable via a pinned reference test (data_layer/certification.py)
# A certification overlay (trusted store certifications.json) may raise an
# engine's displayed status to "certified" — and a failed re-certification
# drops it back. Fail-fast card validation is kept for both files.
import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class EngineCard(BaseModel):
    engine_id: str
    name: str
    domain: str
    capabilities: List[str]
    status: str
    license_status: str
    integration_phase: int
    role_ar: str
    family: str = "third_party"
    version: Optional[str] = None
    input_contract: Optional[dict] = None
    method_citations: Optional[List[str]] = None
    validity_limits_ar: Optional[List[str]] = None


_DATA_PATH = Path(__file__).parent / "data" / "engines.json"
_FIRST_PARTY_PATH = Path(__file__).parent / "data" / "first_party_engines.json"


def _load_cards(path: Path, family: str) -> List[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    engines = raw["engines"]
    for item in engines:
        item.setdefault("family", family)
        EngineCard(**item)  # validation gate: fail fast on malformed cards
    return engines


def _load() -> List[dict]:
    third = _load_cards(_DATA_PATH, "third_party")
    first = _load_cards(_FIRST_PARTY_PATH, "first_party")
    return third + first


ENGINES: List[dict] = _load()


def _certified_ids() -> dict:
    """Engine ids with a PASSING certification record in the trusted store."""
    from geologia.data_layer.records import store_dir
    path = store_dir() / "certifications.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out = {}
    for rec in data.get("certifications", []):
        if rec.get("passed"):
            out[rec["engine_id"]] = rec
    return out


def certified_engines() -> dict:
    """Public view: {engine_id: certification_record} for certified engines."""
    return _certified_ids()


def list_engines(domain: Optional[str] = None) -> List[dict]:
    overlay = _certified_ids()
    items = []
    for e in ENGINES:
        if domain is not None and e["domain"] != domain:
            continue
        if e["engine_id"] in overlay:
            items.append({**e, "status": "certified",
                          "certification": {"certified_at": overlay[e["engine_id"]]
                                            .get("certified_at")}})
        else:
            items.append(e)
    return items


def get_engine(engine_id: str) -> Optional[dict]:
    for e in list_engines():
        if e["engine_id"] == engine_id:
            return e
    return None
