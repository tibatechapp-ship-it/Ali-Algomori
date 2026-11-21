"""Reference dataset integrity + frozen transformation verification.

Two independent proof duties live here:

1. Transformation validity: the frozen control points in
   `geologia/data/reference/transformations.json` were computed once and
   reviewed by hand. If the installed transformation engine disagrees with
   them beyond tolerance, that is a HARD error — the layer refuses to trust
   its own transformations. When pyproj is absent, the checks are honestly
   reported as unverifiable instead of skipped-as-passing.

2. Reference corpus integrity: a reference dataset only has value if the
   files it contains are byte-identical to what was certified.
   `verify_reference_dir()` recomputes hashes against a manifest and fails
   loudly on any drift — a reference that silently changed is not a
   reference, it is a moving target.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from .evidence import compile_evidence, ev_read, ev_unverifiable, ev_verified

REFERENCE_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "reference"

REF_CODES = {
    "REF_DIR_OK": "info",
    "REF_FILE_MISSING": "error",
    "REF_HASH_MISMATCH": "error",
    "REF_MANIFEST_INVALID": "error",
    "XFORM_OK": "info",
    "XFORM_MISMATCH": "error",
    "XFORM_ENGINE_ABSENT": "warning",
}

__all__ = ["REFERENCE_DATA_DIR", "REF_CODES", "load_transformations",
           "verify_transformations", "verify_reference_dir",
           "transformations_fingerprint"]


def _ff(code: str, message: str) -> dict:
    return {"code": code, "severity": REF_CODES[code], "message": message}


def load_transformations(path: Optional[str] = None) -> dict:
    p = Path(path) if path else REFERENCE_DATA_DIR / "transformations.json"
    return json.loads(p.read_text(encoding="utf-8"))


def transformations_fingerprint(path: Optional[str] = None) -> str:
    """sha256 of the frozen reference itself — provenance can pin this."""
    p = Path(path) if path else REFERENCE_DATA_DIR / "transformations.json"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_transformations(transformations: Optional[dict] = None,
                           reference_path: Optional[str] = None) -> dict:
    """Run every frozen control point through the installed engine.

    Returns {ok, findings, evidence, checked, unverifiable} where:
    - ok=True  only when every present check matched within tolerance;
    - engines absent => unverifiable evidence entries, ok stays True ONLY
      if there is nothing contradicting (honest gap, not a failure);
    - any value mismatch => XFORM_MISMATCH error => ok=False.

    CI green is NOT a certificate of geological validity: this function is
    the certificate mechanism, and its result must be re-proven on every
    engine change.
    """
    ref = transformations if transformations is not None else \
        load_transformations(reference_path)
    findings: List[dict] = []
    read_l, ver_l, unv_l = [], [], []
    checked = 0
    fingerprint = transformations_fingerprint(reference_path)
    read_l.append(ev_read("REF_TRANSFORMATIONS_READ",
                          f"reference transformations loaded, sha256 "
                          f"{fingerprint[:16]}…, {len(ref['transformations'])} "
                          f"control points"))

    try:
        import pyproj
        engine = f"pyproj {pyproj.__version__}"
        engine_ok = True
    except ImportError:
        engine = None
        engine_ok = False

    if not engine_ok:
        unv_l.append(ev_unverifiable(
            "XFORM_ENGINE_ABSENT",
            "transformation validity not checked: pyproj is not installed",
            reason="without an independent transformation engine the frozen "
                   "values cannot be re-proven; the layer will not claim "
                   "transformation validity"))

    for t in ref["transformations"]:
        name = t["name"]
        if not engine_ok:
            unv_l.append(ev_unverifiable(
                "XFORM_ENGINE_ABSENT",
                f"control point {name} not re-proven",
                reason="pyproj absent"))
            continue
        try:
            from pyproj import Transformer
            tr = Transformer.from_crs(t["from_crs"], t["to_crs"],
                                      always_xy=True)
            x, y = tr.transform(t["x"], t["y"])
        except Exception as exc:
            findings.append(_ff("XFORM_MISMATCH",
                                f"{name}: engine failed to transform "
                                f"({type(exc).__name__}: {exc})"))
            continue
        err_x = abs(x - t["expected_x"])
        err_y = abs(y - t["expected_y"])
        err = max(err_x, err_y)
        if err <= t["tol"]:
            checked += 1
            ver_l.append(ev_verified(
                "XFORM_OK",
                f"{name}: engine result within {t['tol']}{t['tol_unit']} of "
                f"the frozen reference (max err {err:.3e})",
                check=f"independent recomputation vs frozen control point, "
                      f"engine {engine}"))
        else:
            findings.append(_ff(
                "XFORM_MISMATCH",
                f"{name}: engine disagrees with the frozen reference by "
                f"{err:.3e}{t['tol_unit']} (tolerance {t['tol']}) — "
                f"transformations must not be trusted"))

    ok = not any(f["severity"] == "error" for f in findings)
    if ok and checked == len(ref["transformations"]) and checked:
        findings.append(_ff("REF_DIR_OK",
                            f"all {checked} frozen control points re-proven "
                            f"with {engine}"))
    return {"ok": ok, "findings": findings,
            "evidence": compile_evidence(read_l, ver_l, unv_l),
            "checked": checked,
            "total": len(ref["transformations"])}


def verify_reference_dir(directory: str,
                         manifest_path: Optional[str] = None) -> dict:
    """Recompute sha256+size of every file pinned in a corpus manifest.

    The manifest binds each golden file to its exact bytes. Any missing,
    added or altered file is an error — reference data is not allowed to
    drift silently.
    """
    d = Path(directory)
    mp = Path(manifest_path) if manifest_path else d / "dataset_manifest.json"
    findings: List[dict] = []
    read_l, ver_l, unv_l = [], [], []
    if not mp.exists():
        findings.append(_ff("REF_MANIFEST_INVALID",
                            f"manifest not found: {mp}"))
        return {"ok": False, "findings": findings,
                "evidence": compile_evidence(read_l, ver_l, unv_l),
                "checked": 0}
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        files = manifest["files"]
    except (KeyError, ValueError) as exc:
        findings.append(_ff("REF_MANIFEST_INVALID",
                            f"manifest unreadable: {exc}"))
        return {"ok": False, "findings": findings,
                "evidence": compile_evidence(read_l, ver_l, unv_l),
                "checked": 0}
    read_l.append(ev_read("REF_MANIFEST_READ",
                          f"manifest lists {len(files)} reference files"))
    checked = 0
    for name, entry in sorted(files.items()):
        fpath = d / name
        if not fpath.exists():
            findings.append(_ff("REF_FILE_MISSING",
                                f"reference file missing: {name}"))
            continue
        data = fpath.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.get("sha256"):
            findings.append(_ff(
                "REF_HASH_MISMATCH",
                f"reference file {name} changed on disk (sha256 differs "
                f"from the manifest) — corpus integrity broken"))
            continue
        if len(data) != entry.get("bytes"):
            findings.append(_ff(
                "REF_HASH_MISMATCH",
                f"reference file {name} size drifted"))
            continue
        checked += 1
    if checked == len(files) and files:
        ver_l.append(ev_verified(
            "REF_CORPUS_INTACT",
            f"all {checked} reference files byte-identical to the manifest",
            check="sha256 recomputed over every pinned file"))
        findings.append(_ff("REF_DIR_OK",
                            f"{checked} reference files intact"))
    unv_l.append(ev_unverifiable(
        "REF_CORPUS_SCOPE",
        "reference corpus proves validator behaviour, not geology",
        reason="expected results were defined at construction time by this "
               "project; they certify the code paths, not geology itself"))
    ok = not any(f["severity"] == "error" for f in findings)
    return {"ok": ok, "findings": findings,
            "evidence": compile_evidence(read_l, ver_l, unv_l),
            "checked": checked}
