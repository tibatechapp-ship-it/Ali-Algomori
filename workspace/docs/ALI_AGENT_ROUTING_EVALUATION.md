# Ali Algomori routing evaluation

## Purpose

A curated regression suite checks deterministic intent routing across Arabic, English, Russian, and Chinese. It protects the known lexicon from regressions and verifies that requests without geoscience signals abstain instead of being routed to GIS by default.

## Scope

- 24 total cases in `skill_evaluation.py`: 23 positive cases across all nine planner domains, plus one ambiguous/no-domain case.
- The positive cases are distributed unevenly by domain and language; they are not a balanced six-domain-by-four-language dataset.
- The one negative case is `ambiguous_no_fallback`; the current code does not contain four negative examples.
- Every case must return exactly its expected domain set; the ambiguous case expects no domain.
- The benchmark currently checks deterministic domain tags. It does not assert a separate calibrated confidence score or a full user-facing clarification quality rubric.

## Current evaluation

The implementation and this document were reconciled on 2026-11-23. Counts above reflect the current `_CASES` tuple in `skill_evaluation.py`.

The suite is intentionally authored around supported terminology. It is **not** an independent, statistically representative language benchmark, does not measure scientific correctness, and cannot establish general multilingual understanding. Future evaluation should add reviewed real-world requests, ambiguous and adversarial wording, held-out terminology, and domain-expert adjudication.

No model training or scientific engine execution is involved.
