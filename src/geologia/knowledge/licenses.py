# License x purpose matrix (T1.3): the license leg of the ADR-0008 model gate.
# The matrix answers ONLY whether a license state permits a purpose. Training
# is false for every state in v1: the ADR-0008 gate additionally requires the
# frozen-baseline + measured-improvement conditions, so a permissive license
# never opens training by itself. Refusal codes are UPPER_SNAKE.
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

# Data files live in src/geologia/data/knowledge/ (same pattern as catalog.py).
_DATA_DIR = Path(__file__).parent.parent / "data" / "knowledge"

PURPOSES: Tuple[str, ...] = ("indexing", "retrieval", "training", "redistribution")

CODE_ALLOWED = "ALLOWED"
CODE_NOT_PERMITTED = "LICENSE_PURPOSE_NOT_PERMITTED"
CODE_UNKNOWN_RESTRICTED = "LICENSE_UNKNOWN_RESTRICTED"
CODE_BAD_STATE = "LICENSE_STATUS_UNKNOWN_STATE"

# The one license state that is itself "unknown" and therefore restricted.
_UNKNOWN_STATE = "unknown"


def load_license_matrix() -> dict:
    """Load and shape-check the frozen license x purpose matrix from package data."""
    raw = json.loads(
        (_DATA_DIR / "license_purpose_matrix.json").read_text(encoding="utf-8")
    )
    if list(raw.get("purposes", [])) != list(PURPOSES):
        raise ValueError("license matrix purposes drifted from the four fixed purposes")
    matrix = raw.get("matrix", {})
    for state, cells in matrix.items():
        if set(cells) != set(PURPOSES):
            raise ValueError(f"license matrix state {state!r} does not cover all purposes")
        for purpose, cell in cells.items():
            if not isinstance(cell.get("allowed"), bool) or not str(cell.get("reason", "")).strip():
                raise ValueError(f"license matrix cell {state}/{purpose} malformed")
    return raw


def purpose_allowed(license_status: str, purpose: str) -> Tuple[bool, str]:
    """Return (allowed, code) for one license state x purpose question."""
    if purpose not in PURPOSES:
        raise ValueError(f"LM_INVALID_PURPOSE: unknown purpose {purpose!r}")
    matrix = load_license_matrix()["matrix"]
    if license_status not in matrix:
        return (False, CODE_BAD_STATE)
    cell = matrix[license_status][purpose]
    if cell["allowed"]:
        return (True, CODE_ALLOWED)
    if license_status == _UNKNOWN_STATE:
        return (False, CODE_UNKNOWN_RESTRICTED)
    return (False, CODE_NOT_PERMITTED)


def assert_purpose_allowed(license_status: str, purpose: str) -> None:
    """Raise PermissionError carrying the refusal code when not allowed."""
    allowed, code = purpose_allowed(license_status, purpose)
    if not allowed:
        raise PermissionError(
            f"{code}: {license_status!r} x {purpose!r} is not permitted by the frozen matrix"
        )


def matrix_states() -> List[str]:
    """License states currently covered by the matrix."""
    return list(load_license_matrix()["matrix"])
