"""Upload ingestion: quarantine -> reception gate -> registration -> proof.

This module is the LIBRARY-level glue between the HTTP boundary and the
data layer (ADR-0007). It deliberately contains no HTTP concepts: the
FastAPI endpoint streams bytes and enforces the transport cap, everything
below is pure-Python and testable without a server (Termux-safe).

The ingestion contract, in strict order:

1. STREAM CAP     bytes are consumed with the reception size cap
                  (GEOLOGIA_MAX_UPLOAD_BYTES); an oversized stream is
                  refused WITHOUT touching disk (SEC_TOO_LARGE).
2. QUARANTINE     accepted-for-inspection bytes land in
                  GEOLOGIA_DATA_DIR/uploads/<sha256>_<safe_name> — raw,
                  immutable, content-addressed. The raw upload is never
                  modified (DATA_GOVERNANCE: «الخام غير قابل للتعديل»);
                  sanitization applies to the NAME, not the bytes.
3. RECEPTION      check_upload() with run_content_validation=False: the
                  SECURITY verdict only (size, magic, archive safety,
                  hygiene). Rejected here -> nothing is registered, and
                  the refusal is appended to the provenance chain.
4. REGISTRATION   register_dataset(): content-addressed id, the record
                  keeps the sanitized name; provenance records the
                  declared client name verbatim as a value reference.
                  Files that pass SECURITY but fail CONTENT are still
                  registered — with an honest proof_refused record
                  status that no task gate will ever accept (mirrors
                  the path-based register->validate ledger semantics).
5. PROOF          prove_file(): ONE parse producing the honest verdict —
                  refused / proven / proven_with_unverified_claims — with
                  the three-level evidence triple, appended to the
                  tamper-evident provenance chain.
6. ARCHIVES       zip/gzip uploads are quarantined and scanned but NEVER
                  registered as data (ADR-0005: members must be inspected
                  individually first) — the verdict is needs_review with
                  an explicit reason, not a silent pass.

Every verdict — including rejections — is appended to the provenance log:
a refusal that leaves no trace is not evidence, it is a shrug.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from geologia.data_layer import records as ds
from geologia.data_layer.evidence import prove_file
from geologia.data_layer.provenance import ProvenanceLog, ref_value
from geologia.data_layer.reception import check_upload, max_upload_bytes, \
    sanitize_filename

UPLOADS_SUBDIR = "uploads"

# dtypes for which a full content proof runs (must stay in lockstep with
# reception.TEXT_DTYPE_MAGIC_OK — the security gate refuses anything else).
PROOF_DTYPE_OK = ("las", "csv", "geojson", "tiff", "gpkg")

STATUS_REJECTED = "rejected"
STATUS_REVIEW = "needs_review"

__all__ = ["UPLOADS_SUBDIR", "PROOF_DTYPE_OK", "STATUS_REJECTED",
           "STATUS_REVIEW", "uploads_dir", "ingest_stream", "ingest_bytes"]


def uploads_dir() -> Path:
    d = ds.store_dir() / UPLOADS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rejected(filename: str, reception: dict,
              note: Optional[str] = None) -> dict:
    return {
        "status": STATUS_REJECTED,
        "dataset_id": None,
        "sha256": reception.get("sha256"),
        "declared_name": filename,
        "stored_name": reception.get("sanitized_name"),
        "quarantine_path": reception.get("file"),
        "reception": reception,
        "proof": None,
        "review_reason": note,
    }


def ingest_stream(chunks: Iterable[bytes], filename: str,
                  dtype: str = "auto",
                  declared_crs: Optional[str] = None,
                  declared_units: Optional[str] = None,
                  provenance_log: Optional[ProvenanceLog] = None) -> dict:
    """Ingest an uploaded file given an iterator of byte chunks.

    Enforces the reception size cap while consuming the stream, quarantines
    the raw bytes immutably, runs the security gate, then (for known data
    types) registers the dataset and produces the honest proof verdict.
    See the module docstring for the full contract.
    """
    cap = max_upload_bytes()
    digest = hashlib.sha256()
    total = 0
    # Spill to disk beyond 8 MiB: a 100 MiB upload must not be held in RAM.
    spooled = tempfile.SpooledTemporaryFile(max_size=8 << 20)
    for chunk in chunks:
        if not chunk:
            continue
        total += len(chunk)
        if total > cap:
            spooled.close()
            reception = {
                "status": STATUS_REJECTED, "dtype": dtype,
                "findings": [{"code": "SEC_TOO_LARGE", "severity": "error",
                              "message": f"stream exceeded the {cap}-byte "
                                         f"reception cap "
                                         f"(GEOLOGIA_MAX_UPLOAD_BYTES) at "
                                         f">{total} bytes"}],
                "sha256": None,
            }
            if provenance_log is not None:
                provenance_log.append(
                    action="upload_rejected",
                    inputs=[ref_value("declared_name", filename),
                            ref_value("cap_bytes", cap)],
                    outputs=[],
                    verdict={"status": STATUS_REJECTED,
                             "codes": ["SEC_TOO_LARGE"]})
            return _rejected(filename, reception,
                             note=f"stream size {total} exceeds cap {cap}")
        digest.update(chunk)
        spooled.write(chunk)
    sha = digest.hexdigest()
    if total == 0:
        spooled.close()
        reception = {
            "status": STATUS_REJECTED, "dtype": dtype,
            "findings": [{"code": "SEC_EMPTY_FILE", "severity": "error",
                          "message": "upload is empty — refusing"}],
            "sha256": None,
        }
        if provenance_log is not None:
            provenance_log.append(
                action="upload_rejected",
                inputs=[ref_value("declared_name", filename)],
                outputs=[],
                verdict={"status": STATUS_REJECTED,
                         "codes": ["SEC_EMPTY_FILE"]})
        return _rejected(filename, reception, note="empty upload")
    if not filename or not filename.strip():
        spooled.close()
        reception = {
            "status": STATUS_REJECTED, "dtype": dtype,
            "findings": [{"code": "SEC_NAME_REFUSED", "severity": "error",
                          "message": "declared filename is empty — refusing"}],
            "sha256": sha,
        }
        if provenance_log is not None:
            provenance_log.append(
                action="upload_rejected",
                inputs=[ref_value("declared_name", filename),
                        ref_value("sha256", sha)],
                outputs=[],
                verdict={"status": STATUS_REJECTED,
                         "codes": ["SEC_NAME_REFUSED"]})
        return _rejected(filename, reception, note="empty filename")

    # -- quarantine: raw bytes, immutable, content-addressed ------------------
    safe_name, _name_flags = sanitize_filename(filename)
    quarantine = uploads_dir() / f"{sha}_{safe_name}"
    spooled.seek(0)
    with tempfile.NamedTemporaryFile(dir=uploads_dir(), delete=False) as tmp:
        while True:
            block = spooled.read(1 << 20)
            if not block:
                break
            tmp.write(block)
        tmp_name = tmp.name
    spooled.close()
    os.replace(tmp_name, quarantine)  # atomic: readers see full bytes only

    # -- reception security gate (content proof runs later, exactly once) ----
    reception = check_upload(str(quarantine), declared_name=filename,
                             dtype=dtype, declared_crs=declared_crs,
                             declared_units=declared_units,
                             run_content_validation=False)
    codes = [f["code"] for f in reception["findings"]
             if f["severity"] == "error"]

    if provenance_log is not None:
        provenance_log.append(
            action="upload_quarantined",
            inputs=[{"name": safe_name, "sha256": sha, "bytes": total},
                    ref_value("declared_name", filename),
                    ref_value("declared_crs", declared_crs),
                    ref_value("declared_units", declared_units)],
            outputs=[{"name": "quarantine_path", "value": str(quarantine)}],
            verdict={"status": reception["status"], "codes": codes})

    if reception["status"] == STATUS_REJECTED:
        if provenance_log is not None:
            provenance_log.append(
                action="upload_rejected",
                inputs=[{"name": safe_name, "sha256": sha, "bytes": total}],
                outputs=[],
                verdict={"status": STATUS_REJECTED, "codes": codes})
        return _rejected(filename, reception)

    kind = reception.get("sniffed")
    if kind in ("zip", "gzip"):
        # ADR-0005: archives are not data until their members are inspected
        # individually. Quarantine + scan verdict only — no registration.
        return {
            "status": STATUS_REVIEW,
            "dataset_id": None,
            "sha256": sha,
            "declared_name": filename,
            "stored_name": safe_name,
            "quarantine_path": str(quarantine),
            "reception": reception,
            "proof": None,
            "review_reason": "archive: members must be inspected and "
                             "individually validated before any of them "
                             "can become data (ADR-0005)",
        }

    if reception.get("dtype") not in PROOF_DTYPE_OK:
        return {
            "status": STATUS_REVIEW,
            "dataset_id": None,
            "sha256": sha,
            "declared_name": filename,
            "stored_name": safe_name,
            "quarantine_path": str(quarantine),
            "reception": reception,
            "proof": None,
            "review_reason": f"no content proof path for dtype "
                             f"{reception.get('dtype')!r} — quarantined "
                             f"for manual review",
        }

    # -- registration (content-addressed) -------------------------------------
    record = ds.register_dataset(
        name=safe_name, path=str(quarantine), dtype=reception["dtype"],
        declared_crs=declared_crs, declared_units=declared_units,
        notes="received through the upload gate (ADR-0007)")
    ds_id = record["id"]
    if provenance_log is not None:
        provenance_log.append(
            action="upload_registered",
            inputs=[{"name": safe_name, "sha256": sha, "bytes": total}],
            outputs=[{"name": "dataset_id", "value": ds_id}],
            verdict={"status": record["status"]})

    # -- proof: one parse, honest verdict, provenance appended ----------------
    proof = prove_file(str(quarantine), dtype=reception["dtype"],
                       declared_crs=declared_crs,
                       declared_units=declared_units,
                       provenance=provenance_log)
    ds.attach_upload_proof(ds_id, proof)

    return {
        "status": proof["proof_status"],
        "dataset_id": ds_id,
        "sha256": sha,
        "declared_name": filename,
        "stored_name": safe_name,
        "quarantine_path": str(quarantine),
        "reception": reception,
        "proof": proof,
        "review_reason": None,
    }


def ingest_bytes(data: bytes, filename: str,
                 dtype: str = "auto",
                 declared_crs: Optional[str] = None,
                 declared_units: Optional[str] = None,
                 provenance_log: Optional[ProvenanceLog] = None) -> dict:
    """Ingest an in-memory payload (thin wrapper over ingest_stream)."""
    return ingest_stream(iter([data]), filename, dtype=dtype,
                         declared_crs=declared_crs,
                         declared_units=declared_units,
                         provenance_log=provenance_log)
