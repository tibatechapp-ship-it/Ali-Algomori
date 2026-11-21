"""Golden evaluation package (T3): frozen eval set + deterministic audit.

- golden_eval_v1.json (data/evaluation/) is fingerprint-locked; never edit it
  silently (verify_fingerprint fails loudly on any modification).
- audit.py grades the real KnowledgeBase against the frozen set and computes
  the section-5.7 metric table with honest "not_measurable_yet" entries.

Attributes are imported lazily (PEP 562) so `python -m geologia.evaluation.audit`
does not import the module twice.
"""
from typing import Any

_LAZY = (
    "AUDIT_VERSION", "GOLDEN_EVAL_PATH", "load_golden_eval",
    "run_audit", "verify_fingerprint",
)


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from geologia.evaluation import audit
        return getattr(audit, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    return sorted(list(globals()) + list(_LAZY))
