# Dataset records: durable registry of real data with checksums and
# validation status. Foundation-phase storage is an atomic JSON file under
# GEOLOGIA_DATA_DIR (default ./.geologia/) — no database yet, by design.
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from geologia.data_layer.validators import validate_file

DATASET_FIELDS_REQUIRED = ("name", "path", "dtype")


def store_dir() -> Path:
    return Path(os.environ.get("GEOLOGIA_DATA_DIR", ".geologia"))


def _read_store() -> dict:
    path = store_dir() / "datasets.json"
    if not path.exists():
        return {"datasets": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_store(data: dict) -> None:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "datasets.json"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def register_dataset(name: str, path: str, dtype: str = "auto",
                     declared_crs: Optional[str] = None,
                     declared_units: Optional[str] = None,
                     license_status: str = "unknown",
                     source_url: Optional[str] = None,
                     derived_from: Optional[str] = None,
                     notes: str = "") -> dict:
    """Register a real dataset file. Content-addressed id (sha256[:12]):
    the same bytes registered twice produce the same dataset id."""
    if not name or not path:
        raise ValueError("name and path are required")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"dataset file not found: {path}")
    if p.stat().st_size == 0:
        raise ValueError("refusing to register an empty file")
    digest = sha256_file(path)
    ds_id = f"ds-{digest[:12]}"
    store = _read_store()
    for ds in store["datasets"]:
        if ds["id"] == ds_id:
            ds["last_seen_at"] = _now()
            _write_store(store)
            return {**ds, "status": "already_registered"}
    record = {
        "id": ds_id,
        "sha256": digest,
        "name": name,
        "path": str(p.resolve()),
        "dtype": dtype,
        "bytes": p.stat().st_size,
        "declared_crs": declared_crs,
        "declared_units": declared_units,
        "license_status": license_status,
        "source_url": source_url,
        "derived_from": derived_from,
        "notes": notes,
        "received_at": _now(),
        "last_seen_at": _now(),
        "validation": None,
        "status": "registered",
    }
    store["datasets"].append(record)
    _write_store(store)
    return {**record, "status": "registered"}


def list_datasets() -> List[dict]:
    return _read_store()["datasets"]


def get_dataset(ds_id: str) -> Optional[dict]:
    for ds in _read_store()["datasets"]:
        if ds["id"] == ds_id:
            return ds
    return None


def verify_checksum(ds_id: str) -> dict:
    ds = get_dataset(ds_id)
    if ds is None:
        raise KeyError(ds_id)
    current_path = Path(ds["path"])
    if not current_path.exists():
        ds["status"] = "file_missing"
        _save(ds)
        return {"dataset_id": ds_id, "checksum_ok": False, "reason": "file_missing"}
    current = sha256_file(str(current_path))
    ok = current == ds["sha256"]
    ds["status"] = "verified" if ok else "checksum_mismatch"
    _save(ds)
    return {"dataset_id": ds_id, "checksum_ok": ok,
            "expected": ds["sha256"][:16], "actual": current[:16]}


def validate_dataset(ds_id: str) -> dict:
    ds = get_dataset(ds_id)
    if ds is None:
        raise KeyError(ds_id)
    if not Path(ds["path"]).exists():
        raise FileNotFoundError(f"dataset file missing: {ds['path']}")
    report = validate_file(ds["path"], ds.get("dtype", "auto"),
                           declared_crs=ds.get("declared_crs"),
                           declared_units=ds.get("declared_units"))
    ds["validation"] = {
        "status": report["status"],
        "findings": report["findings"],
        "validated_at": _now(),
    }
    ds["status"] = "validated_pass" if report["status"] == "pass" else "validated_fail"
    _save(ds)
    return {**ds, "report": report}


def _save(record: dict) -> None:
    store = _read_store()
    for i, ds in enumerate(store["datasets"]):
        if ds["id"] == record["id"]:
            store["datasets"][i] = record
            break
    _write_store(store)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dataset_is_validated_pass(ds_id: str) -> bool:
    ds = get_dataset(ds_id)
    return bool(ds and ds.get("validation", {}) and ds["validation"]["status"] == "pass")
