"""Knowledge layer tests: seed catalog, engine KB, retrieval-only honesty."""
import pytest

from geologia.knowledge.catalog import load_digest_documents, load_engine_kb, load_seed_catalog
from geologia.knowledge.retrieval import KnowledgeBase


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


def test_seed_catalog_loads_and_validates():
    entries = load_seed_catalog()
    assert len(entries) >= 60
    ids = {e.entry_id for e in entries}
    # Arabic heritage, Chinese heritage, Yemen sources, US/China/Arab portals
    assert "heritage-ibnsina-mountains" in ids
    assert "heritage-shenkou-mengxi" in ids
    assert "yemen-geukens-pp560d" in ids
    assert "portal-cgs-china" in ids
    assert "portal-usgs-pubs" in ids
    assert "portal-saudi-sgs" in ids


def test_every_entry_has_confidence_and_keywords():
    for e in load_seed_catalog():
        assert e.confidence in ("well_known", "to_verify")
        assert e.title_ar and e.origin_type


def test_engine_kb_matches_third_party_registry_ids():
    # The knowledge engine KB documents third-party tools; first-party engines
    # carry their own reference documentation (data/reference/).
    from geologia.registry import ENGINES
    kb_ids = {c["engine_id"] for c in load_engine_kb()}
    third_party_ids = {e["engine_id"] for e in ENGINES
                       if e["family"] == "third_party"}
    assert kb_ids == third_party_ids


def test_digest_documents_packaged():
    docs = load_digest_documents()
    assert len(docs) == 10
    assert all(d["language"] == "ar" for d in docs)
    assert any("معيار" in d["title_ar"] for d in docs)


def test_retrieval_finds_arabic_answer_with_citation(kb):
    result = kb.search("ما هي مبادئ الجيولوجيا ومتى بدأ علم الجيولوجيا؟")
    assert result["status"] == "found"
    assert result["no_generated_content"] is True
    top = result["results"][0]
    assert top["payload"]["citation"]
    assert top["score"] > 0


def test_retrieval_groundwater_topic(kb):
    result = kb.search("الهيدروجيولوجيا والمياه الجوفية وmodflow")
    hits = {r["payload"]["kind"] for r in result["results"]}
    assert "digest" in hits or "catalog" in hits
    assert all(r["payload"].get("citation") for r in result["results"])


def test_engine_kb_query(kb):
    result = kb.search("lasio قراءة سجلات الآبار las", scope="engine_kb")
    assert result["status"] == "found"
    ids = {r["doc_id"] for r in result["results"]}
    assert any("engine:lasio" in i for i in ids)


def test_honest_miss_is_not_fabricated(kb):
    result = kb.search("xxqq zzvv 12345 bogus")
    assert result["status"] == "not_in_library"
    assert result["results"] == []
    assert "ليس في المكتبة" in result["message_ar"]


def test_scope_filtering(kb):
    all_hits = kb.search("groundwater modflow", scope="catalog")
    assert all(h["payload"]["kind"] == "catalog" for h in all_hits.get("results", []))


def test_stats(kb):
    stats = kb.stats()
    assert stats["catalog_entries"] >= 60
    assert stats["engine_kb_cards"] == 30
    assert stats["retrieval_only"] is True
