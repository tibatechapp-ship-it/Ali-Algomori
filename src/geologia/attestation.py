"""Reproducible evidence-chain attestation — the honesty fingerprint as a product.

Closes the P1 gap "the honesty fingerprint is not a product yet" from
docs/benchmark/STRATEGIC_LEADERSHIP_PLAN.md: one command that lets any party
verify the integrity of the evidence chain locally, plus one committed
reference that makes tampering detectable offline (ADR-0010).

Design invariants (the acceptance gate is cross-system identity):
- The compared payload contains ONLY content-derived, environment-independent
  values: sha256 of every declared evidence asset plus the two internal
  fingerprints of the frozen golden evaluation set. No wall-clock, no file
  paths, no runtime results inside the hash — two independent systems on the
  same repo state MUST produce the identical chain fingerprint.
- data/attestation/attestation_reference_v1.json is the committed reference
  (the frozen-golden-eval pattern: fingerprint of everything except itself).
  Tampering with any asset, adding an undeclared asset, deleting an asset,
  or silently editing the reference breaks verification in tests and in
  `geologia certify`.
- Runtime checks (first-party engine re-certification) are advisory and
  excluded from the hash: optional dependencies differ across systems and an
  honest skip must never change the deterministic fingerprint.
- Truth class on every output: this attests evidence-chain and engineering-gate
  integrity, never geological truth (fixed rule 2).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from geologia import __version__
from geologia.evaluation.audit import sha256_of, verify_fingerprint

ATTESTATION_VERSION = "1.0.0"
SCHEMA = "geologia.attestation.v1"
REFERENCE_SCHEMA = "geologia.attestation.reference.v1"
REPORT_SCHEMA = "geologia.attestation.report.v1"

DATA_DIR = Path(__file__).parent / "data"
REFERENCE_PATH = DATA_DIR / "attestation" / "attestation_reference_v1.json"
GOLDEN_EVAL_REL = "evaluation/golden_eval_v1.json"

# Declared evidence assets of the core layer, relative to the package data dir.
# The agents directory and the knowledge digests are discovered deterministically
# (sorted glob) so a new card or digest is caught as "undeclared" until the
# reference is regenerated through the documented procedure.
EVIDENCE_ASSETS: List[str] = [
    "evaluation/golden_eval_v1.json",
    "first_party_engines.json",
    "knowledge/engines_kb.json",
    "knowledge/institutions.json",
    "knowledge/license_purpose_matrix.json",
    "knowledge/seed_catalog.json",
    "knowledge/terms_multilingual.json",
    "reference/geoid_golden_nodes.json",
    "reference/geoid_grid_registry.json",
    "reference/geoid_model_reference.json",
    "reference/porosity_density_v1_reference.json",
    "reference/reference_sources.json",
    "reference/transformations.json",
]
GLOBBED_ASSETS: List[str] = ["agents/*.json", "knowledge/docs/*.md"]

TRUTH_NOTE_AR = (
    "تصنيف الحقيقة: هذه الشهادة توثّق سلامة سلسلة الأدلة والبوابات الهندسية "
    "لا الصحة الجيولوجية — شهادة CI تظل شهادة هندسية للشفرة والبوابات أبداً "
    "(الثابت 2)."
)
TRUTH_NOTE_EN = (
    "Truth class: this attestation documents evidence-chain and engineering-gate "
    "integrity, never geological truth — CI success remains an engineering "
    "certificate of the code and gates only (fixed rule 2)."
)
LIMIT_NOTE_AR = (
    "الحد الصادق: الشهادة كاشفةٌ للعبث لا مانعةٌ منه — تعديلُ أصولٍ مع تعديل "
    "المرجع معاً يُكشف عبر ثبات البصمة في تاريخ CI وأدلة الإصدارات المثبّتة."
)
LIMIT_NOTE_EN = (
    "Honest limit: the attestation is tamper-EVIDENT, not tamper-PROOF — "
    "coordinated asset+reference edits are caught by fingerprint stability "
    "across CI history and pinned release evidence."
)

PASS_MESSAGE_AR = (
    "سلسلة الأدلة سليمة: كل الأصول المعلنة مطابقة للمرجع المثبت والبصمة "
    "الحاكمة متطابقة."
)
PASS_MESSAGE_EN = (
    "Evidence chain intact: every declared asset matches the committed "
    "reference and the governing fingerprint matches."
)
BROKEN_MESSAGE_AR = (
    "كسرٌ في سلسلة الأدلة — المتابعة الصامتة ممنوعة؛ راجع حقل mismatches "
    "وأعد التوليد بالإجراء الموثق فقط لا بالتعديل الصامت."
)
BROKEN_MESSAGE_EN = (
    "Evidence chain broken — silent continuation is forbidden; see the "
    "mismatches field and regenerate via the documented procedure only."
)


class AttestationBroken(RuntimeError):
    """The evidence chain failed an internal consistency check."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_relpaths(base_dir: Path) -> List[str]:
    names = sorted(EVIDENCE_ASSETS)
    for pattern in GLOBBED_ASSETS:
        names += sorted(p.relative_to(base_dir).as_posix()
                        for p in base_dir.glob(pattern))
    return names


def collect_asset_hashes(base_dir: Optional[Path] = None) -> Dict[str, str]:
    """sha256 of every declared evidence asset, keyed by data-relative path."""
    root = Path(base_dir) if base_dir is not None else DATA_DIR
    return {rel: _sha256_file(root / rel) for rel in _asset_relpaths(root)}


def _golden_eval_block(base_dir: Path) -> dict:
    doc = json.loads((base_dir / GOLDEN_EVAL_REL).read_text(encoding="utf-8"))
    verify_fingerprint(doc)  # loud ValueError on any frozen-set tampering
    return {
        "fingerprint_sha256": doc["fingerprint_sha256"],
        "blocked_split_sha256": doc["blocked_split_sha256"],
    }


def build_chain_payload(base_dir: Optional[Path] = None) -> dict:
    """The deterministic, hash-compared payload of the attestation."""
    root = Path(base_dir) if base_dir is not None else DATA_DIR
    try:
        golden = _golden_eval_block(root)
    except ValueError as exc:
        raise AttestationBroken(
            f"golden-eval internal fingerprints broken: {exc}") from exc
    return {
        "schema": SCHEMA,
        "attestation_version": ATTESTATION_VERSION,
        "assets": collect_asset_hashes(root),
        "golden_eval": golden,
    }


def chain_fingerprint(base_dir: Optional[Path] = None) -> str:
    """Content-derived fingerprint — identical on two independent systems."""
    return sha256_of(build_chain_payload(base_dir))


def build_reference(base_dir: Optional[Path] = None,
                    frozen_at: str = "") -> dict:
    payload = build_chain_payload(base_dir)
    return {
        "schema": REFERENCE_SCHEMA,
        "attestation_version": ATTESTATION_VERSION,
        "geologia_version": __version__,
        "frozen_at": frozen_at,
        "assets": payload["assets"],
        "golden_eval": payload["golden_eval"],
        "chain_fingerprint_sha256": sha256_of(payload),
    }


def regenerate_reference(base_dir: Optional[Path] = None,
                         out_path: Optional[Path] = None,
                         frozen_at: str = "2026-11-23") -> dict:
    """Regenerate the committed reference (documented procedure, never silent).

    After regenerating: re-run tests/test_attestation.py, record the new
    chain fingerprint in the release evidence (CHANGELOG entry), and commit
    the asset change and the reference change in the same commit.
    """
    ref = build_reference(base_dir, frozen_at=frozen_at)
    path = Path(out_path) if out_path is not None else REFERENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ref, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return ref


def _runtime_checks() -> dict:
    """Advisory checks re-run at execution; NEVER part of the hashed payload."""
    out: Dict[str, object] = {}
    try:
        from geologia.data_layer.certification import certify_engine
        rep = certify_engine("porosity_density_v1")
        out["engine_porosity_density_v1"] = {
            "certified": bool(rep["certified"]),
            "excluded_from_fingerprint": True,
        }
    except Exception as exc:  # honest skip: optional deps or store problems
        out["engine_porosity_density_v1"] = {
            "honest_skip": True,
            "reason": type(exc).__name__,
            "excluded_from_fingerprint": True,
        }
    return out


def verify_attestation(base_dir: Optional[Path] = None,
                       reference_path: Optional[Path] = None,
                       include_runtime_checks: bool = True) -> dict:
    """Verify the tree against the committed reference; classify every diff."""
    root = Path(base_dir) if base_dir is not None else DATA_DIR
    ref_path = Path(reference_path) if reference_path is not None \
        else REFERENCE_PATH
    reference = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_assets: Dict[str, str] = reference.get("assets", {})
    mismatches: List[dict] = []
    computed: Dict[str, str] = {}
    for rel in sorted(set(ref_assets) | set(_asset_relpaths(root))):
        path = root / rel
        if not path.exists():
            mismatches.append({"asset": rel, "kind": "missing"})
            continue
        digest = _sha256_file(path)
        computed[rel] = digest
        expected = ref_assets.get(rel)
        if expected is None:
            mismatches.append({"asset": rel, "kind": "undeclared"})
        elif digest != expected:
            mismatches.append({"asset": rel, "kind": "tampered",
                               "expected": expected[:16] + "…",
                               "observed": digest[:16] + "…"})
    golden: Optional[dict] = None
    golden_ok = True
    try:
        golden = _golden_eval_block(root)
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        golden_ok = False
        mismatches.append({"asset": GOLDEN_EVAL_REL,
                           "kind": "internal_fingerprints"})
    computed_chain: Optional[str] = None
    kinds = {m["kind"] for m in mismatches}
    if golden_ok and not (kinds & {"missing", "tampered", "undeclared"}):
        payload = {
            "schema": SCHEMA,
            "attestation_version": ATTESTATION_VERSION,
            "assets": computed,
            "golden_eval": golden,
        }
        computed_chain = sha256_of(payload)
    chain_matches = (computed_chain is not None
                     and computed_chain == reference.get("chain_fingerprint_sha256"))
    status = "pass" if (not mismatches and chain_matches) else "broken"
    report = {
        "schema": REPORT_SCHEMA,
        "attestation_version": ATTESTATION_VERSION,
        "status": status,
        "compared_assets": len(ref_assets),
        "computed_chain_fingerprint": computed_chain,
        "reference_chain_fingerprint": reference.get("chain_fingerprint_sha256"),
        "chain_fingerprint_matches": chain_matches,
        "mismatches": mismatches,
        "reference_geologia_version": reference.get("geologia_version"),
        "reference_frozen_at": reference.get("frozen_at"),
        "truth_class": {
            "classification": "documented",
            "note_ar": TRUTH_NOTE_AR,
            "note_en": TRUTH_NOTE_EN,
        },
        "limits_ar": LIMIT_NOTE_AR,
        "limits_en": LIMIT_NOTE_EN,
        "message_ar": PASS_MESSAGE_AR if status == "pass" else BROKEN_MESSAGE_AR,
        "message_en": PASS_MESSAGE_EN if status == "pass" else BROKEN_MESSAGE_EN,
    }
    if include_runtime_checks:
        report["runtime_checks"] = _runtime_checks()
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m geologia.attestation",
        description="verify the evidence chain, or regenerate the reference")
    parser.add_argument("--regenerate", action="store_true",
                        help="regenerate the committed reference (documented "
                             "procedure — never a silent edit)")
    parser.add_argument("--frozen-at", default="2026-11-23",
                        help="informational freeze date recorded in the reference")
    args = parser.parse_args(argv)
    if args.regenerate:
        ref = regenerate_reference(frozen_at=args.frozen_at)
        print(json.dumps(ref, ensure_ascii=False, indent=2, sort_keys=True))
        print(
            "[i] المرجع جُدِّد — أعد تشغيل tests/test_attestation.py وثّق البصمة "
            "الجديدة في إدخال CHANGELOG بنفس الcommit.",
            file=sys.stderr)
        return 0
    report = verify_attestation(include_runtime_checks=False)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
