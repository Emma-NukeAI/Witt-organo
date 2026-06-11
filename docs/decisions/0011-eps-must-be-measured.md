# 0011 — EPS must be measured (noise-probe before any improvement claim)

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** `evaluation-runner`, the RIL (RIL_PROGRAM §3/§8), Test 3

## Context

autoresearch v1's central mistake was reporting noise as a finding. v3 fixed it by **measuring** the
noise floor (EPS) before counting any delta as improvement. GWT v1.1's Test-3 iteration curve needs
the same discipline, or it will report provider/corpus drift as substrate learning.

## Decision

EPS is **measured, not assumed**. The noise-probe (`tools/noise_probe.py`) runs the held-out set as
paired identical replicas on three axes (Retrieval Jaccard, Citation overlap, Hypothesis cosine) and
records, per axis: median, σ, `EPS_delta = 2σ`, `EPS_pass = p25` (closes the C.20 naming collision).
No Test-3 delta is counted as improvement unless it (a) followed a same-config effective-frontier
re-measure within `REMEASURE_EVERY` outputs AND (b) exceeds `EPS_delta`. Otherwise it is logged as
`drift_suspected`.

**Phasing (NO-SPEND, honest):** axes a/b (set-overlap) are scaffolded and runnable now; axis c
(cosine) and the full probe require a local embedding model + a retrieval backend, which depend on the
RAG architecture that is still OPEN (plan §A). The scaffold proves the EPS math on synthetic pairs; the
held-out set v1 (30 questions, broad zebrafish biomedicine) is frozen as the month-0 baseline.

## Alternatives considered

- Single-pass evaluation (no noise probe). Rejected: the documented autoresearch failure mode.
- Assume a fixed EPS. Rejected: the noise floor is hardware/provider-dependent and must be measured.

## Consequences

- Easier: improvement claims become defensible (cleared a measured floor).
- Deferred: the real 3-axis probe activates with the RAG backend; until then EPS runs on a/b only.

## Evidence

`docs/autoresearch-handoff/STRATEGY_FINAL.md` §5.1; `program.v3.md` (EPS); `substrate_calibration/RIL_PROGRAM.md`
§3/§8; `substrate_calibration/tools/noise_probe.py`; `evaluation/held_out_set_v1.json`.
