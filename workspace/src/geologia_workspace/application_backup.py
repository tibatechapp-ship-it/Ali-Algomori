"""Self-contained offline backup/restore for GEOLOGIA local data."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from typing import Any

from geologia_workspace.database_backup import backup_database

FORMAT_VERSION = 1


def _path(env: str, default: str) -> Path:
    return Path(os.environ.get(env, default)).expanduser().absolute()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {"size_bytes": path.stat().st_size, "sha256": _hash(path)}


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe backup path")
    if "\\" in value or ":" in value:
        raise ValueError("invalid portable backup path")
    return path


def _verify_file(path: Path, record: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("backup file is missing or unsafe")
    if path.stat().st_size != record.get("size_bytes") or _hash(path) != record.get("sha256"):
        raise ValueError("backup file checksum or size mismatch")


def _dataset_rows(db: Path) -> list[sqlite3.Row]:
    try:
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT id,content_path,size_bytes,sha256 FROM datasets ORDER BY id"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise ValueError("could not read dataset metadata") from exc


def _source_dataset_path(value: str, root: Path) -> tuple[Path, str]:
    raw = Path(value).expanduser()
    path = (raw if raw.is_absolute() else root / raw).absolute()
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("dataset path escapes upload root")
    cursor = path
    while cursor != root and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError("symlinked dataset path is not supported")
        cursor = cursor.parent
    if not path.is_file():
        raise ValueError("registered dataset file is missing")
    return path, path.relative_to(root).as_posix()


def create_application_backup(destination: str | os.PathLike[str]) -> dict[str, Any]:
    """Create an atomic self-contained snapshot. Stop GEOLOGIA before calling."""
    target = Path(destination).expanduser().absolute()
    db = _path("GEOLOGIA_DB_PATH", ".geologia/geologia.sqlite3")
    knowledge = Path(os.environ.get(
        "GEOLOGIA_KNOWLEDGE_DB_PATH", str(db.parent / "knowledge.sqlite3")
    )).expanduser().absolute()
    root = _path("GEOLOGIA_UPLOAD_DIR", ".geologia/uploads")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if db.is_symlink() or not db.is_file() or knowledge.is_symlink() or root.is_symlink():
        raise ValueError("application storage paths are missing or unsafe")
    if db == knowledge:
        raise ValueError("metadata and knowledge databases must be different")
    if target.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
        raise ValueError("backup destination must be outside upload storage")

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        uploads_dir = stage / "uploads"
        uploads_dir.mkdir()
        db_files = {}
        metadata_copy = stage / "metadata.sqlite3"
        backup_database(db, metadata_copy)
        db_files["metadata.sqlite3"] = _record(metadata_copy)
        if knowledge.exists():
            knowledge_copy = stage / "knowledge.sqlite3"
            backup_database(knowledge, knowledge_copy)
            db_files["knowledge.sqlite3"] = _record(knowledge_copy)

        dataset_files = {}
        for row in _dataset_rows(db):
            source, relative = _source_dataset_path(row["content_path"], root)
            if source.stat().st_size != row["size_bytes"] or _hash(source) != row["sha256"]:
                raise ValueError(f"dataset integrity mismatch: {row['id']}")
            dataset_files[row["id"]] = relative

        upload_files = []
        if root.exists():
            for folder, dirs, names in os.walk(root, followlinks=False):
                current = Path(folder)
                if any((current / name).is_symlink() for name in dirs):
                    raise ValueError("upload tree contains a symlink directory")
                for name in names:
                    source = current / name
                    if source.is_symlink() or not source.is_file():
                        raise ValueError("upload tree contains an unsafe file")
                    relative = source.relative_to(root).as_posix()
                    safe = _relative(relative)
                    output = uploads_dir.joinpath(*safe.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
                    upload_files.append({"path": relative, **_record(output)})
        upload_files.sort(key=lambda item: item["path"])
        manifest = {
            "format": "geologia.application-backup",
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "databases": db_files,
            "datasets": dataset_files,
            "uploads": upload_files,
            "offline_snapshot": True,
            "manifest_signed": False,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        os.replace(stage, target)
        return {
            "status": "created", "destination": str(target),
            "dataset_count": len(dataset_files), "upload_file_count": len(upload_files),
            "knowledge_database_included": "knowledge.sqlite3" in db_files,
            "manifest_sha256": _hash(target / "manifest.json"),
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def restore_application_backup(
    backup_directory: str | os.PathLike[str],
    destination: str | os.PathLike[str],
) -> dict[str, Any]:
    """Restore a verified snapshot into a new directory; existing data is never replaced."""
    source = Path(backup_directory).expanduser().absolute()
    target = Path(destination).expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("backup directory is missing or unsafe")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    manifest_path = source / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or (source / "uploads").is_symlink():
        raise ValueError("backup manifest or upload directory is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("backup manifest is invalid") from exc
    if manifest.get("format") != "geologia.application-backup" or manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported application backup format")
    db_records, datasets, uploads = (
        manifest.get("databases"), manifest.get("datasets"), manifest.get("uploads")
    )
    if not isinstance(db_records, dict) or "metadata.sqlite3" not in db_records:
        raise ValueError("metadata database is missing from backup manifest")
    if not isinstance(datasets, dict) or not isinstance(uploads, list):
        raise ValueError("backup inventory is invalid")

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        uploads_stage = stage / "uploads"
        uploads_stage.mkdir()
        database_paths = {}
        for name, record in db_records.items():
            if name not in {"metadata.sqlite3", "knowledge.sqlite3"}:
                raise ValueError("unexpected database file in backup")
            source_db = source / name
            _verify_file(source_db, record)
            output_db = stage / name
            backup_database(source_db, output_db)
            database_paths[name] = output_db

        expected = {}
        for record in uploads:
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                raise ValueError("invalid upload manifest entry")
            relative = _relative(record["path"]).as_posix()
            if relative in expected:
                raise ValueError("duplicate upload path in manifest")
            expected[relative] = record

        actual = set()
        upload_source_root = source / "uploads"
        if not upload_source_root.is_dir() or upload_source_root.is_symlink():
            raise ValueError("backup upload directory is missing or unsafe")
        for folder, dirs, names in os.walk(upload_source_root, followlinks=False):
            current = Path(folder)
            if any((current / name).is_symlink() for name in dirs):
                raise ValueError("backup upload tree contains symlink directory")
            for name in names:
                path = current / name
                if path.is_symlink():
                    raise ValueError("backup upload tree contains symlink file")
                actual.add(path.relative_to(upload_source_root).as_posix())
        if actual != set(expected):
            raise ValueError("upload inventory does not match backup contents")

        upload_root_real = upload_source_root.resolve(strict=True)
        for relative, record in expected.items():
            source_file = upload_source_root / relative
            if not source_file.resolve(strict=True).is_relative_to(upload_root_real):
                raise ValueError("backup upload path escapes its upload directory")
            _verify_file(source_file, record)
            output = uploads_stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, output)

        metadata = database_paths["metadata.sqlite3"]
        with closing(sqlite3.connect(metadata)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            current_ids = {row[0] for row in conn.execute("SELECT id FROM datasets")}
            if current_ids != set(datasets):
                raise ValueError("dataset inventory does not match metadata database")
            for dataset_id, value in datasets.items():
                relative = _relative(value).as_posix()
                if relative not in expected:
                    raise ValueError("dataset file missing from backup inventory")
                conn.execute(
                    "UPDATE datasets SET content_path=? WHERE id=?",
                    (str(target / "uploads" / relative), dataset_id),
                )
            conn.commit()
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("restored metadata database failed integrity check")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("restored metadata database has foreign-key violations")
        for path in database_paths.values():
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("restored SQLite database failed integrity check")
        shutil.copy2(manifest_path, stage / "manifest.json")
        os.replace(stage, target)
        return {
            "status": "restored", "destination": str(target),
            "dataset_count": len(datasets), "upload_file_count": len(uploads),
            "knowledge_database_included": "knowledge.sqlite3" in database_paths,
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
