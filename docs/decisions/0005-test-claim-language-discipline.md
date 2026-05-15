# ADR 0005 — Test claim language discipline: "satisfied" vs "case capture" vs "infrastructure populated"

- **Date:** 2026-05-14
- **Status:** proposed
- **Decided by:** Emmanuel (Nuke AI) — pending review; surfaced by composite-audit SESS-2026-05-14
- **Affects:** `PROJECT_SCOPE.md §5`, `skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md`, future substrate-instrumented outputs

## Context

The composite audit of session 2026-05-14 (`docs/findings/2026-05-14-composite-audit-meta-conclusion.md` finding F-self-audit-E6/E7) identified an anti-pattern that emerged in v2.3 despite the v2.2 stress-test recalibration: the agent claimed *"Tests 1-4 satisfied"* in the v1.4 consolidated report when only Tests 1+2 had operational evidence, Test 3 only had **one session of case capture** (not the longitudinal use Test 3 spec requires), and Test 4 only had **infrastructure populated** (4 claim records with `observed_outcome: null` — no ECE/Brier computed yet).

The session's confidence trajectory 0.40 → 0.68 was reported on the direct_answer which aggregated multiple sub-claims of asymmetric evidence-strength. Reader downstream may interpret "Test N satisfied" as completed/measured when it is only case-captured.

This anti-pattern is **AP-N2** in the composite audit's enumeration of new anti-patterns emerged 2026-05-14.

## Decision

Adopt a **four-level vocabulary** for reporting substrate test status, enforced in any output that references Tests 1-5:

| Level | Meaning | Required evidence |
|---|---|---|
| **not exercised** | Test scope was not engaged in this session/period | n/a |
| **case capture** | Test scope engaged; one or more case records produced; NO aggregated measurement yet | At least 1 case record (claim record, evaluation pass, audit instance) tagged with `test_mapping: ["test_N"]` |
| **infrastructure populated** | Mechanisms required to measure the test are in place but the measurement has not been computed against observed outcomes | Schema-conforming records exist with `observed_outcome: null` field, AND the aggregation pipeline (e.g., `compute_ece.py`) is runnable |
| **satisfied** | Test threshold met per PROJECT_SCOPE §5 defensive criterion | Aggregated measurement computed against observed outcomes ≥ threshold |

**Mandatory rules:**

1. The word *"satisfied"* (or its synonyms: passed, met, achieved, completed) is **reserved for the fourth level**. Pre-measurement work uses one of the other three.
2. Reports that summarize multiple tests must report status per test (not aggregate). A report claiming "Tests 1-4 ✓ satisfied" without per-test evidence is an audit failure.
3. The structured output contract (§5) may include a `tests_status` field with the four-level vocabulary when relevant; structured ≥ prose.

## Alternatives considered

1. **Three-level (not exercised / partial / satisfied)** — Rejected: "partial" conflates case-capture and infrastructure-populated, which are operationally distinct. Test 3 with one case capture is not on the path to satisfied without longitudinal accumulation; Test 4 with infrastructure populated IS on the path once outcomes arrive.

2. **Binary (exercised / satisfied)** — Rejected: erases the audit signal between "we have one data point" and "we have a measured aggregate." This is the conflation that produced the anti-pattern in the first place.

3. **Per-test custom vocabulary** — Rejected: would create reporting drift between tests. One vocabulary for all five is enforceable.

4. **Keep "satisfied" as the only category, no shading** — Rejected by definition; this is the status quo and what caused the failure.

## Consequences

**Positive:**

- Future reports will distinguish case-captured Tests 3+5 from satisfied Tests (which require year-end aggregation per PROJECT_SCOPE §5).
- Investor-facing summaries will reflect honest substrate status; reduces overclaim risk that v2.2 audit discipline targets.
- Forces structural completion of Tests 3+4 (infrastructure → satisfied requires the aggregation step, not just record collection).
- Aligns with PROJECT_SCOPE §5 v1.2 three-tier reporting (defensive / ambitious / per-category): adds the orthogonal dimension of *status* (not exercised / case capture / infra / satisfied).

**Negative / costs:**

- Some past reports (including this session's v1.4) are retroactively misaligned. Choice: leave historical as-is (preserved per ADR-0002) but apply the new vocabulary from now onward.
- Adds slight verbosity to test reporting. Acceptable.

**Implementation:**

- `substrate-evidence-guide.md` should be bumped to v1.4 adding §"Test status reporting vocabulary."
- `PROJECT_SCOPE.md §5` may add a cross-reference note (not a change in thresholds).
- This session's v1.4 consolidated report is annotated with this ADR retroactively — does not get rewritten (ADR-0002).

## Evidence

- `docs/findings/2026-05-14-composite-audit-meta-conclusion.md` §4 (anti-pattern AP-N2)
- `docs/findings/2026-05-14-pronephros-proteomics-session-retrospective.md` errors E6 + E7
- `reports/proteomic-evidence-pronephros-windows-v1.4-CONSOLIDATED.md` §1 TL;DR table (where "Tests 1-4 ✓" first overclaimed)
- `PROJECT_SCOPE.md §5` (the test specs themselves)
