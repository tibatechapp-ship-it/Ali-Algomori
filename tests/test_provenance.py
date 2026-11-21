"""Provenance tests: the tamper-evident chain must actually resist tampering.

A provenance log that can be edited silently is decoration, not evidence.
These tests attack the chain the way an attacker would: edit a record,
delete one, insert one, reorder — every attack must be detected with its
specific code.
"""
import json


from geologia.data_layer.provenance import (GENESIS_HASH, ProvenanceLog,
                                            default_log_path, ref_file,
                                            tool_versions)


def write_log(tmp_path, n=3):
    log = ProvenanceLog(str(tmp_path / "prov.jsonl"))
    for i in range(n):
        log.append(action=f"step-{i}", inputs=[{"name": f"in-{i}"}],
                   outputs=[{"name": f"out-{i}"}],
                   verdict={"status": "pass"})
    return log


def test_tool_versions_names_every_engine():
    tv = tool_versions()
    for key in ("python", "geologia", "pydantic", "lasio", "tifffile",
                "pyproj", "numpy", "sqlite3"):
        assert key in tv
    assert tv["geologia"]  # own version always known


def test_append_and_verify_clean_chain(tmp_path):
    log = write_log(tmp_path, 3)
    v = log.verify()
    assert v["ok"] is True and v["count"] == 3
    assert v["findings"] == []


def test_first_record_links_to_genesis(tmp_path):
    log = write_log(tmp_path, 1)
    rec = log.records()[0]
    assert rec["parent_hash"] == GENESIS_HASH
    assert rec["seq"] == 1


def test_record_hash_covers_full_content(tmp_path):
    log = write_log(tmp_path, 1)
    rec = log.records()[0]
    import hashlib
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    assert rec["record_hash"] == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def test_edited_record_is_detected(tmp_path):
    log = write_log(tmp_path, 2)
    recs = log.records()
    recs[0]["verdict"]["status"] = "pass-forged"
    (tmp_path / "prov.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")
    v = log.verify()
    assert v["ok"] is False
    codes_ = [f["code"] for f in v["findings"]]
    assert "PROV_HASH_MISMATCH" in codes_


def test_deleted_record_is_detected(tmp_path):
    log = write_log(tmp_path, 3)
    recs = log.records()
    del recs[1]  # attacker removes an inconvenient step
    (tmp_path / "prov.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")
    v = log.verify()
    assert v["ok"] is False
    codes_ = [f["code"] for f in v["findings"]]
    assert "PROV_CHAIN_BROKEN" in codes_ or "PROV_SEQ_GAP" in codes_


def test_inserted_record_is_detected(tmp_path):
    log = write_log(tmp_path, 2)
    recs = log.records()
    forged = dict(recs[0])
    forged["seq"] = 2
    forged["action"] = "forged-step"
    recs.insert(1, forged)
    (tmp_path / "prov.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")
    v = log.verify()
    assert v["ok"] is False


def test_reordered_records_are_detected(tmp_path):
    log = write_log(tmp_path, 3)
    recs = log.records()
    recs[0], recs[1] = recs[1], recs[0]
    (tmp_path / "prov.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")
    v = log.verify()
    assert v["ok"] is False


def test_each_record_snapshots_tool_versions(tmp_path):
    log = write_log(tmp_path, 2)
    recs = log.records()
    assert recs[0]["tool_versions"]["geologia"]
    assert recs[1]["tool_versions"]["geologia"]


def test_default_log_path_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOLOGIA_DATA_DIR", str(tmp_path))
    assert default_log_path() == tmp_path / "provenance.jsonl"


def test_ref_file_hashes_content(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    ref = ref_file(str(p))
    import hashlib
    assert ref["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert ref["bytes"] == 3
