# Agent Skill Assessment and Development Roadmap

**Status:** assessment and roadmap; no skill certification is implied  
**Baseline reviewed:** main commit `46fd8283628b3dc7e573cfac7d9edc83b77f2102`  
**Scope:** the nine GEOLOGIA specialist profiles and the first executable hydrology skill in `workspace/`

## Executive assessment

GEOLOGIA has moved beyond role labels. The workspace now contains:

- auditable competency contracts for nine domains;
- shared cross-domain quality requirements;
- multilingual routing regression cases;
- four-stage domain workflow templates;
- one bounded, local, descriptive groundwater time-series skill.

This is a sound foundation for a lightweight, deterministic-first scientific assistant. It is **not yet evidence of broad scientific mastery**. The current routing benchmark is a curated regression suite; passing it proves that known requests still route as expected, not that an agent can solve representative field problems. The hydrology skill is descriptive QC/statistics only and must not be represented as groundwater modeling, forecasting, yield estimation, or drilling advice.

## Current capability inventory

| Capability | Evidence in workspace | Current interpretation |
|---|---|---|
| Specialist definition | `skills.py`, nine domain profiles | Requirements and limits are explicit |
| Readiness assessment | `assess_skill_readiness` | Input availability only; not mastery |
| Multilingual routing | `skill_evaluation.py`, 23 curated cases | Regression coverage, not representative evaluation |
| Domain workflows | `skill_workflows.py`, four stages per domain | Plans and acceptance criteria, not execution |
| Executable scientific utility | `hydrology_skill.py` | Bounded CSV QC and descriptive statistics |
| Provenance / evidence | Existing evidence and knowledge systems | Must remain the source of truth for claims |
| Scientific certification | No broad skill benchmark or independent review report | Not established |

## Assessment findings

### Strengths to preserve

1. Deterministic routing and explicit no-fallback behavior for ambiguous requests.
2. Domain profiles identify required inputs, outputs, checks, and safety limits.
3. The plan/execution distinction is explicit in skill status fields.
4. The first executable skill is local, bounded, hash-aware, and rejects symlink inputs.
5. Scientific data ownership, evidence records, engine registry, and job lifecycle remain in the primary workspace rather than duplicated.

### Gaps to close

1. **Routing coverage:** 23 cases are useful smoke tests but too small and curated to estimate real-world routing quality.
2. **No task-level skill benchmark:** the current benchmark tests classification, not whether a specialist's artifact is correct, complete, reproducible, or safe.
3. **Limited executable breadth:** only one specialist capability is implemented as a bounded executable skill.
4. **Input readiness semantics:** `ready_for_validation` means required input names are present; it must not be interpreted as data quality, scientific readiness, or authorization to execute.
5. **Uncertainty and abstention:** limits are documented, but refusal and uncertainty behavior need adversarial and incomplete-input tests.
6. **No measured competency score:** profiles describe expected skills; they do not measure proficiency or certify an agent.
7. **Human review:** domain-specific acceptance rubrics and independent reviewer sign-off are not yet consistently attached to executable skills.

## Skill maturity model

Every skill must have one explicit maturity state:

- **S0 — Defined:** competency contract exists.
- **S1 — Planned:** workflow and acceptance criteria exist.
- **S2 — Implemented:** deterministic or bounded code exists and has unit tests.
- **S3 — Benchmarked:** versioned representative fixtures and scoring report exist.
- **S4 — Independently reviewed:** domain reviewer approves the method, limitations, and evidence.
- **S5 — Operationally eligible:** authorization, isolation, resource bounds, recovery, and monitoring are verified for the intended deployment.

A skill may be S2 for one narrow operation and remain S0/S1 for its broader domain. Do not assign a single maturity level to an entire specialist when only one capability has been validated.

## Evaluation protocol

Each executable skill must be evaluated against a versioned corpus with:

- valid, invalid, incomplete, noisy, edge-case, and adversarial inputs;
- expected outputs or reference ranges with provenance;
- deterministic seeds and pinned tool/library versions where applicable;
- tests for units, CRS/datum, time conventions, nulls, duplicates, limits, and input integrity;
- negative cases that require a safe refusal or a clear data-gap report;
- separate results for Arabic and English requests and relevant multilingual variants.

### Scoring dimensions

Report each dimension independently; do not collapse them into an opaque “AI intelligence” score.

| Dimension | What is measured |
|---|---|
| Routing | Correct domain/tool selection; false-positive and false-negative rates |
| Input validation | Invalid or missing inputs rejected or clearly flagged |
| Scientific correctness | Agreement with trusted reference results or expert-reviewed expected outputs |
| Evidence/provenance | Claims trace to input hashes, sources, parameters, and versions |
| Reproducibility | Same pinned input/configuration produces equivalent outputs |
| Uncertainty | Assumptions, limits, uncertainty sources, and missing evidence disclosed |
| Abstention | Unsupported requests refused without fabricated results |
| Safety | No unauthorized writes, execution, path escape, or unsafe recommendation |
| Usability | Report is understandable, actionable, and bilingual where required |

A passing threshold must be defined per skill before benchmark execution. Safety, provenance, and required-input checks are hard gates; a high average score cannot compensate for a failure in these gates.

## Development roadmap

### Phase A — Evaluation infrastructure

1. Define a versioned skill evaluation report schema: skill ID/version, benchmark ID/version, environment, input hashes, expected/actual result, per-dimension scores, failures, reviewer, and limitations.
2. Expand routing cases to a balanced, reviewed corpus including multi-domain requests, ambiguous requests, misspellings, dialect variation, and unsupported requests.
3. Keep routing tests separate from scientific skill tests.
4. Add benchmark commands/API that run offline and do not access external services by default.
5. Publish coverage and failure categories, not only a pass/fail summary.

**Exit criteria:** reproducible benchmark run; fixed corpus version; all failures inspectable; no claim of scientific certification from routing results.

### Phase B — Harden the first executable skill

1. Review CSV semantics: units, measurement reference, vertical datum, timezone, duplicate policy, and sampling assumptions.
2. Add edge-case tests for daylight-saving/time offsets, mixed offsets, extreme but finite values, empty files, row/byte limits, malformed quoting, and interrupted reads.
3. Ensure trend output is labeled descriptive and is not presented as a forecast or causal interpretation.
4. Add structured provenance for input hash, skill version, parameter values, and environment.
5. Define expert-reviewed reference fixtures and a safe refusal rubric.

**Exit criteria:** complete test suite; benchmark results against reference fixtures; documented known limitations; independent hydrology review before any broader scientific claim.

### Phase C — Build a small set of high-value specialist skills

Prioritize bounded utilities with deterministic outputs and available reference data, rather than broad “agent intelligence” features:

1. **GIS layer inventory and CRS/unit audit** — inspect supported vector/raster metadata, geometry validity, extent, units, and provenance; no reprojection or mutation by default.
2. **Well-log/LAS header and curve QC** — parse supported LAS versions, list curves/units/null values, check depth ordering and gaps; no petrophysical interpretation without required logs and calibration.
3. **Geochemistry sample/QA-QC validation** — schema, sample identity, units, detection limits, blanks/standards/duplicates; no grade/resource estimates.
4. **Seismic catalogue metadata QC** — time system, event/station metadata, sampling and provenance; no hazard forecast.
5. **Remote-sensing metadata/coverage audit** — sensor, acquisition date, CRS, resolution, coverage, and GCP inventory; no validated classification or DEM claim.

Each skill should be a separately versioned module with its own fixtures, tests, benchmark report, and maturity state.

### Phase D — Specialist collaboration

1. Introduce a task contract with objective, project scope, authorized inputs, candidate capability IDs, expected artifacts, acceptance checks, and stop conditions.
2. Let specialists contribute structured findings; do not let them independently mutate shared state.
3. Add a reviewer role that checks evidence, units, assumptions, and conflicts.
4. Resolve disagreements by returning to source data and explicit criteria, not by majority vote.
5. Require a human approval boundary for consequential interpretations, data changes, or future engine execution.

**Exit criteria:** integration tests prove that unregistered capabilities, missing evidence, and conflicting results block completion.

### Phase E — Scientific and operational certification

For any skill that invokes a scientific engine:

- review license and data terms;
- pin dependencies and runtime;
- use known-answer fixtures and independent reference comparisons;
- capture parameters, software versions, input/output hashes, and uncertainty;
- test resource limits, isolation, cancellation, crash recovery, and idempotent artifact publication;
- obtain independent domain review;
- certify only the exact method, version, and supported input range.

Public or multi-user execution remains blocked until authentication, project authorization, tenant isolation, quotas, storage policy, monitoring, and security review are complete.

## Suggested 30 / 60 / 90-day sequence

| Window | Deliverable | Completion evidence |
|---|---|---|
| Days 1–30 | Evaluation report schema, routing corpus expansion, hydrology skill hardening | Versioned benchmark, reproducible tests, reviewed edge cases |
| Days 31–60 | GIS inventory/CRS audit and LAS header/QC skills | Separate modules, reference fixtures, test and benchmark reports |
| Days 61–90 | Geochemistry QA/QC skill, reviewer workflow, first skill maturity records | Independent review, hard-gate results, documented scope |

Dates are planning targets; work is complete only when evidence is merged and verified.

## Quality gates for every new skill PR

- [ ] Scope is narrow and scientifically honest.
- [ ] Required inputs and unsupported cases are explicit.
- [ ] No hidden network calls or execution of untrusted repository code.
- [ ] Input size, row count, time, and memory limits are bounded where applicable.
- [ ] Unit, integration, negative, and regression tests are included.
- [ ] Known-answer or expert-reviewed fixtures are included.
- [ ] Output includes provenance, assumptions, and limitations.
- [ ] Benchmark results are recorded; routing benchmark is not substituted for skill validation.
- [ ] CI passes on the exact PR head.
- [ ] No capability is marked certified without independent review.

## Success measures

Track these in the evaluation report over time:

- routing precision/recall by language and domain;
- skill benchmark pass rate by fixture category;
- critical safety/provenance gate failures (target: zero);
- invalid-input detection and safe-abstention rate;
- reproducibility rate on pinned environments;
- number of skills at S2/S3/S4/S5, reported individually;
- regression rate across releases.

## Non-goals

- Do not add one model per specialist.
- Do not claim neural training or self-improving mastery from profile files.
- Do not infer scientific readiness from filename, role, or routing confidence.
- Do not enable public execution as a shortcut to agent capability.
- Do not make forecasts, resource estimates, or drilling recommendations without validated methods and adequate evidence.

## Decision

The next investment should be **evaluation quality and narrow executable skills**, not increasing the number of agents. GEOLOGIA's competitive advantage should be reproducible geoscience workflows with traceable evidence, safe abstention, and lightweight local execution.
