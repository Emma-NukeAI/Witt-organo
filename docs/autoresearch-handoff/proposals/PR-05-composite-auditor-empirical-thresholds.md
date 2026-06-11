# PR-05 — composite-auditor empirical thresholds (p25) + multi-family (NO-SPEND gated)

- **Status:** APPLIED (threshold note in catalog); multi-family DEFERRED (NO-SPEND block).
- **Target:** `composite-auditor` block in `agent-catalog.md`.
- **Depends on:** PR-04 conceptually; ADR-0011 (EPS_pass=p25).
- **Closes:** part of C.16 (Self-Consistency independence — prompt variation still deferred).

## Decision

The composite-auditor's Self-Consistency agreement threshold is the **empirical p25** (`EPS_pass`) of the
measured agreement distribution, **not the arbitrary "70%"**. This ties the audit pass/fail to the
measured noise floor (RIL_PROGRAM §3). Multi-family (N=3-5 generators from DIFFERENT model families) is
the INTEGRATION §5.3 ideal but is **NO-SPEND-gated**: Phase I uses single-family Self-Consistency with
the limitation logged + a lowered default confidence; multi-family activates only on explicit budget
approval. Prompt variation across runs (not just family variation) is a further mitigation, deferred.

## Cycle status

- Applied: the p25-threshold note in the `composite-auditor` catalog block.
- Deferred: multi-family (paid, multi-API); prompt-variation mitigation. Logged limitation until budget.
