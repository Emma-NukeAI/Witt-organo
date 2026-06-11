# 0012 — Reactive calibration (rolling K=6 + auto-cap) supersedes quarterly-only

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** `calibration-tracker`, `reasoning-exposer`, Test 4, the RIL (Cycle 3)

## Context

PROJECT_SCOPE §5 Test 4 computes calibration **quarterly** (months 2/5/8). autoresearch's `program.md`
v3 §13 showed that a **per-output** reactive tally (rolling K=6 hit-rate with an auto-cap) catches
overconfidence within a run, not three months later. The RIL needs the online safety floor.

## Decision

Add reactive calibration as a per-output mechanism (state in `retrospectives/rolling_calibration.json`,
updated by `tools/rolling_calibration.py`). When the high-confidence (≥0.70) hit-rate over the last
K=6 resolved predictions drops below the stream threshold, `reasoning-exposer` clamps new
`stated_confidence` to the stream cap until a correct high-conf prediction restores the window. The
quarterly ECE (compute_ece.py) is **retained** as the aggregate; reactive calibration is the online
complement, not a replacement. Threshold/cap regime is per-stream (see ADR-0014).

## Alternatives considered

- Quarterly-only (status quo). Rejected: too slow to catch within-run overconfidence; the documented
  failure mode (confidence trajectories that look good but are unvalidated) needs a faster signal.
- Batch (every N outputs). Rejected: autoresearch found per-output is what makes the cap responsive.

## Consequences

- Easier: overconfidence self-corrects mid-flight; cap-active→lifted recovery is a Test-3 signal.
- Care: cap can over-hedge on a short bad streak; mitigated by per-stream thresholds (ADR-0014) and
  the K=6 window (dormant until ≥6 resolved).

## Evidence

`docs/autoresearch-handoff/program.v3.md` §13; `substrate_calibration/RIL_PROGRAM.md` §4; GWT v1.1 plan §5.4.
