# Held-out evaluation set

This directory holds the frozen 60-80 question set for Test 3 (iteration loop) per `PROJECT_SCOPE.md` §5. Once month 0 is snapshotted, the questions are frozen — additions trigger versioning.

## Structure
- `held_out_set/INDEX.md` — master listing
- `held_out_set/q###-*.md` — individual question files with: question, expected output structure, target categories (binary/ranking/extraction/generation), substrate test mapping
- `perturbations/` — numerical, order, and surface perturbation generators per `evaluation-runner` v2.2 spec
- `runs/month_N/` — snapshot of substrate state, run logs, results per question per perturbation
- `reports/` — quarterly aggregation per Test 4 three-tier reporting

## Status
Month 0 baseline: [TBD: pending user-specified questions]
Month 4 target: [planned]
Month 8 target: [planned]

## Question categories required (per agent-catalog.md `evaluation-runner` v2.2)
- Binary classification questions
- Ranking questions (e.g., TF candidate ordering, Tier assignments)
- Extraction questions (e.g., identifying markers from text)
- Generation questions (e.g., experiment design, cascade simulation predictions)

## Skills contributing eval data automatically

- `squidiff-in-silico-gate` Mode 1/3 outputs → claim records → calibration evidence (also lives in `substrate_calibration/records/`)
- `organogenesis-agent-architect` outputs → structured-output contract claims
- `causal-ablation-cascade-sim` outputs → cascade scenario predictions per `references/protocol-and-decouple.md`

## Question file template

Each question lives in its own file `q###-<short-slug>.md` with this structure:

```yaml
---
question_id: q001
category: ranking | binary | extraction | generation
substrate_test_mapping: [test_1, test_3, test_4]
created: 2026-05-XX
frozen_at_month: 0
---

## Question

[Full question text in user-facing language]

## Expected output structure

[What a correct response looks like — schema, not literal answer]

## Evaluation criteria

[How to score — what counts as correct/approximate/wrong]

## Perturbation classes applicable

- Numerical: [yes/no — describe what numbers can vary]
- Order: [yes/no — describe what can be reordered]
- Surface: [yes/no — describe what surface changes preserve semantics]

## Confidence threshold

High-confidence prediction (target ≥85% accurate per Test 4): [threshold]
```
