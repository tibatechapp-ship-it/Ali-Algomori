# Knowledge-source intake (T2.1) — the "no-second-door" rule.
#
# Every byte of every EXTERNAL knowledge source (PDF/HTML/MD/TXT) enters the
# platform through the SAME reception machinery as data files: the double
# size cap, raw immutable content-addressed quarantine, magic-byte sniffing
# (never extensions), filename sanitization incl. bidi marks, and a
# tamper-evident provenance record for every verdict INCLUDING refusals.
# There is no special fetch path "because the site is trusted": trust is
# earned AFTER the gate, never before it (T2.1, binding).
#
# What this module is NOT: it does not judge the SCIENTIFIC truth of a
# source. It proves "these bytes are what they claim to be and are now
# fingerprinted and quarantined" — nothing more (three-certificate doctrine).
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

from geologia.data_layer.evidence import (
    compile_evidence,
    ev_read,
    ev_unverifiable,
    ev_verified,
)
from geologia.data_layer.provenance import ProvenanceLog
from geologia.data_layer.reception import max_upload_bytes, sanitize_filename
from geologia.data_layer.records import store_dir

SOURCES_SUBDIR = "sources"
REGISTRY_SCHEMA = "geologia-sources/1"

STATUS_PROVEN = "proven"
STATUS_REJECTED = "rejected"
STATUS_ALREADY = "already_registered"

# Knowledge-source families and their allowed extensions (lowercased).
KNOWLEDGE_EXT = {
    "pdf": (".pdf",),
    "html": (".html", ".htm"),
    "md": (".md",),
    "txt": (".txt",),
}

_KS_CODES = {
    "KS_EMPTY_FILE": "error",
    "KS_TOO_LARGE": "error",
    "KS_UNKNOWN_MAGIC": "error",
    "KS_EXT_MISMATCH": "error",
    "KS_NOT_TEXT": "error",
    "KS_NAME_REFUSED": "error",
    "KS_SIZE_OK": "info",
    "KS_MAGIC_MATCH": "info",
    "KS_QUARANTINED": "info",
    "KS_NAME_OK": "info",
    "KS_NAME_SANITIZED": "warning",
}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PDF_MAGIC = b"%PDF-"
_AR_RANGE = (0x0600, 0x06FF)


def _f(code: str, message: str) -> dict:
    return {"code": code, "severity": _KS_CODES[code], "message": message}


def sources_dir() -> Path:
    d = store_dir() / SOURCES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _registry_path() -> Path:
    return store_dir() / "sources_registry.json"


def load_sources_registry() -> List[dict]:
    p = _registry_path()
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw.get("sources", []) if isinstance(raw, dict) else []


def _append_registry(record: dict) -> None:
    p = _registry_path()
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {"schema": REGISTRY_SCHEMA, "sources": []}
    else:
        raw = {"schema": REGISTRY_SCHEMA, "sources": []}
    raw.setdefault("sources", []).append(record)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def _detect_dtype(path: Path, head: bytes) -> Optional[str]:
    ext = path.suffix.lower()
    for dtype, exts in KNOWLEDGE_EXT.items():
        if ext in exts:
            return dtype
    if head.startswith(_PDF_MAGIC):
        return "pdf"
    if head.lstrip()[:1] == b"<":
        return "html"
    try:
        head.decode("utf-8")
        return "txt"
    except UnicodeDecodeError:
        return None


def _magic_verdict(dtype: str, data: bytes) -> Optional[dict]:
    """Content sniffing for the knowledge family; extensions never decide."""
    if dtype == "pdf":
        if not data.startswith(_PDF_MAGIC):
            return _f("KS_UNKNOWN_MAGIC",
                      "declared pdf but bytes do not start with %PDF-")
        return _f("KS_MAGIC_MATCH", "pdf header verified at byte 0")
    if dtype == "html":
        stripped = data[:512].lstrip()
        if not stripped.startswith(b"<"):
            return _f("KS_UNKNOWN_MAGIC",
                      "declared html but bytes do not start with markup '<'")
        return _f("KS_MAGIC_MATCH", "html markup header verified")
    # txt / md must decode as UTF-8 text without control characters.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _f("KS_NOT_TEXT", "declared text source is not valid UTF-8")
    if _CONTROL_RE.search(text):
        return _f("KS_NOT_TEXT",
                  "declared text source contains control characters")
    return _f("KS_MAGIC_MATCH", f"{dtype} text content verified")


def intake_source(path: str, *, source_url: str = "",
                  license_status: str = "unknown",
                  source_version: Optional[str] = None,
                  dtype: str = "auto",
                  provenance_log: Optional[ProvenanceLog] = None,
                  notes: str = "") -> dict:
    """Run one external knowledge source through the single intake gate.

    Contract (T2.1): quarantine -> magic sniffing -> fingerprint -> registry
    -> provenance. A refusal still lands in the provenance log: a refusal
    that leaves no trace is not evidence, it is a shrug.
    """
    p = Path(path)
    findings: List[dict] = []
    if not p.exists() or not p.is_file():
        findings.append(_f("KS_EMPTY_FILE", f"no readable file at {p}"))
        return _rejected_result(p.name, findings, None, provenance_log)
    size = p.stat().st_size
    if size == 0:
        findings.append(_f("KS_EMPTY_FILE", "empty source file"))
        return _rejected_result(p.name, findings, None, provenance_log)
    cap = max_upload_bytes()
    if size > cap:
        findings.append(_f(
            "KS_TOO_LARGE",
            f"source exceeds the {cap}-byte reception cap (GEOLOGIA_MAX_UPLOAD_BYTES)"))
        return _rejected_result(p.name, findings, None, provenance_log)
    findings.append(_f("KS_SIZE_OK", f"size within cap: {size} bytes"))

    data = p.read_bytes()
    effective = dtype
    if effective == "auto":
        effective = _detect_dtype(p, data[:512]) or ""
        if not effective:
            findings.append(_f(
                "KS_UNKNOWN_MAGIC",
                "cannot recognize the source family from bytes or extension"))
            return _rejected_result(p.name, findings, None, provenance_log)
    if p.suffix.lower() not in KNOWLEDGE_EXT.get(effective, ()):
        findings.append(_f(
            "KS_EXT_MISMATCH",
            f"extension {p.suffix!r} does not match dtype {effective!r}"))
        return _rejected_result(p.name, findings, None, provenance_log)
    magic = _magic_verdict(effective, data)
    findings.append(magic)
    if magic["severity"] == "error":
        return _rejected_result(p.name, findings, None, provenance_log)

    sha256 = hashlib.sha256(data).hexdigest()
    safe_name, name_flags = sanitize_filename(p.name)
    if not safe_name or "refused_empty_after_sanitization" in name_flags:
        findings.append(_f("KS_NAME_REFUSED",
                           "sanitization refused the filename"))
        return _rejected_result(p.name, findings, sha256, provenance_log)
    if name_flags:
        findings.append(_f("KS_NAME_SANITIZED", f"name flags: {name_flags}"))
    else:
        findings.append(_f("KS_NAME_OK", "filename needed no sanitization"))

    qdir = sources_dir()
    qpath = qdir / f"{sha256[:16]}_{safe_name}"
    if not qpath.exists():
        # Raw bytes are copied verbatim: the raw source is never modified.
        shutil.copyfile(str(p), str(qpath))
    findings.append(_f("KS_QUARANTINED", f"raw bytes quarantined at {qpath}"))

    registry = load_sources_registry()
    for prev in registry:
        if prev.get("sha256") == sha256:
            result = {
                "status": STATUS_ALREADY,
                "source_id": prev["source_id"],
                "sha256": sha256,
                "quarantine_path": str(qpath),
                "findings": findings,
                "note": "same bytes already registered (content-addressed id is stable)",
            }
            if provenance_log is not None:
                provenance_log.append(
                    "knowledge_source_intake",
                    inputs=[{"path": str(p), "declared_name": p.name}],
                    outputs=[{"source_id": prev["source_id"],
                              "sha256": sha256}],
                    verdict={"status": STATUS_ALREADY},
                )
            return result

    source_id = f"src-{sha256[:12]}"
    record = {
        "source_id": source_id,
        "sha256": sha256,
        "size_bytes": size,
        "dtype": effective,
        "declared_name": p.name,
        "stored_name": safe_name,
        "quarantine_path": str(qpath),
        "source_url": source_url,
        "license_status": license_status,
        "source_version": source_version,
        "notes": notes,
    }
    _append_registry(record)

    evidence = compile_evidence(
        [ev_read("KS_READ_SIZE", f"{size} bytes ingested"),
         ev_read("KS_READ_MAGIC", magic["message"]),
         ev_verified("KS_VERIFIED_QUARANTINE",
                     f"raw bytes content-addressed at {qpath}",
                     check="sha256 quarantine identity"),
         ev_unverifiable(
             "KS_UNVERIFIED_SCIENCE",
             "the scientific accuracy of the source content",
             "an intake gate proves bytes, not geology — claims need "
             "knowledge units with their own truth classes")],
    )
    result = {
        "status": STATUS_PROVEN,
        "source_id": source_id,
        "sha256": sha256,
        "size_bytes": size,
        "dtype": effective,
        "stored_name": safe_name,
        "quarantine_path": str(qpath),
        "source_url": source_url,
        "license_status": license_status,
        "source_version": source_version,
        "findings": findings,
        "evidence": evidence,
    }
    if provenance_log is not None:
        provenance_log.append(
            "knowledge_source_intake",
            inputs=[{"path": str(p), "declared_name": p.name,
                     "source_url": source_url}],
            outputs=[{"source_id": source_id, "sha256": sha256,
                      "stored_name": safe_name}],
            verdict={"status": STATUS_PROVEN, "dtype": effective},
        )
    return result


def _rejected_result(name: str, findings: List[dict], sha: Optional[str],
                     provenance_log: Optional[ProvenanceLog] = None) -> dict:
    result = {
        "status": STATUS_REJECTED,
        "source_id": None,
        "sha256": sha,
        "declared_name": name,
        "findings": findings,
    }
    if provenance_log is not None:
        provenance_log.append(
            "knowledge_source_intake",
            inputs=[{"declared_name": name}],
            outputs=[{"sha256": sha}],
            verdict={"status": STATUS_REJECTED,
                     "codes": [f["code"] for f in findings
                               if f["severity"] == "error"]},
        )
    return result
