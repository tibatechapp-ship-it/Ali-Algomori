"""Evidence honesty model for the data layer.

Binding contract since 0.6.0: the data layer must be able to PROVE three
separable things about every file it touches —

- read          what was actually parsed out of the bytes (no correctness
                claim attached);
- verified      what was checked against an independent reference, rule or
                counter-computation (with the check named);
- unverifiable  what was declared or assumed but could NOT be confirmed,
                with the concrete reason it cannot be confirmed.

A validation report that cannot name what it cannot confirm is not a
validation report — it is a guess with formatting. CI green does not
certify geological validity; this structure exists so the difference
between "checked" and "assumed" is machine-visible and testable.

Every evidence item is validated against a strict shape at compile time
(`compile_evidence`), so a reader cannot smuggle in a malformed claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

LEVELS = ("read", "verified", "unverifiable")

# Statuses produced by prove_file(): the three-tier honesty verdict.
PROOF_REFUSED = "refused"
PROOF_PROVEN = "proven"
PROOF_PROVEN_WITH_GAPS = "proven_with_unverified_claims"

__all__ = [
    "LEVELS", "PROOF_REFUSED", "PROOF_PROVEN", "PROOF_PROVEN_WITH_GAPS",
    "ev_read", "ev_verified", "ev_unverifiable", "compile_evidence",
    "file_identity_evidence", "findings_to_evidence", "prove_file",
]


def ev_read(code: str, detail: str) -> dict:
    """A structural fact that was parsed from the bytes (no truth claim)."""
    return {"code": code, "level": "read", "detail": detail}


def ev_verified(code: str, detail: str, check: str) -> dict:
    """A claim that was confirmed against a named, independent check."""
    return {"code": code, "level": "verified", "detail": detail, "check": check}


def ev_unverifiable(code: str, detail: str, reason: str) -> dict:
    """A claim the layer cannot confirm — the reason must be concrete."""
    return {"code": code, "level": "unverifiable", "detail": detail,
            "reason": reason}


def _validate_item(item: dict) -> None:
    """Honesty invariant: every claim must carry its level and justification.

    - read          requires `detail`
    - verified      requires `detail` AND `check` (an unnamed check is a
                    claim, not a verification)
    - unverifiable  requires `detail` AND `reason` (unexplained silence is
                    indistinguishable from a lie)
    """
    if not isinstance(item, dict) or item.get("level") not in LEVELS:
        raise ValueError(f"evidence item malformed: {item!r}")
    code, detail = item.get("code"), item.get("detail")
    if not code or not isinstance(detail, str) or not detail:
        raise ValueError(f"evidence item missing code/detail: {item!r}")
    if item["level"] == "verified" and not item.get("check"):
        raise ValueError(f"verified claim without named check: {code}")
    if item["level"] == "unverifiable" and not item.get("reason"):
        raise ValueError(f"unverifiable claim without reason: {code}")


def compile_evidence(*groups: List[dict]) -> Dict[str, Any]:
    """Bucket validated evidence items into the three-level structure.

    Items keep their `level` key so compiled triples can be recompiled
    (e.g. prove_file merging reader evidence with file identity)."""
    out: Dict[str, Any] = {lvl: [] for lvl in LEVELS}
    for group in groups:
        for item in (group or []):
            _validate_item(item)
            out[item["level"]].append(dict(item))
    out["counts"] = {lvl: len(out[lvl]) for lvl in LEVELS}
    return out


def file_identity_evidence(path: str) -> List[dict]:
    """Read-level identity: what the layer can state about the bytes itself."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return [
        ev_read("FILE_SHA256", f"sha256 {h.hexdigest()} over {p.stat().st_size} bytes"),
        ev_read("FILE_SIZE", f"{p.stat().st_size} bytes"),
    ]


# Explicit, closed mapping from validator findings to evidence levels. Only
# codes listed here are translated; everything else stays as a raw finding.
# Deliberately minimal: translating a finding into "verified" without an
# independent check would defeat the model.
_FINDING_LEVEL_MAP = {
    "CRS_DECLARED_OK": ("verified", "declared CRS is consistent with the "
                        "observed coordinate value ranges"),
    "CRS_NONE_DECLARED": ("unverifiable", "no CRS declared in or with the "
                          "file; the spatial reference is left to assumption"),
    "CRS_AXIS_ORDER_NOTE": ("unverifiable", "axis order cannot be confirmed "
                            "from the file alone"),
    "CRS_UNITS_SUSPECT": ("unverifiable", "declared units contradict "
                          "coordinate magnitudes"),
    "CRS_LOCAL_NO_TRANSFORM": ("unverifiable", "local/depth CRS: no "
                               "transformation to a geodetic reference "
                               "exists or is declared"),
    "CRS_GEOJSON_CRS_UNRECOGNIZED": ("unverifiable", "CRS string present but "
                                     "unrecognized; cannot map to EPSG"),
}


def findings_to_evidence(findings: List[dict]) -> Dict[str, List[dict]]:
    """Translate a closed set of known findings into evidence items."""
    read: List[dict] = []
    verified: List[dict] = []
    unverifiable: List[dict] = []
    for f in findings or []:
        m = _FINDING_LEVEL_MAP.get(f.get("code", ""))
        if m is None:
            continue
        level, why = m
        if level == "verified":
            verified.append(ev_verified(f["code"], f["message"], check=why))
        else:
            unverifiable.append(ev_unverifiable(f["code"], f["message"],
                                                reason=why))
    return {"read": read, "verified": verified, "unverifiable": unverifiable}


def _empty_evidence() -> Dict[str, Any]:
    return compile_evidence()


def prove_file(path: str, dtype: str = "auto",
               declared_crs: Optional[str] = None,
               declared_units: Optional[str] = None,
               provenance: Any = None) -> dict:
    """Full honesty report for one file: format validation + evidence triple.

    Returns the validate_file() report plus:
    - evidence:   {read, verified, unverifiable, counts}
    - proof_status: refused | proven | proven_with_unverified_claims

    A file is `proven` only when format validation passed AND every
    load-bearing claim was independently checked. Any unverifiable claim on
    a passing file yields `proven_with_unverified_claims` — never silently
    `proven`. When `provenance` (a ProvenanceLog) is given, the proof event
    is appended to the tamper-evident chain.
    """
    from .validators import validate_file  # lazy: avoid import cycle

    report = validate_file(path, dtype=dtype, declared_crs=declared_crs,
                           declared_units=declared_units)
    evidence = report.get("evidence")
    if not evidence:
        translated = findings_to_evidence(report.get("findings", []))
        evidence = compile_evidence(file_identity_evidence(path),
                                    translated["read"],
                                    translated["verified"],
                                    translated["unverifiable"])
    else:
        # Ensure identity is always part of "what was read".
        codes = {i["code"] for i in evidence["read"]}
        extra = [i for i in file_identity_evidence(path)
                 if i["code"] not in codes]
        if extra:
            evidence = compile_evidence(evidence["read"] + extra,
                                        evidence["verified"],
                                        evidence["unverifiable"])

    if report["status"] == "fail":
        proof_status = PROOF_REFUSED
    elif evidence["counts"]["unverifiable"] == 0:
        proof_status = PROOF_PROVEN
    else:
        proof_status = PROOF_PROVEN_WITH_GAPS

    result = {**report, "evidence": evidence, "proof_status": proof_status}

    if provenance is not None:
        provenance.append(
            action="prove_file",
            inputs=[{"name": Path(path).name,
                     "sha256": next((i["detail"].split()[-3]
                                     for i in evidence["read"]
                                     if i["code"] == "FILE_SHA256"), None),
                     "bytes": Path(path).stat().st_size}],
            outputs=[{"name": "proof_report",
                      "status": report["status"],
                      "proof_status": proof_status}],
            verdict={"status": report["status"], "proof_status": proof_status,
                     "codes": [f["code"] for f in report["findings"]]},
        )
    return result
