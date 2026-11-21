# Knowledge corpus: seed catalog + ingestion (retrieval-only, zero hallucination).
#
# Zero-hallucination rule: the platform never produces knowledge beyond stored
# documents. Every retrieval result cites its stored source; if nothing matches
# above threshold, the honest answer is "not in the library".
#
# Honesty about confidence: seed entries carry confidence levels. "well_known"
# marks foundational classics and institutions; "to_verify" marks entries whose
# URL/details still need verification at fetch time. Nothing is claimed beyond
# what the entry itself states.
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Data files live in src/geologia/data/knowledge/ (catalog.py is one level deeper).
_DATA_DIR = Path(__file__).parent.parent / "data" / "knowledge"

CONFIDENCE_LEVELS = ("well_known", "to_verify")
ORIGIN_TYPES = (
    "book", "paper", "map_series", "standard", "report",
    "corpus_portal", "course", "company_manual", "digest",
)


@dataclass
class CatalogEntry:
    entry_id: str
    title_ar: str
    title_orig: str
    author: str
    year: Optional[int]
    origin_type: str
    language: str
    region_scope: str
    source_url: Optional[str]
    license_status: str
    confidence: str
    notes_ar: str
    keywords: List[str]

    @staticmethod
    def from_dict(d: dict) -> "CatalogEntry":
        missing = [k for k in (
            "entry_id", "title_ar", "title_orig", "author", "origin_type",
            "language", "region_scope", "confidence",
        ) if k not in d]
        if missing:
            raise ValueError(f"catalog entry missing fields: {missing}")
        if d["confidence"] not in CONFIDENCE_LEVELS:
            raise ValueError(f"bad confidence for {d['entry_id']}: {d['confidence']}")
        if d["origin_type"] not in ORIGIN_TYPES:
            raise ValueError(f"bad origin_type for {d['entry_id']}: {d['origin_type']}")
        return CatalogEntry(
            entry_id=d["entry_id"],
            title_ar=d["title_ar"],
            title_orig=d.get("title_orig", ""),
            author=d.get("author", ""),
            year=d.get("year"),
            origin_type=d["origin_type"],
            language=d.get("language", "ar"),
            region_scope=d.get("region_scope", "global"),
            source_url=d.get("source_url"),
            license_status=d.get("license_status", "unknown"),
            confidence=d["confidence"],
            notes_ar=d.get("notes_ar", ""),
            keywords=list(d.get("keywords", [])),
        )

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def load_seed_catalog() -> List[CatalogEntry]:
    """Load and validate the packaged seed catalog (fails fast on malformed rows)."""
    raw = json.loads((_DATA_DIR / "seed_catalog.json").read_text(encoding="utf-8"))
    entries = [CatalogEntry.from_dict(item) for item in raw["entries"]]
    ids = [e.entry_id for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate entry_id in seed catalog")
    return entries


def load_engine_kb() -> List[dict]:
    """Load the 30-engine knowledge base (docs URLs, keywords, search hints)."""
    raw = json.loads((_DATA_DIR / "engines_kb.json").read_text(encoding="utf-8"))
    cards = raw["engine_kb"]
    ids = [c["engine_id"] for c in cards]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate engine_id in engines_kb")
    return cards


def load_digest_documents() -> List[dict]:
    """Load Arabic digest markdown documents packaged with the seed corpus."""
    docs = []
    for md in sorted((_DATA_DIR / "docs").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        first_line = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        docs.append({
            "doc_id": f"digest-{md.stem}",
            "title_ar": first_line,
            "path": str(md),
            "origin_type": "digest",
            "author": "GEOLOGIA platform (original digest)",
            "year": None,
            "language": "ar",
            "region_scope": "global",
            "source_url": None,
            "license_status": "original_work",
            "confidence": "well_known",
            "text": text,
        })
    return docs


def catalog_to_dicts(entries: Optional[List[CatalogEntry]] = None) -> List[dict]:
    return [e.to_dict() for e in (entries if entries is not None else load_seed_catalog())]


def _catalog_summary(d: Dict) -> dict:
    return {
        "entry_id": d["entry_id"],
        "title_ar": d["title_ar"],
        "author": d["author"],
        "year": d.get("year"),
        "origin_type": d["origin_type"],
        "language": d["language"],
        "region_scope": d["region_scope"],
        "confidence": d["confidence"],
        "license_status": d["license_status"],
    }
