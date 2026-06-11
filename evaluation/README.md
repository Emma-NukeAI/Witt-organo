# Held-out evaluation set

This directory holds the frozen 60-80 question set for Test 3 (iteration loop) per `PROJECT_SCOPE.md` §5. Once month 0 is snapshotted, the questions are frozen — additions trigger versioning.

## Structure
- `held_out_set/INDEX.md` — master listing
- `held_out_set/q###-*.md` — individual question files with: question, expected output structure, target categories (binary/ranking/extraction/generation), substrate test mapping
- `perturbations/` — numerical, order, and surface perturbation generators per `evaluation-runner` v2.2 spec
- `runs/month_N/` — snapshot of substrate state, run logs, results per question per perturbation
- `reports/` — quarterly aggregation per Test 4 three-tier reporting

## Status
**Month 0 baseline: `held_out_set_v1.json` (GWT v1.1 Cycle 2, 2026-06-11).** A frozen v1 of **30
questions** spanning **broad zebrafish biomedicine** — NOT pronephros-only — across the 13 niches
(Indices_nichos) and the 9 authoritative databases (Bases de datos), modeled on real team-biomedic
interactions (the Nat Witt cornea/N5 sessions: regulator-vs-bystander, Morpheus model assembly,
specificity ratio, ortholog mapping, simulation debug). Cross-field (N5-ophthalmology) items carry
`EXPLORATORY-NOT-TEST-5`. This v1 (30) is below the 60-80 target — it is the "prueba pequeño" seed;
expansion to 60-80 is the next increment (bump `set_version`).
Month 4 target: [planned — run with perturbations + noise-probe once a retrieval backend exists]
Month 8 target: [planned]

## Noise-probe / EPS (RIL_PROGRAM.md §3)
`substrate_calibration/tools/noise_probe.py` measures the run-to-run noise floor on three axes
(Retrieval Jaccard, Citation overlap, Hypothesis cosine) so improvements are distinguished from drift
(`EPS_delta=2σ`, `EPS_pass=p25`). Axes a/b run on set-overlap now; axis c (cosine) and the real probe
await the RAG/retrieval backend (plan §A OPEN). The scaffold's self-test proves the EPS math NO-SPEND.

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
