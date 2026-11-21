# Deterministic TF-IDF retrieval index (pure Python, no ML, no network).
# Determinism + citations = the anti-hallucination mechanism: a query either
# returns stored passages with their provenance, or an honest empty result.
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from geologia.normalize import normalize_text

# Small Arabic/English stopword set (normalized forms). Keep it conservative:
# dropping content words is worse than keeping a stopword.
_STOPWORDS = {
    "من", "في", "على", "عن", "الى", "هذا", "هذه", "ذلك", "الذي", "التي",
    "ما", "هل", "و", "مع", "كل", "بين", "ثم", "او", "ان", "إن", "لماذا",
    "كيف", "اين", "ايضا", "خلال", "هو", "هي", "كان", "يكون", "قد", "لا",
    "the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "is",
    "are", "was", "were", "what", "how", "why", "with", "by", "at", "it",
}

_TOKEN_SPLIT = re.compile(r"[\s_\-/]+")

MIN_QUERY_TOKEN_LEN = 2


def tokenize(text: str) -> List[str]:
    """Normalized tokens for indexing and querying."""
    norm = normalize_text(text)
    tokens = []
    for tok in _TOKEN_SPLIT.split(norm):
        tok = tok.strip()
        if len(tok) < MIN_QUERY_TOKEN_LEN or tok in _STOPWORDS:
            continue
        tokens.append(tok)
    return tokens


@dataclass
class IndexedDoc:
    doc_id: str
    title: str
    text: str
    payload: Dict = field(default_factory=dict)


class TokenIndex:
    """In-memory inverted index with TF-IDF scoring. Deterministic ordering:
    score desc, then doc_id, then insertion order."""

    def __init__(self) -> None:
        self._docs: List[IndexedDoc] = []
        self._postings: Dict[str, List[Tuple[int, int]]] = {}
        self._df: Dict[str, int] = {}

    def add(self, doc: IndexedDoc) -> None:
        idx = len(self._docs)
        self._docs.append(doc)
        counts: Dict[str, int] = {}
        for tok in tokenize(f"{doc.title} {doc.text}"):
            counts[tok] = counts.get(tok, 0) + 1
        for term, tf in counts.items():
            self._postings.setdefault(term, []).append((idx, tf))
            self._df[term] = self._df.get(term, 0) + 1

    def __len__(self) -> int:
        return len(self._docs)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.05,
               filter_fn=None) -> List[dict]:
        """filter_fn: optional predicate on IndexedDoc applied BEFORE top_k
        truncation, so scope-restricted queries are not starved by off-scope
        high scorers."""
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return []
        allowed = {i for i, d in enumerate(self._docs)
                   if filter_fn is None or filter_fn(d)}
        if not allowed:
            return []
        n_docs = len(allowed)
        scores: Dict[int, float] = {}
        for term in q_tokens:
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = math.log((n_docs + 1) / (self._df.get(term, 0) + 1)) + 1.0
            for idx, tf in postings:
                if idx not in allowed:
                    continue
                weight = (1.0 + math.log(tf)) * idf
                scores[idx] = scores.get(idx, 0.0) + weight
        if not scores:
            return []
        max_score = max(scores.values())
        results = []
        for idx, score in scores.items():
            norm_score = score / max_score if max_score > 0 else 0.0
            if norm_score < min_score:
                continue
            doc = self._docs[idx]
            results.append({
                "doc_id": doc.doc_id,
                "title": doc.title,
                "excerpt": doc.text[:320].replace("\n", " ").strip(),
                "score": round(norm_score, 4),
                "payload": doc.payload,
            })
        results.sort(key=lambda r: (-r["score"], r["doc_id"]))
        return results[:top_k]


def build_text_search_string(title: str, meta_fields: List[str]) -> str:
    """Concatenate title + metadata fields into one indexable string."""
    return " ".join([title] + [f for f in meta_fields if f])
