# Retrieval layer: search over catalog entries, digest documents and the
# engine knowledge base. Retrieval-only: no generative answers, every hit
# carries a citation, misses are reported honestly ("not in the library").
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from geologia.knowledge.catalog import (
    catalog_to_dicts,
    load_digest_documents,
    load_engine_kb,
    load_seed_catalog,
)
from geologia.knowledge.index import IndexedDoc, TokenIndex

NOT_IN_LIBRARY_AR = (
    "ليس في المكتبة بعد: لا يوجد مقطع مخزن يجيب عن هذا السؤال. "
    "المنصة لا تختلق جوابًا من خارج المصادر المخزنة — أضف مستندًا أو ابحث بسؤال آخر."
)
NOT_IN_LIBRARY_EN = (
    "Not in the library: no stored passage answers this query. The platform does "
    "not fabricate answers beyond stored sources — add a document or rephrase."
)

# Anchor added to every chunk for citation (document + paragraph number).
_MAX_CHUNK_CHARS = 900


def _chunk_text(text: str) -> List[str]:
    """Split markdown/plain text into citable paragraph chunks."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    buffer = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) + 2 <= _MAX_CHUNK_CHARS:
            buffer = f"{buffer}\n{para}" if buffer else para
        else:
            if buffer:
                chunks.append(buffer)
            buffer = para[:_MAX_CHUNK_CHARS]
    if buffer:
        chunks.append(buffer)
    return chunks


class KnowledgeBase:
    """In-memory retrieval corpus: digests + catalog + engine KB (+ user adds)."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._index = TokenIndex()
        self._n_chunks = 0
        self._store_dir = store_dir
        self._build()

    # -- construction ----------------------------------------------------
    def _build(self) -> None:
        for entry in catalog_to_dicts():
            text = " ".join(
                [entry["title_ar"], entry["title_orig"], entry["author"],
                 entry["notes_ar"], " ".join(entry["keywords"])]
            )
            self._add_doc(
                doc_id=f"cat:{entry['entry_id']}",
                title=entry["title_ar"],
                text=text,
                citation_meta=entry,
                kind="catalog",
            )
        for doc in load_digest_documents():
            for i, chunk in enumerate(_chunk_text(doc["text"])):
                self._add_doc(
                    doc_id=f"digest:{doc['doc_id']}#p{i + 1}",
                    title=doc["title_ar"],
                    text=chunk,
                    citation_meta=doc,
                    kind="digest",
                )
        for card in load_engine_kb():
            text = " ".join([
                card["name"], card["domain"], card.get("role_ar", ""),
                " ".join(card.get("keywords", [])),
            ])
            self._add_doc(
                doc_id=f"engine:{card['engine_id']}",
                title=f"{card['name']} — {card['domain']}",
                text=text,
                citation_meta=card,
                kind="engine_kb",
            )

    def _add_doc(self, doc_id: str, title: str, text: str,
                 citation_meta: dict, kind: str) -> None:
        self._index.add(IndexedDoc(
            doc_id=doc_id, title=title, text=text, payload={
                "kind": kind,
                "citation": self._citation(kind, citation_meta, doc_id),
                **self._public_meta(citation_meta),
            }
        ))
        self._n_chunks += 1

    @staticmethod
    def _public_meta(meta: dict) -> dict:
        keys = ("author", "year", "language", "region_scope", "confidence",
                "license_status", "source_url", "origin_type")
        return {k: meta[k] for k in keys if k in meta and meta[k] is not None}

    @staticmethod
    def _citation(kind: str, meta: dict, doc_id: str) -> str:
        author = meta.get("author") or ""
        year = meta.get("year")
        title = meta.get("title_ar") or meta.get("title") or meta.get("name") or ""
        who = f"{author}، " if author else ""
        when = f"({year})" if year else ""
        return f"{who}{title} {when}".strip() + f" [{doc_id}]"

    # -- queries ---------------------------------------------------------
    def search(self, query: str, top_k: int = 5, scope: str = "all") -> dict:
        filter_fn = None
        if scope != "all":
            filter_fn = lambda doc: doc.payload["kind"] == scope  # noqa: E731
        hits = self._index.search(query, top_k=max(1, min(top_k, 20)),
                                  filter_fn=filter_fn)
        if not hits:
            return {
                "status": "not_in_library",
                "message_ar": NOT_IN_LIBRARY_AR,
                "message_en": NOT_IN_LIBRARY_EN,
                "results": [],
            }
        return {
            "status": "found",
            "retrieval_only": True,
            "no_generated_content": True,
            "count": len(hits),
            "results": hits,
        }

    def stats(self) -> dict:
        entries = len(load_seed_catalog())
        digests = len(load_digest_documents())
        engines = len(load_engine_kb())
        return {
            "catalog_entries": entries,
            "digest_documents": digests,
            "engine_kb_cards": engines,
            "indexed_chunks": self._n_chunks,
            "retrieval_only": True,
        }

    # -- user corpus (persisted outside the package) ----------------------
    def add_document(self, path: str, title_ar: str, author: str = "",
                     year: Optional[int] = None, language: str = "ar",
                     source_url: Optional[str] = None,
                     license_status: str = "unknown") -> dict:
        """Ingest a user-provided .md/.txt file into the retrieval corpus.

        The file itself is never copied or modified; chunks reference its path."""
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"source file not found: {path}")
        if src.suffix.lower() not in (".md", ".txt"):
            raise ValueError("only .md and .txt files are ingestable in foundation phase")
        text = src.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError("refusing to ingest an empty document")
        doc_id = f"user:{src.stem}"
        meta = {
            "title_ar": title_ar,
            "title_orig": src.stem,
            "author": author,
            "year": year,
            "origin_type": "digest",
            "language": language,
            "region_scope": "user_corpus",
            "source_url": source_url,
            "license_status": license_status,
            "confidence": "user_provided",
        }
        for i, chunk in enumerate(_chunk_text(text)):
            self._add_doc(
                doc_id=f"{doc_id}#p{i + 1}",
                title=title_ar,
                text=chunk,
                citation_meta=meta,
                kind="user_corpus",
            )
        return {
            "doc_id": doc_id,
            "chunks_added": len(_chunk_text(text)),
            "file_path": str(src.resolve()),
            "bytes": len(text.encode("utf-8")),
            "note_ar": "الفهرس داخل الذاكرة لهذه الجلسة؛"
                       " التخزين الدائم يعاد بناؤه من نفس الملف.",
        }


_DEFAULT: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    """Process-wide default knowledge base (built once, cheap to rebuild)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = KnowledgeBase()
    return _DEFAULT


def search_knowledge(query: str, top_k: int = 5, scope: str = "all") -> dict:
    return get_kb().search(query, top_k=top_k, scope=scope)
