# Substrate calibration records

Test 4 (calibration tracking) requires more than self-reported confidence trajectories. This directory holds **claim records** that can be matched against ground truth when outcomes arrive.

## Why this exists

The 2026-05-09 session documented a confidence trajectory 0.78 → 0.96. That trajectory is self-reported, not validated. Until claims are matched against observable outcomes, the trajectory tells us how confident the agent felt, not whether it was right.

This directory institutionalizes the matching. Each substantive substrate-instrumented output generates a record; when ground truth arrives (experiment result, literature confirmation, time-resolved outcome), the record is updated.

## Skills contributing records

- `squidiff-in-silico-gate` (Mode 1 and Mode 3 outputs with confidence < 0.95 and checkable outcomes) — automatic
- `causal-ablation-cascade-sim` (cascade scenario predictions with checkable outcomes) — automatic
- Other substrate-instrumented skills, when added — must implement the same record-writing pattern

## Record format

One JSON file per claim, filename pattern: `claim_YYYYMMDD_HHMMSS_<short-slug>.json`. Schema:

```json
{
  "claim_id": "claim_20260512_143022_hoxb8a-tier-1",
  "claim_timestamp": "2026-05-12T14:30:22Z",
  "session_id": "<session identifier or report filename>",
  "skill_origin": "squidiff-in-silico-gate | organogenesis-agent-architect | manual",
  "skill_version": "squidiff-in-silico-gate-v2.0.1",
  "claim_text": "hoxb8a is a Tier 1 TF candidate for pronephros perturbation, specificity ratio ~5.4× better than mafba.",
  "claim_category": "ranking | binary | extraction | generation",
  "prior": 0.75,
  "stated_confidence": 0.92,
  "framework_applied": "Self-Consistency (Tier 1) — per reasoning-frameworks-catalog.md §X",
  "expected_outcome_if_h1": "Wet-lab KO produces pronephros-specific phenotype matching cluster predictions.",
  "expected_outcome_if_h0": "Wet-lab KO produces systemic phenotype or no pronephros effect.",
  "observable_at": "wet-lab completion of experiment N",
  "observed_outcome": null,
  "observed_at": null,
  "post_hoc_calibration_applied": null,
  "test_mapping": ["test_4"],
  "epoch": "2026-Q2",
  "seed": 42
}
```

## When to write a record

Any structured-output substrate-instrumented agent output with confidence < 0.95 and a checkable outcome. Confidence ≥ 0.95 records are optional but encouraged.

**For Squidiff specifically:** Mode 1 and Mode 3 outputs with confidence < 0.95. Skip Mode 0 (synthetic mode is not for calibration evidence — confidence capped at 0.50 is not a real signal).

The claim record MUST include the `seed` field. This is what makes calibration auditable across re-runs: a record can be replayed by re-invoking the skill with the same seed and inputs, verifying that the prediction was deterministic. If a future re-run with the same seed produces a different `stated_confidence`, the substrate has drifted — that's a Test 4 signal.

## When to update a record

When the outcome is observable: append `observed_outcome` and `observed_at`. Do not modify `stated_confidence`, `prior`, or `framework_applied` post-hoc. The point is to measure calibration, not to revise it.

## Aggregation

`tools/compute_ece.py` walks `records/`, applies post-hoc calibration methods (isotonic regression, histogram binning), and produces quarterly Brier score + ECE per category. Three-tier reporting per `PROJECT_SCOPE.md` §5 Test 4.
