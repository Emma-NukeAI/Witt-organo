# ADR-0030 — compute_ece Test-4 language: a cross-sectional snapshot is "aggregate-captured", never "satisfied"

- **Status:** Accepted — from a composite-auditor finding (2026-07-04, panel auditor 2 "overclaim" lens, APPROVE_MINOR F1).
- **Relates:** ADR-0005 (test-claim language discipline — the vocabulary this tightens), ADR-0007 (HTML-at-conclusion), PROJECT_SCOPE §5 Test 4 (the full test definition), the full-functionality audit `reports/2026-07-05_full-functionality-audit_composite.html`.
- **Affects:** `substrate_calibration/tools/compute_ece.py` (read-and-report tool logic — **NOT** a DATA INAMOVIBLE mutation).

## Context

The full-functionality audit ran `compute_ece` over the 16 claim records and the tool reported `tests_status.test_4 = "satisfied"` at `n_scored = 10`, `ece_raw = 0.114` (< 0.20 defensive threshold). The composite-auditor's overclaim lens flagged this as the round's over-claim:

- **ADR-0005** reserves "satisfied" for a *measured + aggregated* state at/beyond threshold.
- **PROJECT_SCOPE §5 Test 4** defines the test as **longitudinal** — "are the confidence estimates well-calibrated, **and do they improve with use?**", measured at months 0 / 4 / 8 — and carries a **≥85% high-confidence sub-threshold**.

A single **cross-sectional** run with `ece_raw < 0.20` establishes *neither* the longitudinal "improve with use" arc *nor* (as originally coded) the ≥85% sub-threshold. Emitting "satisfied" from one snapshot is exactly the AP-N2 anti-pattern ADR-0005 exists to prevent: a reader seeing `test_4:"satisfied"` in the artifact concludes Test 4 is met.

The prior mapping was `n_scored >= 10 → "satisfied"` (a deliberate but too-strong prior choice; its own comment cited ADR-0005 while under-reading it).

## Decision

`compute_ece` **never emits "satisfied"** — it is a single-snapshot tool and "satisfied" is a longitudinal cross-run judgment. The status vocabulary becomes:

| n_scored | status |
|---|---|
| 0 | `infrastructure populated` |
| 1–9 | `case capture` |
| ≥10 | `aggregate-captured` |

Additionally the report now:
- computes and reports the **≥85% high-confidence sub-threshold** (`aggregate.high_conf_frac_correct`, `high_conf_subthreshold_met`; high-conf = stated_confidence ≥ 0.80);
- carries a `satisfied_requires` block naming the **three** conditions ("satisfied" needs defensive ECE **AND** the ≥85% sub-threshold **AND** the longitudinal arc) and marks the longitudinal one `not-establishable-from-single-run`;
- updates `reporting_note` accordingly.

## Consequences

- Any prior artifact recording `test_4 = "satisfied"` from a single snapshot (e.g. `substrate_calibration/reports/_smoke_ece.json` before this change) is **superseded** — the label was over-strong; the correct state at the current corpus (n=10, 10 skills × n=1 singleton mosaic) is `aggregate-captured`.
- "Test 4 satisfied" can only be asserted by a **longitudinal** judgment across month-0/4/8 runs plus the sub-threshold — a decision for a human/`retrospector`, not for this tool.
- Read-and-report only; **zero DATA INAMOVIBLE mutation**. No API spend.
- Verified: `compute_ece` now emits `test_4="aggregate-captured"` at n=10; `smoke_contract.py` reports it as INFO (never as PASS/objective-met).
