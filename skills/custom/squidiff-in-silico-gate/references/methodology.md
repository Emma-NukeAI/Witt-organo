# Methodology Reference — Squidiff Operations (v2.0)

This file is the source of truth for the math each Squidiff operation performs and how the real Squidiff model implements it. Read this before producing any figure.

## What Changed from v1.0

v1.0 described how PCA serves as a proxy for the trained semantic encoder. v2.0 describes how the **real** Squidiff (via `pip install Squidiff`) executes each operation. The PCA proxy is retained only as the Mode 0 fallback (see `synthetic-data.md`); the default path is real inference.

## Table of Contents
1. The Squidiff architecture (recap)
2. Real-model semantics — what calling the package actually does
3. Operation 1 — Interpolation
4. Operation 2 — Addition
5. Operation 3 — Two-gene combination
6. Operation 4 — Drug response
7. Operation 5 — Drug adapter (rFCFP)
8. Transfer learning — when pretrained ≠ trained-on-your-system
9. What Squidiff cannot do

---

## 1. The Squidiff Architecture (Recap)

Squidiff is a conditional denoising diffusion implicit model (DDIM) with two components:

- **Semantic encoder** `Enc(x₀)` → `zsem` — neural network that maps a cell's transcriptome into a low-dimensional latent capturing biologically meaningful variation
- **Conditional DDIM** — denoises Gaussian noise `xT ~ N(0, I)` conditioned on `zsem` to produce new transcriptomes

Together they enable: encode any cell → manipulate latent → decode back to gene space. The manipulations are the five operations below.

## 2. Real-Model Semantics — What Calling the Package Actually Does

When `scripts/run_inference.py` calls `Squidiff.sample_squidiff.sampler(model_path=...)`, it:

1. Loads a PyTorch checkpoint (the pretrained weights)
2. Reconstructs the encoder and DDIM modules with the same architecture used during training
3. Returns an object with `encoder` and `pred` methods

The encoder forward pass is `z_sem = sampler.model.encoder(X_tensor)`. The decoder pass is `X_pred = sampler.pred(z_sem, gene_size=N)`. Operations between these two calls are the five operations.

This is what makes v2.0 fundamentally different from v1.0: PCA is replaced by a learned encoder that has seen millions of single cells and knows non-linear cell-state manifolds. Operations expressed in PCA coordinates only capture linear structure; operations in real `z_sem` capture whatever the encoder learned.

## 3. Operation 1 — Interpolation

**Paper:** Fig 1g, Fig 2b–c (iPSC differentiation), Fig 4c (BVO trajectory).

**Math:**

Given two states with embeddings `z¹sem` and `z²sem`:

```
zsem(t) = (1 - t) · z¹sem + t · z²sem,   t ∈ [0, 1]
x_pred(t) = sampler.pred(zsem(t), gene_size=N)
```

Linear in the latent. Non-linear in gene space (the decoder is a neural network).

**In the script:**

```python
z_src = sampler.model.encoder(X_src_tensor).mean(dim=0, keepdim=True)
z_tgt = sampler.model.encoder(X_tgt_tensor).mean(dim=0, keepdim=True)
for t in [0.25, 0.5, 0.75]:
    z_interp = (1 - t) * z_src + t * z_tgt
    X_pred[t] = sampler.pred(z_interp.repeat(n_cells, 1), gene_size=N)
```

**Validation:** if the user provides intermediate-state cells, compute Pearson against them. Without intermediates, report `latent_pca` (for visualization) and `delta_zsem_norm` (sanity-check that source and target are actually separable in latent).

**Verdict caveats:** the paper achieves r ≥ 0.85 on iPSC differentiation when the trajectory is roughly straight in latent. Curved trajectories (multiple growth factors at different timepoints) give lower r — note this when the user describes a multi-input intervention.

## 4. Operation 2 — Addition

**Paper:** Fig 1e–f, Fig 2a, Fig 5b–c (radiation perturbation across cell types).

**Math:**

Given control and perturbed populations:

```
Δzsem = mean(zsem_perturbed) - mean(zsem_control)
zsem_pred(cell_i) = zsem(cell_i) + Δzsem
x_pred(cell_i) = sampler.pred(zsem_pred)
```

This is the most common operation for Witt's POC because every causal-pruning experiment is some form of "what would happen if we applied this perturbation". The user's 13-scenario contractility experiment is 12 addition operations (one per non-control scenario).

**In the script:** see `_run_addition` in `run_inference.py`. The metrics reported are:
- Pearson r between predicted and ground-truth target mean
- R² 
- Directional accuracy on top-20 DE genes
- |Δzsem| (latent perturbation magnitude — useful for ranking scenarios by perturbation strength)

**Verdict caveats:** the paper validates this works across cell types (learn Δzsem on endothelial, apply to mural). When the target cell type is far from the type Δzsem was learned on, accuracy drops. The skill measures this distance and downgrades verdict accordingly.

## 5. Operation 3 — Two-Gene Combination

**Paper:** Fig 3a–c, validated on K562 cells.

**Math:**

```
Δzsem_combined = Δzsem_g1 + Δzsem_g2
zsem_pred = zsem_base + Δzsem_combined
```

The interesting property of the trained model: this captures **non-additive** interactions even though the operation is mathematically additive in latent space. The non-additivity emerges from the encoder's learned non-linear structure — the same gene-set perturbation has different latent representations depending on the cellular context.

**Implementation:** requires two pre-learned single-gene perturbation Δzsem vectors. The script supports this when the user provides paired control + single-perturbation + double-perturbation labels.

**Verdict caveats:** the paper's `k562` checkpoint is the best fit. Other checkpoints have not been validated on two-gene combinations and the skill applies a confidence penalty.

## 6. Operation 4 — Drug Response

**Paper:** Fig 3d–g, validated on glioblastoma with six drugs across three cell types.

**Math:** conditional `zsem(c, d) = Enc(x₀, c, d)` where `c` is cell type and `d` is drug. Predicting `d` on a new cell type `c'` uses the conditional structure to generalize.

**Implementation:** requires data with both cell type and drug labels, and at least one cell type with the drug already in training. The `glioblastoma` checkpoint is the canonical one for this operation.

**Verdict caveats:** when the user asks about a drug not in the training set, this becomes Operation 5 (drug adapter), which is weaker. When the user asks about a cell type not in training, the skill reports the latent distance to nearest trained cell type and applies a penalty.

## 7. Operation 5 — Drug Adapter (rFCFP)

**Paper:** Fig 3h–i, integrated with PRNet's molecular fingerprint adapter.

**Math:**

```
zsem' = Enc(x₀, rFCFP(SMILES))
```

The fingerprint goes through an adapter network that maps molecular structure to a perturbation direction in latent space. The `sciplex` checkpoint includes this adapter.

**Implementation:** requires `rdkit` (installed optionally by setup script). The user provides SMILES, the script computes Morgan fingerprints, and the adapter handles the rest.

**Verdict caveats:** the paper notes that even with the adapter, novel-drug prediction is the hardest case. The skill's default verdict for Operation 5 is MODERATE unless substantial training data is available. PASS for Operation 5 requires explicit user acknowledgment of the difficulty.

## 8. Transfer Learning — When Pretrained ≠ Trained-On-Your-System

This is the most important difference between v2.0 and v1.0 from the user's perspective. Real Squidiff with pretrained weights does not magically know your system. It knows the systems it was trained on (BVO, iPSC, K562, glioblastoma, sci-plex).

The skill measures **transfer distance**:

- `near`: user system is essentially the trained system (BVO data on BVO model)
- `mid`: user system is structurally similar (zebrafish pronephros on iPSC model — both ESC-to-mesoderm-to-tissue developmental logic)
- `far`: user system is structurally different (drug screen on iPSC model, gene perturbation on BVO model)
- `unknown`: no documented analogy

The penalty applied at each distance is in `gate-criteria.md`. `far` distance is a one-level verdict downgrade; `mid` is a confidence × 0.90; `near` is no penalty.

**For Witt's pronephros POC**, the situation is:
- No `near` checkpoint exists
- `ipsc` is the best `mid`-distance fit (both are ESC → mesoderm differentiation)
- Mode 1 with `ipsc` checkpoint gives a starting verdict but with confidence penalty
- Mode 2 (fine-tune from `ipsc` on zebrafish or POC data) reduces this to `near` and removes the penalty

This is why the fine-tuning guide exists. It's the path from "Squidiff applied transfer" to "Squidiff on this domain".

## 9. What Squidiff Cannot Do

Even the perfectly-trained model has structural limits. These do not go away with Mode 2 or more data:

- **Predict tissue morphology.** Squidiff's output is a cells × genes matrix. It does not produce 3D shape, lumen architecture, or sub-cellular geometry. For these, pair with Morpheus.
- **Predict sub-cellular phenomena that don't show in bulk-cell expression.** Squidiff sees the mean (or distribution) of expression per cell. Phenomena visible only in single-molecule resolution or in protein localization are out of scope.
- **Predict mechanical or biophysical phenotypes directly.** It can predict the transcriptomic consequence of mechanical perturbation (via mechanotransduction → expression), but not the mechanical state itself.
- **Predict events outside the training data distribution.** Truly novel cell types, novel drug mechanisms, or novel developmental programs will fail unpredictably. The verdict carries this caveat as transfer distance.

These limits are why Witt's substrate has multiple simulators (Morpheus, BioDynamo, AlphaFold, Squidiff) rather than relying on any one. The cross-verdict in Mode 3 is the architectural expression of this: each simulator answers its question, and the substrate consolidates.
