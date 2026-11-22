"""Read-only upload storage audit regression tests."""
import hashlib
import pytest

from geologia_workspace import store
from geologia_workspace.storage_audit import audit_upload_storage


@pytest.fixture
def audit_paths(tmp_path, monkeypatch):
    db, root = tmp_path / "metadata.sqlite3", tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(db))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(root))
    project = store.create_project("Storage audit", "", "en")
    return root, project


def add_dataset(project, path, content, stored_path=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return store.create_dataset(
        project["id"], name=path.name, file_format="txt", original_filename=path.name,
        content_path=str(stored_path or path),
        sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content),
        crs=None, data_role=None, summary={},
    )


def test_clean_storage_is_verified_and_not_modified(audit_paths):
    root, project = audit_paths
    path = root / "sample.blob"
    add_dataset(project, path, b"clean bytes")
    result = audit_upload_storage()
    assert result["status"] == "clean"
    assert result["verified_dataset_count"] == 1
    assert result["automatic_cleanup"] is False
    assert path.read_bytes() == b"clean bytes"


def test_missing_and_tampered_files_are_reported(audit_paths):
    root, project = audit_paths
    path = root / "tampered.blob"
    item = add_dataset(project, path, b"original")
    path.write_bytes(b"modified")
    missing = root / "missing.blob"
    store.create_dataset(
        project["id"], name="missing", file_format="txt", original_filename="missing.txt",
        content_path=str(missing), sha256="0" * 64, size_bytes=7, crs=None,
        data_role=None, summary={},
    )
    result = audit_upload_storage()
    assert result["missing_files"][0]["path"] == "missing.blob"
    assert result["integrity_mismatches"][0]["dataset_id"] == item["id"]


def test_orphan_and_interrupted_uploads_are_reported_not_deleted(audit_paths):
    root, project = audit_paths
    add_dataset(project, root / "owned.blob", b"owned")
    orphan, temp = root / "orphan.blob", root / ".upload-interrupted"
    orphan.write_bytes(b"orphan")
    temp.write_bytes(b"partial")
    result = audit_upload_storage()
    assert result["orphan_files"] == [".upload-interrupted", "orphan.blob"]
    assert result["temporary_files"] == [".upload-interrupted"]
    assert orphan.exists() and temp.exists()


def test_path_escape_is_flagged_without_reading_external_file(audit_paths, tmp_path):
    _, project = audit_paths
    external = tmp_path / "external.bin"
    external.write_bytes(b"outside")
    item = store.create_dataset(
        project["id"], name="external", file_format="bin", original_filename="x.bin",
        content_path=str(external), sha256="0" * 64, size_bytes=7, crs=None,
        data_role=None, summary={},
    )
    result = audit_upload_storage()
    assert result["unsafe_references"] == [
        {"dataset_id": item["id"], "reason": "path_outside_upload_root"}
    ]
    assert external.read_bytes() == b"outside"


def test_audit_requires_existing_metadata_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(tmp_path / "absent.sqlite3"))
    with pytest.raises(ValueError, match="does not exist"):
        audit_upload_storage()
