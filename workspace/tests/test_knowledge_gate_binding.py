"""Binding tests: the workspace retrieval index has exactly one door — the
governed core's reception gate (T2.1 no-second-door, applied to the app layer).

These tests need BOTH layers importable (governed core ``geologia`` + workspace
``geologia_workspace``); where only the workspace is installed they skip
honestly with a named reason (CONTRIBUTING rule #4).
"""
import importlib.util
import json
from pathlib import Path

import pytest

from geologia_workspace import knowledge
from geologia_workspace.knowledge_gate import (
    GATE_STATUS_INDEXED,
    GATE_STATUS_REFUSED,
    gate_ingest_document,
    gate_verdict,
)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("geologia") is None,
    reason="the binding needs the governed core package (pip install -e .. in the monorepo)",
)


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(tmp_path / "corestore"))
    # desktop.py mutates os.environ process-wide (setdefault); guard the
    # knowledge DB resolution exactly like tests/test_knowledge.py does.
    monkeypatch.delenv("GEOLOGIA_KNOWLEDGE_DB_PATH", raising=False)
    knowledge.initialize()
    return tmp_path


def _metadata(**over):
    metadata = {
        "source_id": "src-gate-binding-001",
        "title": "Gate binding test document",
        "author": "Gate Binding Tests",
        "publisher": "GEOLOGIA",
        "source_url": "https://example.org/gate-binding-test.md",
        "license_name": "GEOLOGIA Proprietary License 1.0",
        "license_status": "original_work",
        "reviewed_by": "binding tests",
        "review_date": "2026-11-22",
        "language": "en",
        "source_kind": "core_note",
        "scientific_review_status": "not_assessed",
    }
    metadata.update(over)
    return metadata


def test_accepted_source_is_indexed_and_quarantined(isolated):
    marker = "kaitlinite-gate-marker-7391"
    doc = isolated / "accepted.md"
    doc.write_text(
        f"# Accepted via gate\n\nThe {marker} token proves the single door.\n",
        encoding="utf-8",
    )
    result = gate_ingest_document(doc, _metadata())
    assert result["status"] == GATE_STATUS_INDEXED
    assert result["gate"]["status"] == "proven"
    assert result["indexed"]["status"] == "indexed"
    assert result["indexed"]["chunk_count"] >= 1
    quarantine = Path(result["gate"]["quarantine_path"])
    assert quarantine.is_file()
    hits = knowledge.search(marker, limit=5)
    assert hits["count"] >= 1


def test_refused_source_is_never_indexed(isolated, monkeypatch):
    fake = isolated / "fake.pdf"
    fake.write_text(
        "refused marker zxqvu-9931 — magic byte inspection must refuse this",
        encoding="utf-8",
    )
    calls = []
    real_ingest = knowledge.ingest_document

    def spy(path, metadata):
        calls.append(str(path))
        return real_ingest(path, metadata)

    monkeypatch.setattr(knowledge, "ingest_document", spy)
    result = gate_ingest_document(fake, _metadata(source_id="src-gate-refused-001"))
    assert result["status"] == GATE_STATUS_REFUSED
    assert result["indexed"] is None
    error_codes = [
        f["code"] for f in result["gate"]["findings"] if f["severity"] == "error"
    ]
    assert error_codes, "a refusal carries named codes, not a shrug"
    assert calls == [], "the retrieval index was never touched by a refused byte"
    hits = knowledge.search("zxqvu-9931", limit=5)
    assert hits["count"] == 0


def test_refusal_leaves_a_hash_chained_provenance_trace(isolated):
    from geologia.data_layer.provenance import ProvenanceLog

    empty = isolated / "empty.md"
    empty.write_text("", encoding="utf-8")
    log_path = isolated / "prov.jsonl"
    verdict = gate_verdict(empty, provenance_log=ProvenanceLog(str(log_path)))
    assert verdict["status"] == "rejected"
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    traced = [
        r for r in records
        if r.get("action") == "knowledge_source_intake"
        and r.get("verdict", {}).get("status") == "rejected"
    ]
    assert traced, "a refusal without a trace is not evidence, it is a shrug"


def test_core_seeds_pass_the_gate_and_index(isolated):
    result = knowledge.seed_core_knowledge()
    assert result["gate_refused_count"] == 0
    assert result["seeded_count"] == result["source_count"]
    assert result["external_downloads"] == 0
    status = knowledge.status()
    assert status["core_seeded_count"] == len(knowledge.CORE_SEEDS)
