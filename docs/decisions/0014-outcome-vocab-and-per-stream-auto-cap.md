# 0014 — Outcome vocabulary reconciliation + per-stream auto-cap regime

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** `compute_ece.py`, `rolling_calibration.py`, claim-record schema, Test 4

## Context

Two related calibration ambiguities needed a decision:
1. **Outcome vocabulary.** Claim records mixed `h1`/`h0` (the 2026-05-14 records) and `positive` (the
   first resolved record, 2026-05-31). The original `compute_ece.py` scored anything `!= "h1"` as 0.0,
   so the resolved `positive` record would have been scored WRONG (a latent bug).
2. **Auto-cap regime.** autoresearch parity caps to 0.30 when hit-rate < 0.34; INTEGRATION §5.4 caps to
   `max(declared, 0.60)` when < 0.60. These are different regimes for different risk profiles.

## Decision

1. **Outcome enum:** `positive | negative | unfalsifiable_in_phase_I` (with back-compat aliases
   `h1→positive`, `h0→negative`, `true/correct`, `false/incorrect`). `unfalsifiable` is **excluded**
   from ECE, not scored 0.0. Implemented in `compute_ece.outcome_to_label()`.
2. **Per-stream auto-cap (chosen by Emmanuel over single-regime options):**
   - `extraction` / toy / deterministic: trigger hit-rate < **0.34** → clamp to **0.30** (autoresearch parity).
   - biomedical hypotheses (`ranking`/`generation`; signaling/morphogenesis/single-cell sub-domains):
     trigger < **0.60** → clamp to **max(declared, 0.60)** (INTEGRATION §5.4).
   Stream selected by `claim_category` + `sub_domain`. Documented in `RIL_PROGRAM.md` §4.

## Alternatives considered

- Single regime (autoresearch-only, or INTEGRATION-only). Rejected: the toy/extraction stream and the
  biomedical-hypothesis stream have genuinely different overconfidence profiles; one threshold misfits one.
- Score `unfalsifiable` as 0.0. Rejected: it would punish honest "can't be checked in Phase I" claims.

## Consequences

- The resolved 2026-05-31 record now scores correctly; `compute_ece` reports n_scored=2 "case capture".
- `rolling_calibration.py` applies the regime matching the claim's stream.

## Evidence

`substrate_calibration/tools/compute_ece.py` (the fix); `program.v3.md` §13; INTEGRATION_PROPOSAL §5.4;
the resolved records under `substrate_calibration/records/`.
