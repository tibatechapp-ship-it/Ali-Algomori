"""Read-only integrity and orphan audit for GEOLOGIA upload files."""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any


def audit_upload_storage() -> dict[str, Any]:
    """Report missing, altered, unsafe, and orphan files; never delete anything."""
    db = Path(os.environ.get("GEOLOGIA_DB_PATH", ".geologia/geologia.sqlite3"))
    db = db.expanduser().absolute()
    root = Path(os.environ.get("GEOLOGIA_UPLOAD_DIR", ".geologia/uploads")).expanduser().absolute()
    if db.is_symlink() or not db.is_file():
        raise ValueError("GEOLOGIA metadata database does not exist or is unsafe")
    if root.is_symlink():
        raise ValueError("upload root must not be a symbolic link")
    root_real = root.resolve(strict=False)
    try:
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id,content_path,size_bytes,sha256 FROM datasets ORDER BY id"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise ValueError("could not read dataset metadata") from exc

    missing, changed, unreadable, unsafe = [], [], [], []
    referenced: set[Path] = set()
    verified = 0
    for row in rows:
        raw = Path(row["content_path"]).expanduser()
        path = (raw if raw.is_absolute() else root / raw).absolute()
        try:
            resolved = path.resolve(strict=False)
            if not resolved.is_relative_to(root_real):
                unsafe.append({"dataset_id": row["id"], "reason": "path_outside_upload_root"})
                continue
            cursor, has_link = path, False
            while cursor != root and cursor != cursor.parent:
                if cursor.is_symlink():
                    has_link = True
                    break
                cursor = cursor.parent
            if has_link:
                unsafe.append({"dataset_id": row["id"], "reason": "symlink_in_dataset_path"})
                continue
        except (OSError, RuntimeError):
            unsafe.append({"dataset_id": row["id"], "reason": "unresolvable_dataset_path"})
            continue
        if not path.exists() or not path.is_file():
            missing.append({"dataset_id": row["id"], "path": _relative(path, root)})
            continue
        referenced.add(resolved)
        try:
            size = path.stat().st_size
            digest = _sha256(path)
        except OSError:
            unreadable.append({"dataset_id": row["id"], "path": _relative(path, root)})
            continue
        if size != row["size_bytes"] or digest != row["sha256"]:
            changed.append({
                "dataset_id": row["id"], "path": _relative(path, root),
                "expected_size_bytes": row["size_bytes"], "actual_size_bytes": size,
                "expected_sha256": row["sha256"], "actual_sha256": digest,
            })
        else:
            verified += 1

    orphans, temporary, unsafe_entries = [], [], []
    if root.exists():
        for folder, dirs, files in os.walk(root, followlinks=False):
            current = Path(folder)
            links = [name for name in dirs if (current / name).is_symlink()]
            unsafe_entries.extend(_relative(current / name, root) for name in links)
            dirs[:] = [name for name in dirs if name not in links]
            for name in files:
                path = current / name
                if path.is_symlink():
                    unsafe_entries.append(_relative(path, root))
                    continue
                if path.resolve(strict=False) not in referenced:
                    rel = _relative(path, root)
                    orphans.append(rel)
                    if name.startswith((".upload-", ".reproject-")):
                        temporary.append(rel)
    for collection in (orphans, temporary, unsafe_entries):
        collection.sort()
    count = sum(map(len, (missing, changed, unreadable, unsafe, orphans, unsafe_entries)))
    return {
        "status": "clean" if count == 0 else "issues_found",
        "registered_dataset_count": len(rows),
        "verified_dataset_count": verified,
        "missing_files": missing,
        "integrity_mismatches": changed,
        "unreadable_files": unreadable,
        "unsafe_references": unsafe,
        "orphan_files": orphans,
        "temporary_files": temporary,
        "unsafe_storage_entries": unsafe_entries,
        "automatic_cleanup": False,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError:
        return "<outside-upload-root>"
