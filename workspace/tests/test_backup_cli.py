"""CLI regression tests for the application backup utility."""
import json

from geologia_workspace import store
from geologia_workspace.backup_cli import main


def test_backup_cli_creates_and_restores_bundle(tmp_path, monkeypatch, capsys):
    database = tmp_path / "source" / "metadata.sqlite3"
    uploads = tmp_path / "source" / "uploads"
    uploads.mkdir(parents=True)
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(database))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(uploads))
    monkeypatch.delenv("GEOLOGIA_KNOWLEDGE_DB_PATH", raising=False)
    store.create_project("CLI backup", "", "en")

    backup = tmp_path / "backup.bundle"
    assert main(["create", str(backup)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "created"

    restored = tmp_path / "restored"
    assert main(["restore", str(backup), str(restored)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "restored"
    assert (restored / "metadata.sqlite3").is_file()
    assert (restored / "uploads").is_dir()
