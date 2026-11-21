# GEOLOGIA knowledge layer — retrieval-only, zero-hallucination memory.
from geologia.knowledge.catalog import load_engine_kb, load_seed_catalog
from geologia.knowledge.retrieval import KnowledgeBase, get_kb, search_knowledge

__all__ = ["KnowledgeBase", "get_kb", "search_knowledge", "load_seed_catalog", "load_engine_kb"]
