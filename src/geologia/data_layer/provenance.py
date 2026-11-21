"""Data provenance: sources, transformations, tool versions — tamper-evident.

The binding question this module answers: when the platform shows a
result, CAN IT PROVE which file, which version of which tool, and which
transformations produced it — and that nobody rewrote the story in
between?

Design:
- Append-only JSON Lines log. Nothing is ever edited in place; corrections
  are new records.
- Hash chain: each record's `record_hash` is sha256 over its canonical
  JSON, and each record carries `parent_hash` = previous record's hash,
  with the genesis chain rooted at 64 zeros. Deleting, editing or
  reordering any record breaks `verify()`.
- Every record snapshots `tool_versions()` at write time, so "verified
  with pyproj 3.8.0" is a fact about the past, not a hope about the
  present.

This is provenance, not a blockchain: it proves tampering, not identity.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


GENESIS_HASH = "0" * 64
SCHEMA = "geologia-provenance/1"

PROV_CODES = {
    "PROV_OK": "info",
    "PROV_CHAIN_BROKEN": "error",
    "PROV_HASH_MISMATCH": "error",
    "PROV_SEQ_GAP": "error",
    "PROV_LOG_EMPTY": "warning",
}

__all__ = ["GENESIS_HASH", "SCHEMA", "PROV_CODES", "tool_versions",
           "ProvenanceLog", "ref_file", "default_log_path"]


def _pf(code: str, message: str) -> dict:
    return {"code": code, "severity": PROV_CODES[code], "message": message}


def _lib_version(dist: str) -> Optional[str]:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def tool_versions() -> Dict[str, Optional[str]]:
    """Versions of every tool that can influence a verification result.

    Absent libraries are reported as None — the log must show that, e.g.,
    a claim was made WITHOUT pyproj rather than silently assuming it.
    """
    import geologia
    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "geologia": geologia.__version__,
        "pydantic": _lib_version("pydantic"),
        "lasio": _lib_version("lasio"),
        "tifffile": _lib_version("tifffile"),
        "pyproj": _lib_version("pyproj"),
        "numpy": _lib_version("numpy"),
        "sqlite3": platform.python_implementation() + "/"
                   + __import__("sqlite3").sqlite_version,
    }



def ref_file(path: str) -> dict:
    """Input/output reference for a file: name + sha256 + size."""
    import hashlib as _h
    p = Path(path)
    h = _h.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return {"name": p.name, "sha256": h.hexdigest(), "bytes": p.stat().st_size}


def ref_value(name: str, value: Any) -> dict:
    """Input/output reference for a value (e.g. declared_crs, transform)."""
    return {"name": name, "value": value}


def default_log_path() -> Path:
    """Default provenance log, colocated with the dataset store."""
    import os
    return Path(os.environ.get("GEOLOGIA_DATA_DIR", ".geologia")) / \
        "provenance.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(rec: dict) -> str:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


class ProvenanceLog:
    """Append-only, hash-chained provenance log (JSON Lines)."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else default_log_path()

    # -- reading ------------------------------------------------------------
    def records(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    # -- appending ----------------------------------------------------------
    def append(self, action: str, inputs: List[dict],
               outputs: List[dict], verdict: dict,
               extra: Optional[dict] = None) -> dict:
        """Append one event; returns the stored record (with its hash)."""
        recs = self.records()
        parent = recs[-1]["record_hash"] if recs else GENESIS_HASH
        rec: dict = {
            "schema": SCHEMA,
            "seq": len(recs) + 1,
            "ts": _now(),
            "action": action,
            "tool_versions": tool_versions(),
            "inputs": inputs,
            "outputs": outputs,
            "verdict": verdict,
        }
        if extra:
            rec["extra"] = extra
        rec["parent_hash"] = parent
        rec["record_hash"] = hashlib.sha256(
            _canonical(rec).encode("utf-8")).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(rec) + "\n")
        return rec

    # -- verification -------------------------------------------------------
    def verify(self) -> dict:
        """Recompute the whole chain. Any edit/deletion/reorder is detected.

        Returns {ok, count, findings, tool_versions_last}. This is the
        function that turns a log into EVIDENCE: an unverifiable log is
        worth exactly nothing.
        """
        recs = self.records()
        findings: List[dict] = []
        if not recs:
            findings.append(_pf("PROV_LOG_EMPTY", "provenance log is empty"))
            return {"ok": False, "count": 0, "findings": findings,
                    "tool_versions_last": None}
        parent = GENESIS_HASH
        for i, rec in enumerate(recs, start=1):
            stored = rec.get("record_hash")
            body = {k: v for k, v in rec.items() if k != "record_hash"}
            recomputed = hashlib.sha256(
                _canonical(body).encode("utf-8")).hexdigest()
            if stored != recomputed:
                findings.append(_pf(
                    "PROV_HASH_MISMATCH",
                    f"record {i}: stored hash does not match its content "
                    f"— record was modified after writing"))
            if rec.get("parent_hash") != parent:
                findings.append(_pf(
                    "PROV_CHAIN_BROKEN",
                    f"record {i}: parent link broken (expected "
                    f"{parent[:12]}…, found {str(rec.get('parent_hash'))[:12]}…)"
                    f" — a record was deleted, inserted or reordered"))
            if rec.get("seq") != i:
                findings.append(_pf(
                    "PROV_SEQ_GAP",
                    f"record {i}: seq {rec.get('seq')} — sequence gap"))
            parent = stored
        # The stored `parent_hash` of the NEXT record uses the stored hash of
        # this record, so even a recomputed-content record breaks the chain.
        return {"ok": not any(f["severity"] == "error"
                              for f in findings),
                "count": len(recs), "findings": findings,
                "tool_versions_last": recs[-1].get("tool_versions")}
