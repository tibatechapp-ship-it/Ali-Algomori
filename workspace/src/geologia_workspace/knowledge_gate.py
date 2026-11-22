"""Single-door knowledge ingestion for the workspace layer.

Doctrine (T2.1 — no second door): the workspace retrieval index only ever
receives bytes that first passed the governed core's reception gate
(``geologia.knowledge.intake.intake_source``: quarantine -> magic sniffing ->
fingerprint -> registry -> provenance). The workspace's own extension and size
checks are downstream formatting rules, not a gate.

- Accepted (or already-registered) sources are indexed from their original
  path with unchanged metadata; the gate has already fingerprinted and
  quarantined the raw bytes content-addressed by sha256.
- Refused sources are NEVER indexed. The wrapper attaches a provenance log by
  default, so every verdict — including a refusal — leaves a hash-chained
  trace. A refusal without a trace is not evidence, it is a shrug.
- The scientific accuracy of any indexed content remains unverified here:
  the gate proves bytes, not geology. Claims need knowledge units with their
  own truth classes (core T2.2/T2.4 — the next binding step).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from geologia.data_layer.provenance import ProvenanceLog
from geologia.knowledge.intake import (
    STATUS_ALREADY,
    STATUS_PROVEN,
    STATUS_REJECTED,
    intake_source,
)

_GATE_OK = (STATUS_PROVEN, STATUS_ALREADY)

GATE_STATUS_INDEXED = "indexed_via_gate"
GATE_STATUS_REFUSED = "refused_by_gate"
GATE_STATUS_UNRESOLVED = "unresolved_gate_verdict"


def gate_verdict(
    path: str | Path,
    *,
    source_url: str = "",
    license_status: str = "unknown",
    source_version: Optional[str] = None,
    notes: str = "",
    provenance_log: Optional[ProvenanceLog] = None,
) -> dict:
    """Run one source through the core reception gate; return its verdict."""
    return intake_source(
        str(path),
        source_url=source_url,
        license_status=license_status,
        source_version=source_version,
        notes=notes,
        provenance_log=provenance_log,
    )


def gate_ingest_document(path: str | Path, metadata: dict) -> dict:
    """Index a document ONLY after its bytes survived the core reception gate.

    Returns ``{"status": "indexed_via_gate", "gate": ..., "indexed": ...}``
    on success, or ``{"status": "refused_by_gate", "gate": ..., "indexed":
    None}`` when the gate refused — the retrieval index is never touched by a
    refused byte.
    """
    from geologia_workspace import knowledge  # lazy import: avoids an import cycle

    verdict = gate_verdict(
        path,
        source_url=str(metadata.get("source_url") or ""),
        license_status=str(metadata.get("license_status") or "unknown"),
        provenance_log=ProvenanceLog(),
    )
    status = verdict.get("status")
    if status == STATUS_REJECTED:
        return {"status": GATE_STATUS_REFUSED, "gate": verdict, "indexed": None}
    if status not in _GATE_OK:
        return {"status": GATE_STATUS_UNRESOLVED, "gate": verdict, "indexed": None}
    indexed = knowledge.ingest_document(path, metadata)
    return {"status": GATE_STATUS_INDEXED, "gate": verdict, "indexed": indexed}
