# Fine-Tuning Guide — Mode 2

How to fine-tune Squidiff on your own data when the pretrained checkpoints don't cover your system. This is the path from "transfer-learning prediction" to "domain-specific prediction".

For the Witt × Organogenesis POC specifically, this becomes relevant once Phase I generates scRNA-seq data from zebrafish pronephros experiments (estimated month 4–6 of the timeline).

## When You Need Fine-Tuning

Run Mode 2 (fine-tune) when:

- The user's system is structurally different from the paper's training sets (BVO, iPSC, K562, glioblastoma, sci-plex). Pronephros zebrafish is structurally different from all five.
- Mode 1 transfer-learning distance comes back as `far` and verdicts are systematically downgrading
- The user has at least **2,000 cells per condition** of high-quality scRNA-seq from their system
- The budget allows ~$200–500 of GPU compute (within the Phase I $29k causal-pruning workstream cap)
- A trained checkpoint will be used on multiple hypotheses (one-shot fine-tunes for a single hypothesis are usually not worth the cost — use Mode 1 with caveats instead)

Skip Mode 2 when:

- The user's data is similar to a pretrained system (use Mode 1 with `near` transfer)
- The user has < 500 cells per condition (data too sparse for stable fine-tuning)
- The hypothesis can be answered by morphology alone (use Morpheus, skip Squidiff)
- POC data doesn't exist yet (wait — premature fine-tuning is throwaway work)

## What the Script Does

`scripts/prepare_finetune.py` produces a ready-to-run configuration package:

```
finetune_config/
├── README.md           Overview, what each file is for
├── train_command.sh    The actual training invocation
├── runpod_recipe.md    Step-by-step pod setup + cost estimate
└── validation.sh       Post-training validation harness
```

The script does **NOT** run training itself. Training needs GPU and is expensive. You run training on Runpod (or any GPU you have), then bring the checkpoint home.

## Choosing a Base Checkpoint

You always fine-tune from a pretrained base, not from scratch. Picking the right base saves training time and improves convergence.

| Your System | Recommended Base | Why |
|---|---|---|
| Zebrafish pronephros (Phase I POC) | `ipsc` | iPSC differentiation captures the ESC-to-mesoderm-to-tissue progression that's also operative in pronephros |
| Mouse kidney organoids (Phase II) | `ipsc` then re-fine-tune from your Phase I checkpoint | Stack the fine-tunes |
| Human PSC kidney organoids (Phase III) | Phase II checkpoint | Continue the stack |
| Vascular development | `bvo` | Direct fit |
| Other organoids | `ipsc` | Safe default for organogenesis |
| Drug screen | `glioblastoma` or `sciplex` | Drug-specific architectures |
| Gene knockout panel | `k562` | Perturbation-specific architecture |

For Phase I pronephros, start from `ipsc` and fine-tune on:
1. A zebrafish-specific public dataset first (e.g., Wagner et al. 2018 atlas) — ~$50–100, 2–4h
2. Then on your own POC data once available — ~$200–500, 4–12h

This two-step fine-tune produces a checkpoint that knows both "zebrafish development in general" and "your specific experimental conditions".

## Runpod Pod Selection

| GPU | VRAM | $/hr | When to use |
|---|---|---|---|
| RTX 3090 | 24 GB | ~$0.22 | gene_size ≤ 500, modest batch sizes |
| RTX 4090 | 24 GB | ~$0.34 | Default recommendation — fastest 24GB option |
| A6000 | 48 GB | ~$0.69 | gene_size > 1500 or you want big batches |
| A100 80GB | 80 GB | ~$1.50 | Overkill for Squidiff. Don't. |

Squidiff is small enough that **RTX 4090 is the sweet spot**. A100 is overkill and wastes money.

## Training Time and Cost

These are typical for a Squidiff fine-tune:

| Dataset Size | GPU | Time | Cost (Runpod community) |
|---|---|---|---|
| 5K cells × 500 genes | RTX 4090 | 2–4h | ~$1–2 |
| 20K cells × 500 genes | RTX 4090 | 4–8h | ~$2–4 |
| 50K cells × 500 genes | RTX 4090 | 8–16h | ~$3–6 |
| 100K cells × 1000 genes | A6000 | 12–24h | ~$10–18 |

Add ~$5–10 of buffer for pod setup, data upload, troubleshooting, checkpoint download. Plan for **$15–30 of actual spend per fine-tune attempt**. The $200–500 quoted in the SKILL.md is the worst case with multiple iterations.

## Post-Training Validation

After downloading the checkpoint, run `validation.sh` against a held-out portion of your data:

```bash
bash finetune_config/validation.sh ~/.squidiff-gate-weights/custom/pronephros_v1.pt held_out.h5ad
```

This runs Mode 1 inference with the fine-tuned checkpoint and produces a gate figure. Sanity criteria:

- **Pearson r ≥ 0.75** on the held-out condition. Below 0.6 means the fine-tune didn't take — possibly too little data or too aggressive learning rate.
- **Directional accuracy ≥ 70%** on top-20 DE genes. Below 50% means the model is anti-predicting — almost always a label or data orientation bug.
- **Latent space shows clear separation** between conditions. If the latent collapses (all conditions overlap), the encoder under-fit. Retrain with more epochs or larger model.
- **Reproducibility** — run the same inference twice. Pearson r should match to ≥ 0.99 (it's deterministic for a fixed seed).

If any of these fail, do NOT use the checkpoint for verdicts. Either retrain or fall back to Mode 1 with the pretrained base.

## Cost-Safety Discipline

Before starting any fine-tune:

- [ ] Confirm you have **at least 2,000 cells per condition** in your data
- [ ] Confirm metadata columns are clean (no missing labels, consistent values)
- [ ] Set a wall-clock budget (e.g., 12 hours max) — kill the pod if exceeded
- [ ] Have a held-out test set ready before training starts (don't generate it after — risk of leakage)
- [ ] Snapshot the pod every 2 hours during long runs (or download intermediate checkpoints)
- [ ] Verify checkpoint loads with `sample_squidiff` before terminating the pod
- [ ] **Stop the pod immediately after the checkpoint downloads** — Runpod bills per second

These are not pedantic. Pod-left-running incidents are how budgets get destroyed. The $3k Phase I compute hard-cap exists for a reason.

## The Stack-and-Specialize Pattern

The ideal trajectory through Phase I → Phase II → Phase III for the Witt POC:

```
ipsc.pt (Squidiff base)
     ↓ fine-tune on zebrafish atlas (Wagner 2018, ~$5)
zebrafish_general.pt
     ↓ fine-tune on POC data (Phase I scRNA-seq, ~$15)
pronephros_phase1.pt          ← Use this for all Phase I gate verdicts
     ↓ fine-tune on mouse data (Phase II, ~$30)
pronephros_phase2.pt
     ↓ fine-tune on human PSC organoid data (Phase III, ~$50)
pronephros_phase3.pt          ← Use this for late-stage verdicts and translation work
```

Each step costs little, and each produces a more specialized model. By the time Phase III closes, the checkpoint has seen the entire experimental trajectory and is the most authoritative substrate-evidence asset in the project.

This is the pattern. Plan for it from now; don't try to skip steps.

## Sharing Checkpoints with the Team

Once a checkpoint is validated, store it in the project's shared storage (NOT in the GitHub repo — model files are too big). Suggested location:

```
SIMULATION_OUTPUTS_DB/checkpoints/
├── pronephros_phase1_v1.pt
├── pronephros_phase1_v1.md      # what data trained on, validation Pearson, decisions
├── pronephros_phase1_v2.pt
└── ...
```

Every checkpoint gets a `.md` sidecar with provenance. Without provenance, the checkpoint is unauditable, and an unauditable checkpoint is substrate-corrupting. This rule is non-negotiable for Test 4 calibration tracking.

## Open Questions

Two things to decide as the POC progresses:

1. **Does Squidiff's architecture transfer well from human BVO to zebrafish pronephros?** The paper has no zebrafish validation. We'll know after the first fine-tune attempt. If Pearson r stays low even after fine-tuning, we may need to consider architecture modifications, which is research scope and not skill scope.

2. **Should the substrate maintain one master checkpoint or one per major experimental condition?** One master is simpler but less precise. One-per-condition is the paper's pattern (BVO model, iPSC model, etc.) but means more maintenance. Tentative answer: one master per phase, with optional specialized branches for specific conditions if Pearson gains are large (> 0.1).
