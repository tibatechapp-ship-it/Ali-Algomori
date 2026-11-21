# Knowledge unit schema v1 (T1.2): one evidence-store record per scientific
# claim. Every unit ties a claim to a stored source with a locatable position
# (page_or_section) so any reader can re-check it. Trust states are INHERITED
# from the seed catalog vocabulary (ADR-0002): confidence is exactly
# {"well_known", "to_verify"} and review_status is exactly
# {"read", "verified", "unverifiable"} - no third values, ever.
# Cross-field rules live in validate_unit() as plain Python so the module
# behaves identically on pydantic 1 and 2 (the BaseModel below is structure
# only: no model_config, no validators, no version-specific APIs).
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from geologia.knowledge.licenses import PURPOSES, purpose_allowed

# Trust inheritance fingerprint (pinned by tests): widening these sets
# silently - e.g. adding "confirmed" - is a schema break and must fail CI.
ALLOWED_CONFIDENCE = frozenset({"well_known", "to_verify"})
ALLOWED_REVIEW_STATUS = frozenset({"read", "verified", "unverifiable"})

# License states exactly as they occur in seed_catalog.json (see T1.3 matrix).
ALLOWED_LICENSES = frozenset({
    "licensed", "public_domain", "unknown", "free_online",
    "company_publication", "open_data", "open_source", "open_access",
})

_ID_TYPES = frozenset({"doi", "orcid", "report_number", "map_sheet", "igsn"})

_UNIT_ID_RE = re.compile(r"^ku-[0-9a-z-]+$")
_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DOI_RE = re.compile(r"^10\.[0-9]{4,}/\S+$")
_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$")

# Short-quote doctrine: a stored quotation inside a unit stays short so the
# unit never becomes a redistribution channel for licensed content.
_MAX_QUOTE_CHARS = 300

_FIELDS = frozenset({
    "unit_id", "claim", "source_id", "page_or_section", "doi_or_url",
    "language", "region", "topic", "confidence", "review_status", "license",
    "extracted_at_utc", "source_version", "contradicts", "superseded_by",
    "valid_until", "quantitative", "permanent_ids", "archive",
    "license_per_purpose", "override_source", "quote",
})


class KnowledgeUnit(BaseModel):
    """Structure-only model of one knowledge unit; rules live in validate_unit."""

    unit_id: str
    claim: str
    source_id: str
    page_or_section: str
    doi_or_url: Optional[str] = None
    language: str
    region: str
    topic: str
    confidence: str
    review_status: str
    license: str
    extracted_at_utc: str
    source_version: Optional[str] = None
    contradicts: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    valid_until: Optional[str] = None
    quantitative: Optional[dict] = None
    permanent_ids: Optional[List[dict]] = None
    archive: Optional[dict] = None
    license_per_purpose: dict
    override_source: Optional[str] = None
    quote: Optional[dict] = None


def _fail(code: str, detail: str) -> None:
    raise ValueError(f"{code}: {detail}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _need_non_empty(unit: dict, key: str, code: str) -> str:
    value = unit.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(code, f"{key} must be a non-empty string")
    return value


def _opt_str(unit: dict, key: str, code: str) -> Optional[str]:
    value = unit.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail(code, f"{key} must be a non-empty string when present")
    return value


def _validate_license_legs(unit: dict) -> dict:
    """license_per_purpose: exact shape, strict booleans, never exceeds matrix."""
    license_status = _need_non_empty(unit, "license", "KU_INVALID_LICENSE")
    if license_status not in ALLOWED_LICENSES:
        _fail("KU_INVALID_LICENSE",
              f"license must be one of {sorted(ALLOWED_LICENSES)}, got {license_status!r}")
    legs = unit.get("license_per_purpose")
    if not isinstance(legs, dict) or set(legs) != set(PURPOSES):
        _fail("KU_INVALID_LICENSE_PER_PURPOSE",
              "license_per_purpose needs exactly the four purpose keys")
    for purpose in PURPOSES:
        if not isinstance(legs[purpose], bool):
            _fail("KU_INVALID_LICENSE_PER_PURPOSE", f"{purpose} must be a boolean")
    override_source = _opt_str(unit, "override_source", "KU_INVALID_OVERRIDE_SOURCE")
    for purpose in PURPOSES:
        allowed, _code = purpose_allowed(license_status, purpose)
        if legs[purpose] and not allowed and not override_source:
            _fail("KU_LICENSE_PURPOSE_EXCEEDS_MATRIX",
                  f"{purpose}=true exceeds the frozen matrix for license "
                  f"{license_status!r}; document override_source or set it false")
    return {"license": license_status, "license_per_purpose": legs}


def _validate_quantitative(unit: dict) -> None:
    quantitative = unit.get("quantitative")
    if quantitative is None:
        return
    if not isinstance(quantitative, dict):
        _fail("KU_INVALID_QUANTITATIVE", "quantitative must be an object")
    if not _is_number(quantitative.get("value")):
        _fail("KU_INVALID_QUANTITATIVE", "quantitative.value must be a number")
    q_unit = quantitative.get("unit")
    if not isinstance(q_unit, str) or not q_unit.strip():
        _fail("KU_INVALID_QUANTITATIVE",
              "a number without a unit is not science: quantitative.unit is required")
    method = quantitative.get("measurement_method")
    if not isinstance(method, str) or not method.strip():
        _fail("KU_INVALID_QUANTITATIVE", "quantitative.measurement_method is required")
    if "uncertainty" in quantitative and not _is_number(quantitative["uncertainty"]):
        _fail("KU_INVALID_QUANTITATIVE", "quantitative.uncertainty must be a number")


def _validate_permanent_ids(unit: dict) -> list:
    permanent_ids = unit.get("permanent_ids")
    if permanent_ids is None:
        return []
    if not isinstance(permanent_ids, list):
        _fail("KU_INVALID_PERMANENT_IDS", "permanent_ids must be a list")
    for item in permanent_ids:
        if not isinstance(item, dict) or not isinstance(item.get("id_type"), str):
            _fail("KU_INVALID_PERMANENT_IDS", "each permanent id needs id_type and id")
        id_type = item["id_type"]
        if id_type not in _ID_TYPES:
            _fail("KU_INVALID_PERMANENT_IDS",
                  f"id_type {id_type!r} not in {sorted(_ID_TYPES)}")
        pid = item.get("id")
        if not isinstance(pid, str) or not pid.strip():
            _fail("KU_INVALID_PERMANENT_IDS", "permanent id value must be a non-empty string")
        if id_type == "doi" and not _DOI_RE.match(pid):
            _fail("KU_INVALID_DOI", f"bad doi format: {pid!r}")
        if id_type == "orcid" and not _ORCID_RE.match(pid):
            _fail("KU_INVALID_ORCID", f"bad orcid format: {pid!r}")
    return permanent_ids


def _validate_archive(unit: dict) -> None:
    archive = unit.get("archive")
    if archive is None:
        return
    if not isinstance(archive, dict):
        _fail("KU_INVALID_ARCHIVE", "archive must be an object")
    snapshot = archive.get("snapshot_url")
    if not isinstance(snapshot, str) or not snapshot.strip():
        _fail("KU_INVALID_ARCHIVE", "archive.snapshot_url must be a non-empty string")
    accessed = archive.get("accessed")
    if not isinstance(accessed, str) or not _ISO_DATE_RE.match(accessed):
        _fail("KU_INVALID_ARCHIVE", "archive.accessed must be an ISO date (YYYY-MM-DD)")


def _validate_quote(unit: dict) -> None:
    quote = unit.get("quote")
    if quote is None:
        return
    if not isinstance(quote, dict):
        _fail("KU_INVALID_QUOTE", "quote must be an object")
    text = quote.get("text")
    if not isinstance(text, str) or not text.strip():
        _fail("KU_INVALID_QUOTE", "quote.text must be a non-empty string")
    if len(text) > _MAX_QUOTE_CHARS:
        _fail("KU_INVALID_QUOTE",
              f"short-quote doctrine: quote.text exceeds {_MAX_QUOTE_CHARS} chars")
    position = quote.get("page_or_section")
    if not isinstance(position, str) or not position.strip():
        _fail("KU_INVALID_QUOTE", "quote.page_or_section must be a non-empty string")


def validate_unit(unit: dict) -> dict:
    """Validate one unit dict against schema v1; return the normalized dict."""
    if not isinstance(unit, dict):
        _fail("KU_INVALID_UNIT", "unit must be a JSON object")
    unknown = sorted(set(unit) - _FIELDS)
    if unknown:
        _fail("KU_INVALID_UNKNOWN_FIELD", f"fields not in schema v1: {unknown}")

    unit_id = unit.get("unit_id")
    if not isinstance(unit_id, str) or not _UNIT_ID_RE.match(unit_id):
        _fail("KU_INVALID_UNIT_ID", f"unit_id must match ^ku-[0-9a-z-]+$, got {unit_id!r}")
    _need_non_empty(unit, "claim", "KU_INVALID_CLAIM")
    _need_non_empty(unit, "source_id", "KU_INVALID_SOURCE_ID")
    _need_non_empty(unit, "page_or_section", "KU_INVALID_PAGE_OR_SECTION")
    doi_or_url = _opt_str(unit, "doi_or_url", "KU_INVALID_DOI_OR_URL")
    language = _need_non_empty(unit, "language", "KU_INVALID_LANGUAGE")
    if len(language.strip()) < 2:
        _fail("KU_INVALID_LANGUAGE", "language needs at least 2 characters")
    _need_non_empty(unit, "region", "KU_INVALID_REGION")
    _need_non_empty(unit, "topic", "KU_INVALID_TOPIC")

    confidence = unit.get("confidence")
    if not isinstance(confidence, str) or confidence not in ALLOWED_CONFIDENCE:
        _fail("KU_INVALID_CONFIDENCE",
              f"confidence must be one of {sorted(ALLOWED_CONFIDENCE)}, got {confidence!r}")
    review_status = unit.get("review_status")
    if not isinstance(review_status, str) or review_status not in ALLOWED_REVIEW_STATUS:
        _fail("KU_INVALID_REVIEW_STATUS",
              f"review_status must be one of {sorted(ALLOWED_REVIEW_STATUS)}, "
              f"got {review_status!r}")

    extracted = unit.get("extracted_at_utc")
    if not isinstance(extracted, str) or not _ISO_UTC_RE.match(extracted):
        _fail("KU_INVALID_EXTRACTED_AT",
              "extracted_at_utc must be an ISO-8601 UTC timestamp ending in Z")
    _opt_str(unit, "source_version", "KU_INVALID_SOURCE_VERSION")

    contradicts = unit.get("contradicts")
    if contradicts is None:
        contradicts = []
    if not isinstance(contradicts, list):
        _fail("KU_INVALID_CONTRADICTS", "contradicts must be a list of unit ids")
    for other in contradicts:
        if not isinstance(other, str) or not _UNIT_ID_RE.match(other):
            _fail("KU_INVALID_CONTRADICTS", f"unit id pattern violation: {other!r}")
    superseded_by = _opt_str(unit, "superseded_by", "KU_INVALID_SUPERSEDED_BY")
    if superseded_by is not None and not _UNIT_ID_RE.match(superseded_by):
        _fail("KU_INVALID_SUPERSEDED_BY", f"unit id pattern violation: {superseded_by!r}")
    valid_until = _opt_str(unit, "valid_until", "KU_INVALID_VALID_UNTIL")
    if valid_until is not None and not _ISO_DATE_RE.match(valid_until):
        _fail("KU_INVALID_VALID_UNTIL", "valid_until must be an ISO date (YYYY-MM-DD)")

    _validate_quantitative(unit)
    permanent_ids = _validate_permanent_ids(unit)
    _validate_archive(unit)
    _validate_quote(unit)
    _validate_license_legs(unit)

    # A "verified" claim must be re-checkable: a resolvable position alone is
    # not enough - it needs a doi_or_url or at least one permanent id.
    if review_status == "verified" and not doi_or_url and not permanent_ids:
        _fail("KU_VERIFIED_NO_RECHECK_PATH",
              "verified claims need doi_or_url or permanent_ids to stay re-checkable")

    normalized = {key: unit[key] for key in _FIELDS if key in unit}
    normalized["contradicts"] = contradicts
    KnowledgeUnit(**normalized)  # structural coherence on pydantic 1 and 2
    return normalized


def load_knowledge_units(path) -> List[dict]:
    """Load a {"units": [...]} JSON file and validate every unit."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("units"), list):
        _fail("KU_INVALID_FILE", "expected a JSON object with a 'units' list")
    return [validate_unit(item) for item in raw["units"]]
