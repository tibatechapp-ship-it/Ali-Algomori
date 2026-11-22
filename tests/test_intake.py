"""T2.1 — knowledge-source intake: the no-second-door rule, tested."""
import json
from pathlib import Path

import pytest

from geologia.data_layer.provenance import ProvenanceLog
from geologia.knowledge.intake import (
    STATUS_ALREADY,
    STATUS_PROVEN,
    STATUS_REJECTED,
    intake_source,
    load_sources_registry,
)


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(tmp_path / "store"))
    return tmp_path


def _pdf(tmp_path, name="doc.pdf"):
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n")
    return p


def test_pdf_source_is_proven_and_registered(data_dir, tmp_path):
    src = _pdf(tmp_path)
    log = ProvenanceLog(str(tmp_path / "prov.jsonl"))
    res = intake_source(str(src), source_url="https://example.org/doc.pdf",
                        license_status="open_access",
                        provenance_log=log)
    assert res["status"] == STATUS_PROVEN
    assert res["source_id"].startswith("src-")
    assert Path(res["quarantine_path"]).exists()
    assert res["evidence"]["verified"], "quarantine identity must be verified-level"
    reg = load_sources_registry()
    assert len(reg) == 1
    assert reg[0]["sha256"] == res["sha256"]
    assert reg[0]["license_status"] == "open_access"
    verdicts = [r["verdict"]["status"] for r in log.records()
                if r["action"] == "knowledge_source_intake"]
    assert verdicts == ["proven"]


def test_empty_and_oversized_and_bad_magic_are_refused_and_logged(data_dir, tmp_path, monkeypatch):
    log = ProvenanceLog(str(tmp_path / "prov.jsonl"))
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    r1 = intake_source(str(empty), provenance_log=log)
    assert r1["status"] == STATUS_REJECTED
    assert any(f["code"] == "KS_EMPTY_FILE" for f in r1["findings"])

    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"random garbage bytes, definitely not a pdf")
    r3 = intake_source(str(fake), provenance_log=log)
    assert r3["status"] == STATUS_REJECTED
    assert any(f["code"] == "KS_UNKNOWN_MAGIC" for f in r3["findings"])

    monkeypatch.setenv("GEOLOGIA_MAX_UPLOAD_BYTES", "10")
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-1.4" + b"x" * 100)
    r2 = intake_source(str(big), provenance_log=log)
    assert r2["status"] == STATUS_REJECTED
    assert any(f["code"] == "KS_TOO_LARGE" for f in r2["findings"])

    verdicts = [r["verdict"]["status"] for r in log.records()
                if r["action"] == "knowledge_source_intake"]
    assert verdicts == ["rejected", "rejected", "rejected"], \
        "every refusal must leave a provenance trace"


def test_ext_mismatch_is_refused(data_dir, tmp_path):
    html = tmp_path / "page.pdf"          # pdf extension, html content
    html.write_bytes(b"<html><body><p>x</p></body></html>")
    res = intake_source(str(html), dtype="pdf")
    assert res["status"] == STATUS_REJECTED
    assert any(f["code"] == "KS_UNKNOWN_MAGIC" for f in res["findings"])


def test_no_special_path_for_trusted_sites(data_dir, tmp_path):
    """A 'trusted' URL earns nothing before the gate: same bytes, same refusal."""
    fake = tmp_path / "official.pdf"
    fake.write_bytes(b"not a pdf at all")
    res = intake_source(str(fake),
                        source_url="https://very-trusted-institution.org/x.pdf",
                        license_status="licensed")
    assert res["status"] == STATUS_REJECTED


def test_reintake_is_content_addressed(data_dir, tmp_path):
    src = _pdf(tmp_path)
    r1 = intake_source(str(src))
    r2 = intake_source(str(src))
    assert r1["status"] == STATUS_PROVEN
    assert r2["status"] == STATUS_ALREADY
    assert r2["source_id"] == r1["source_id"]
    assert len(load_sources_registry()) == 1


def test_text_source_requires_utf8(data_dir, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_bytes(b"\xff\xfe\x00binary-ish")
    res = intake_source(str(bad))
    assert res["status"] == STATUS_REJECTED
    assert any(f["code"] == "KS_NOT_TEXT" for f in res["findings"])

    good = tmp_path / "notes.txt"
    good.write_bytes("طبقات اليمن: تصدع طويل".encode("utf-8"))
    res2 = intake_source(str(good), license_status="unknown")
    assert res2["status"] == STATUS_PROVEN
    assert res2["dtype"] == "txt"
