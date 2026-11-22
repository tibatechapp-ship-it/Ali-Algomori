"""Application-level backup/restore integrity and safety tests."""
from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from geologia_workspace import store
from geologia_workspace.application_backup import (
    create_application_backup,
    restore_application_backup,
)


def _setup(tmp_path, monkeypatch):
    db = tmp_path / "source" / "metadata.sqlite3"
    root = tmp_path / "source" / "uploads"
    root.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(db))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(root))
    monkeypatch.delenv("GEOLOGIA_KNOWLEDGE_DB_PATH", raising=False)
    project = store.create_project("Backup test", "", "en")
    data = b"stored geological dataset"
    path = root / "survey.blob"
    path.write_bytes(data)
    item = store.create_dataset(
        project["id"], name="Survey", file_format="txt", original_filename="survey.txt",
        content_path=str(path), sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), crs=None, data_role=None, summary={},
    )
    orphan = root / "unregistered.blob"
    orphan.write_bytes(b"keep orphan too")
    knowledge = db.parent / "knowledge.sqlite3"
    with sqlite3.connect(knowledge) as conn:
        conn.execute("CREATE TABLE notes (value TEXT)")
        conn.execute("INSERT INTO notes VALUES ('knowledge snapshot')")
    return db, root, project, item, knowledge, orphan


def test_application_backup_round_trip_restores_databases_and_rewrites_paths(
    tmp_path, monkeypatch
):
    db, root, project, item, knowledge, orphan = _setup(tmp_path, monkeypatch)
    backup = tmp_path / "backup.bundle"
    created = create_application_backup(backup)
    assert created["status"] == "created"
    assert created["dataset_count"] == 1
    assert created["upload_file_count"] == 2
    assert created["knowledge_database_included"] is True

    restored = tmp_path / "restored"
    result = restore_application_backup(backup, restored)
    assert result["status"] == "restored"
    assert (restored / "uploads" / "survey.blob").read_bytes() == b"stored geological dataset"
    assert (restored / "uploads" / "unregistered.blob").read_bytes() == b"keep orphan too"
    with closing(sqlite3.connect(restored / "metadata.sqlite3")) as conn:
        path = conn.execute(
            "SELECT content_path FROM datasets WHERE id=?", (item["id"],)
        ).fetchone()[0]
        assert path == str(restored / "uploads" / "survey.blob")
    with closing(sqlite3.connect(restored / "knowledge.sqlite3")) as conn:
        assert conn.execute("SELECT value FROM notes").fetchone()[0] == "knowledge snapshot"


def test_backup_refuses_tampered_registered_file_and_does_not_publish_bundle(
    tmp_path, monkeypatch
):
    _, root, _, _, _, _ = _setup(tmp_path, monkeypatch)
    (root / "survey.blob").write_bytes(b"tampered")
    destination = tmp_path / "should-not-exist"
    with pytest.raises(ValueError, match="integrity mismatch"):
        create_application_backup(destination)
    assert not destination.exists()


def test_restore_rejects_changed_backup_file_without_publishing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    backup = tmp_path / "backup"
    create_application_backup(backup)
    (backup / "uploads" / "survey.blob").write_bytes(b"changed")
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="checksum or size mismatch"):
        restore_application_backup(backup, destination)
    assert not destination.exists()


def test_restore_refuses_existing_destination(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    backup = tmp_path / "backup"
    create_application_backup(backup)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        restore_application_backup(backup, destination)


def test_restore_rejects_path_traversal_in_manifest(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    backup = tmp_path / "backup"
    create_application_backup(backup)
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_id = next(iter(manifest["datasets"]))
    manifest["datasets"][dataset_id] = "../escape.blob"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    destination = tmp_path / "restore-attempt"
    with pytest.raises(ValueError, match="unsafe backup path"):
        restore_application_backup(backup, destination)
    assert not destination.exists()
