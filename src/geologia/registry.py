# GEOLOGIA engine registry loader (foundation phase).
# Validates every engine card at import time and exposes read-only access.
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


_DATA_PATH = Path(__file__).parent / "data" / "engines.json"


def _load() -> List[dict]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    engines = raw["engines"]
    for item in engines:
        EngineCard(**item)  # validation gate: fail fast on malformed cards
    return engines


ENGINES: List[dict] = _load()


def list_engines(domain: Optional[str] = None) -> List[dict]:
    if domain is None:
        return list(ENGINES)
    return [e for e in ENGINES if e["domain"] == domain]


def get_engine(engine_id: str) -> Optional[dict]:
    for e in ENGINES:
        if e["engine_id"] == engine_id:
            return e
    return None
