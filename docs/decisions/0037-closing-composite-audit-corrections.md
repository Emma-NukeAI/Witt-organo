# 0037 — Closing composite-audit of the 2026-07-11 session: all claims REVISE, one real bug, corrections applied

- **Date:** 2026-07-11
- **Status:** accepted
- **Decided by:** composite-auditor (Mode 1, multi-family) — the §7 gate; corrections applied by the producing agent
- **Affects:** the session's claim record (A1 baseline, DI+TU L1, Level-2, ADR-0035/0036); `run_held_out.py` (parser bug); the judge-panel method

## Context

Per CLAUDE.md §7, a substrate-evidence session closes with `composite-auditor`, and the producing agent's own
review is NOT an acceptable substitute. The session's 7 substantive claims were put to a panel of 3 adversarial
auditors from distinct families (Opus 4.8 / Sonnet 5 / Haiku 4.5), each prompted to REFUTE.

## Decision

Record the audit outcome and apply its findings. **Verdict: REVISE on all 7 claims** (C5 was 2 REVISE / 1
CONFIRMED), **0 net CONFIRMED**. The panel found the claims systematically over-stated relative to their
evidence and caught a real harness bug the self-review missed.

**Real bug (C1):** 8/30 `month_0` records had their `confidence` value leaked as text into `direct_answer`
(`...</parameter><parameter name="confidence">0.15`); `run_held_out.py` wrote `stated_confidence=null` and
`compute_ece` dropped them — removing 2 of 3 real negatives and inflating the headline. **Fixed forward**
(`_recover_leaked_confidence` in `run_held_out.py`) + rescored: corrected **n=20** (was 13), accuracy **0.85**
(was 0.923), ECE_raw **0.510** (was 0.582), **3** real negatives now in the aggregate (Q02/Q05/Q12).
`reports/ece_month0_corrected_20260711.json` supersedes the buggy figures.

**Corrected claims (honest walk-back; the prior three `2026-07-11_*.html` reports are version-preserved per
ADR-0002 and superseded by these):**
- C1 under-confidence is **suggestive, relative to an ungrounded LLM judge**, on a small single snapshot — not
  "systematic".
- C2 the panel is not literally unanimous, but 90% of divergence is **adjacent-label grading noise** and Opus is
  both author and judge — does NOT demonstrate epistemic independence.
- C3 the L1 literature lift is **not statistically distinguishable from zero** (17/29 ≈ coin flip).
- C4 Level-2 is a **promising directional signal on a favorable n=6 subset**, not "the lever" established;
  metrics are correlated surface readouts and the judge fabricated verification it could not perform.
- C5 facts hold; it was **symbol-lookup verification**, not exhaustive per-binding cross-check.
- C6 the default-path **pass/fail verdict** is unchanged (not "byte-for-byte" — `as_dict` gained a key); the
  smoke suite does not cover reingest; opt-in provenance is an unauthenticated caller-file scan.
- C7 confidence-thresholding is **a** defensible signal, not proven "best" (Q07 is n=1 and circular; confidence
  currently over-fires).

**Standing method flaws to fix (from the panel):** (1) **judge-fabrication** — the judge, given only text,
asserted having "verified against Ensembl" in 11/18 verdicts; the quality metric partly rewards the *appearance*
of grounding; (2) LLM-judge is not ground truth; (3) same-vendor panel ≠ independence; (4) small/favorable n;
(5) ADR-0036 provenance is not authenticated.

## Alternatives considered

- **Treat the session claims as validated** (self-review only) — REJECTED: prohibited by §7; and it would have
  shipped the inflated A1 numbers + the parser bug.
- **Rewrite the three prior reports in place** — REJECTED (ADR-0002 version preservation); the audit report
  supersedes their over-claims instead.

## Consequences

- The honest project state: this session produced **measured + audited-and-corrected** evidence, not validated
  claims. Every headline was walked back to what the (small, LLM-judge, single-snapshot) evidence supports.
- Highest-value follow-ups now explicit: fix judge-fabrication; get independent ground truth; scale Level-2 to
  30; add a non-Anthropic judge. These gate any future strengthening of the claims.
- Demonstrates the gate's value: the composite-auditor caught a real bug + systematic over-claiming that the
  producing agent's own review did not — the §7 "self-audit is not a gate" rule earned its keep here.

## Evidence

- Verdicts: `reports/2026-07-11_closing-audit_verdicts.json` (7 claims × 3 auditors); workflow
  `evaluation/workflows/session_closing_composite_audit.js`.
- Report: `reports/2026-07-11_closing-composite-audit_retrospective.html` (TYPE D).
- Bug fix + rescore: `evaluation/run_held_out.py` (`_recover_leaked_confidence`);
  `reports/ece_month0_corrected_20260711.json`.
- Prior: ADR-0006 (composite-auditor replaces single-LLM audit), ADR-0031 (multi-family panels),
  ADR-0035/0036 (the audited additions).
