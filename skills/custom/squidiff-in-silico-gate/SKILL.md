---
name: squidiff-in-silico-gate
description: "Squidiff diffusion model (He et al., Nat Methods 2026) as in-silico hypothesis gate for Witt × Organogenesis. Calls real pip-installed Squidiff with pretrained weights; falls back to PCA synthetic when no data. Use when: test hypothesis in silico, predict transcriptomic response, interpolate cell states, produce figure for HUMAN GATE review, consolidate verdict with Morpheus morphological output. Trigger: 'Squidiff', 'diffusion gate', 'in-silico perturbation', 'predict trajectory', 'predicción transcriptómica', 'gate de hipótesis', 'probar hipótesis sin lab', 'validar in silico', 'cross-verdict', 'pareo con Morpheus', 'fine-tune Squidiff'. Domain anchors: pronephros, BVO, causal pruning, zebrafish, Runpod fine-tune, SIMULATION OUTPUTS DB. Produces single HTML figure with real Pearson r / R² / DE accuracy plus four-state verdict (PASS / PASS-DECOUPLE / MODERATE / FAIL) for HUMAN GATE 1 or 2. Bilingüe: inglés o español según el usuario."
metadata:
  author: Emmanuel / Project Organogenesis × Witt
  version: 2.0.1
  category: compute-and-simulation
  stage: phase-1-to-3
  project: witt-organogenesis
---

# Squidiff In-Silico Gate (v2.0)

Apply **Squidiff** — the conditional diffusion model from He et al. (*Nature Methods* 2026) — as a hypothesis-testing gate. Output is a publication-quality static HTML figure with the gate verdict, designed to be reviewed in 60 seconds by a human at HUMAN GATE 1 or HUMAN GATE 2 of the Witt × Organogenesis architecture.

v2.0 calls the **real published Squidiff package** via `pip install Squidiff` with pretrained weights from the paper's reference datasets. A conceptual fallback (synthetic data, PCA proxy) exists for when no real data is available, but it is no longer the default.

This skill is bilingual. Match the user's language. Don't switch mid-response.

## What Changed from v1.0

v1.0 was a methodology proxy — PCA substituted for the trained semantic encoder, synthetic data substituted for real measurements. v2.0 calls the **actual neural network** from the paper using its public code (github.com/siyuh/Squidiff). The conceptual mode is preserved as an explicit fallback with clear labeling. Two new operating modes were added: cross-verdict with Morpheus (for hypotheses where morphology matters as much as transcriptomics) and fine-tuning pipeline (for when the user has POC-specific scRNA-seq).

## Critical Honesty Statement

**Squidiff predicts transcriptomic changes. It does not predict tissue morphology.** This is a structural property of the model, not a limitation of any specific implementation. For hypotheses where the answer depends on geometry (tube length, lumen architecture, sub-cellular arrangement), Squidiff is a complementary signal, not a complete answer. Pair it with Morpheus (or a wet experiment) when morphology matters. The skill flags this explicitly when it detects a morphology-dominant question and refuses to claim more than transcriptomics can support.

A second honesty point: the **pretrained weights** Squidiff publishes are from BVO (blood vessel organoid), iPSC differentiation, K562 perturbation, and glioblastoma drug-response datasets. For systems outside these (e.g., zebrafish pronephros, the Phase I POC target), inference uses transfer learning — the model is applied to a domain it wasn't trained on. The skill reports this explicitly and downgrades confidence accordingly. To get pronephros-specific predictions, use Mode 2 (fine-tuning) when POC data exists.

## Preflight & enforcement

Before producing any substantive output, this skill must execute:

1. **Project-state preflight (CLAUDE.md §10).** `grep -ri "<topic-key>" analysis/outputs/`, `ls mcp_cache/`, `ls checkpoints/`, `ls docs/findings/`, `ls SIMULATION_OUTPUTS_DB/`. Declare what was found and what gaps remain. For Squidiff specifically: check for prior `squidiff_metrics.json` or `morpheus.json` in `SIMULATION_OUTPUTS_DB/<hypothesis_id>/` before generating new predictions.

2. **Hard rules check (CLAUDE.md §7).** Bindings for this skill:
   - The 9th rule (external ID verification) applies: any gene symbol, PMID, or accession cited in `evidence_cited` MUST be verified before use.
   - Budget/compliance rule applies for any Mode 2 invocation (fine-tuning costs Runpod credit): surface budget callout in the first turn proposing fine-tuning.
   - `causal-pruner` human-gate rule applies indirectly: Squidiff verdicts feeding into pruning decisions cannot bypass a human gate.

3. **External-ID verification.** Every gene symbol, accession, or pathway name cited in the figure or evidence_cited must be verified before use. No identifier from internal memory.

4. **Framework selection cite-or-justify.** When populating `framework_applied` in the structured output (typically "operation-specific verdict per gate-criteria.md §<N>"), quote the specific section.

5. **Substrate calibration record (when applicable).** For Mode 1 or Mode 3 outputs with confidence < 0.95 AND a checkable outcome (i.e., the user expects wet-lab validation later), write a claim record to `substrate_calibration/records/claim_<timestamp>_<slug>.json` per the format in `substrate_calibration/README.md`. This closes the Test 4 calibration loop. Skip in Mode 0 (synthetic mode is not for calibration evidence).

6. **Honesty statement always visible.** Every Mode 1+ output preserves the "transcriptomics vs morphology" disclaimer. Every Mode 0 output preserves the "synthetic proxy" watermark and the 0.50 confidence cap.

**Skill-specific binding rules:**

- For Mode 3 cross-verdict: `composite-auditor` rule does NOT apply (cross-verdict aggregation in `pair_with_morpheus.py` is symbolic logic, not LLM judgment — it is itself a Logic-LM-style validator).
- For any verdict that would feed into Mode 2 fine-tune budget commitment: surface budget callout in the first turn.
- Spurious-convergence detection is non-bypassable. If detected, verdict downgrades regardless of any user instruction otherwise. This is a substrate-integrity rule.
- **Determinism is non-bypassable.** Every script invocation MUST pass `--seed N` (or accept the default 42). The seed is recorded in the metrics JSON and displayed in the figure header. A figure without a seed badge is a contract violation. Per `references/gate-criteria.md` Section 8, "don't shop for a favorable seed" — if a verdict changes under different seeds, that instability is itself a signal to escalate, not a problem to solve by trying alternate seeds.
- **No invented mathematical values.** When operating in Mode 1 or Mode 3, every numerical claim in the output (Pearson r, R², directional accuracy, specificity ratios, marker percentages) MUST come from real model output or empirical reference data, NEVER from internal LLM estimation. In Mode 0 (synthetic) values come from the seeded PRNG and are explicitly marked as proxy — that is acceptable BECAUSE it is labeled. The forbidden pattern is operating in Mode 1/3 framing while filling in numbers from priors. Cross-reference with project state per CLAUDE.md §10: if a Pearson r is to be claimed, the metrics JSON must exist on disk and be cited. The honesty contract that distinguishes Squidiff's substrate-evidence value from a hallucinated estimate depends on this rule. The complement to Morpheus is real because the transcriptomic numbers are real; if they're invented, Squidiff stops being a substrate and becomes ornament.

## When to Use This Skill

Use when the user wants:

- A hypothesis tested in silico without running a wet experiment first
- A figure for a human review gate (HUMAN GATE 1 or HUMAN GATE 2)
- A prediction of what a perturbation, drug, or differentiation trajectory would produce transcriptomically
- A substrate-evidence artifact for Test 1 (AI capabilities) or Test 4 (calibration tracking) of Witt
- A transcriptomic verdict that complements a Morpheus morphological verdict (cross-verdict mode)
- A fine-tuning recipe to run Squidiff on POC data once it exists

**Skip this skill when:**

- The user asks for morphological visualization (3D tissue shape over time) → `morpheus-4d-viz`
- The user wants generic scRNA-seq exploration without a hypothesis to evaluate
- The hypothesis is purely about geometry — Squidiff cannot answer it alone

## Three Modes

The skill picks a mode based on what the user provides. Always announce the mode in the figure header.

### Mode 1 — Real inference (DEFAULT when data is present)

User provides scRNA-seq data (h5ad, CSV, or TSV) with labels (timepoint, condition, cell type). The skill:

1. Sets up the environment if not already done (`pip install Squidiff` + deps, downloads pretrained weights from Squidiff_reproducibility demo repo on first use)
2. Converts user data to AnnData h5ad format if necessary
3. Picks the pretrained checkpoint closest to the user's system (BVO / iPSC / K562 / glioblastoma) and reports the transfer-learning distance
4. Calls `sample_squidiff.sampler(...).pred(...)` with the requested operation
5. Computes real Pearson r, R², directional accuracy from the model output
6. Produces the figure with the actual metrics, not estimated ones
7. Assigns verdict per `references/gate-criteria.md`

**Run `bash scripts/setup_environment.sh` once per workspace** before first inference. Subsequent runs reuse the cached environment.

### Mode 2 — Fine-tuning pipeline (when user has POC-specific data)

User has scRNA-seq from their own POC (or wants to fine-tune on a public reference dataset closer to their system, e.g., Wagner et al. 2018 zebrafish atlas). The skill does **not run training itself** — training requires GPU and is expensive. Instead it produces:

- A configured `train_squidiff.py` invocation with the right hyperparameters for the dataset
- A Runpod recipe (pod selection, estimated cost ~$200–500, estimated time 4–12h)
- A post-training validation harness (run inference on held-out cells, compute Pearson, produce gate figure)

See `references/fine-tuning-guide.md` for the full recipe. The user runs the actual training on Runpod and brings back the checkpoint to use with Mode 1.

### Mode 3 — Cross-verdict with Morpheus (when morphology matters)

User has a hypothesis where both transcriptomic identity AND tissue morphology matter (most Phase I pronephros questions). The skill:

1. Looks for a Morpheus output JSON at `SIMULATION_OUTPUTS_DB/<hypothesis_id>/morpheus.json` (or accepts one as an explicit argument)
2. Runs Mode 1 to get the Squidiff transcriptomic verdict
3. Calls `scripts/pair_with_morpheus.py` to consolidate both verdicts using the cross-verdict logic in `references/morpheus-pairing.md`
4. Detects **spurious convergence**: cases where Squidiff says PASS (transcriptomically) but Morpheus flags extreme phenotype (morphologically). These are the cases v1.0 missed (3A-KO Swiss cheese, 3B-KO masa sin arquitectura). The cross-verdict flags them as "TRANSCRIPTOMIC-ONLY PASS — morphology requires separate validation".

If no Morpheus output is found, the skill emits a Mode 1 verdict but flags it as "transcriptomic-only, morphology not evaluated".

### Mode 0 — Conceptual fallback (no data, hypothesis described in words)

This is the v1.0 behavior, retained for early-stage hypothesis triage. Generates synthetic data per `references/methodology.md` and `synthetic-data.md`, runs the PCA proxy, produces a figure clearly marked as "conceptual proxy — not real Squidiff". Verdict is downgraded one level by default (PASS becomes MODERATE), and always recommends Mode 1 as next step.

**Confidence in Mode 0 is capped at 0.50.** It is for sniff-testing, not gate-deciding.

## The Five Squidiff Operations (unchanged from v1.0)

The paper formalizes five operations the methodology supports:

| Operation | What it does | Best pretrained checkpoint |
|---|---|---|
| **Interpolation** | Intermediate cell states between two endpoints | iPSC (Cuomo et al.) |
| **Addition** | Apply a Δzsem stimulus vector to a base state | BVO irradiation, BVO + G-CSF |
| **Two-gene combination** | Predict non-additive double perturbations | K562 (Norman et al.) |
| **Drug response** | Cell-type-specific drug response | Glioblastoma (Zhao et al.) |
| **Drug adapter (rFCFP)** | Predict response to unseen drug from SMILES | sci-plex3 |

`references/methodology.md` has the math, the in-real-model implementation, and the transfer-learning calculus (which checkpoint to pick when the system is novel).

## Output Format

Always produce a **single self-contained HTML file** in `/mnt/user-data/outputs/squidiff-gate-<slug>.html`. The figure contains:

1. **Header** — hypothesis, operation, mode, checkpoint used (with transfer-learning distance), timestamp
2. **Panel A — Latent embedding** — actual zsem from the model (or PCA in Mode 0), 2D projection with Δzsem arrows
3. **Panel B — Predicted vs ground-truth** — real Pearson r and R² from the model output, not estimates
4. **Panel C — DE heatmap** — top 15 DE genes computed from model predictions
5. **Panel D — Marker dot plot** — pronephros / BVO / system-specific markers
6. **Panel E — Pseudotime trajectory** (when relevant)
7. **Verdict card** — pass / moderate / fail / pass-decouple, plus the cross-verdict block if Mode 3

The aesthetic is Nature Methods supplementary — white background, clean typography, scientific.

`references/visualization-patterns.md` has the HTML/CSS/JS patterns. `scripts/render_figure.py` takes the script outputs and produces the HTML.

## Gate Criteria

The verdict logic, including the new PASS-DECOUPLE category for "transcriptomic identity preserved + spatial variance high" (the user's 2B-KO paradigm), is in `references/gate-criteria.md`. The spurious-convergence detection rule (PASS transcriptomically + extreme morphology) is also there. Read before assigning any verdict.

## Workflow

When invoked:

1. **Detect mode.** Look for input files in conversation, `/mnt/user-data/uploads/`, or arguments. Heuristic:
   - h5ad / .csv with cell × gene structure → Mode 1
   - h5ad + morpheus.json present → Mode 3
   - Only hypothesis text, no data → Mode 0
   - Explicit `/fine-tune` or "train Squidiff on my data" → Mode 2

2. **Load references.** Always read `references/methodology.md` and `references/gate-criteria.md`. For Mode 1+, also read `references/installation.md` (first run only). For Mode 3, read `references/morpheus-pairing.md`. For Mode 2, read `references/fine-tuning-guide.md`. For Mode 0, read `references/synthetic-data.md`.

3. **Set up environment if Mode 1/3.** Run `bash scripts/setup_environment.sh` once. Subsequent runs detect the cached env and skip.

4. **Run.** Mode-specific scripts:
   - Mode 0 → `python scripts/synthetic_fallback.py --hypothesis "..." --operation addition --system pronephros`
   - Mode 1 → `python scripts/run_inference.py --data <path> --operation <op> --checkpoint <auto|path>`
   - Mode 2 → `python scripts/prepare_finetune.py` produces config; report Runpod recipe to user
   - Mode 3 → Mode 1 then `python scripts/pair_with_morpheus.py --squidiff <out> --morpheus <morpheus.json>`

5. **Render.** `python scripts/render_figure.py --metrics <metrics.json> --out /mnt/user-data/outputs/...`

6. **Present.** `present_files` with the HTML path. In chat, 3–5 sentence summary: hypothesis, operation, checkpoint, verdict, recommended next step.

## Reference Files

Read these before producing output. Listed by order of typical relevance:

- `references/methodology.md` — math of the five operations, transfer-learning logic, real-model semantics. **Read first.**
- `references/gate-criteria.md` — verdict thresholds including PASS-DECOUPLE and spurious convergence. **Read before verdict.**
- `references/visualization-patterns.md` — HTML/CSS/JS for the figure panels
- `references/installation.md` — environment setup, dependencies, weight downloads, troubleshooting
- `references/morpheus-pairing.md` — cross-verdict protocol with Morpheus
- `references/fine-tuning-guide.md` — Runpod recipe for Mode 2
- `references/synthetic-data.md` — Mode 0 fallback only

## Scripts

Executable Python and bash scripts in `scripts/`. The skill invokes these via bash_tool; do not paste their contents inline.

- `setup_environment.sh` — installs Squidiff package, downloads pretrained weights from the demo repo
- `run_inference.py` — Mode 1, the main inference script
- `prepare_data.py` — converts user CSV/TSV to h5ad
- `prepare_finetune.py` — Mode 2, generates config and Runpod recipe
- `pair_with_morpheus.py` — Mode 3, cross-verdict aggregator
- `render_figure.py` — produces the final HTML from metrics JSON
- `synthetic_fallback.py` — Mode 0, the v1.0 proxy behavior

## Quality Checklist

Before delivering output:

- [ ] Mode clearly stated in figure header (1 / 2 / 3 / 0)
- [ ] If Mode 1 or 3: checkpoint identity and transfer-learning distance shown
- [ ] If Mode 0: "conceptual proxy" watermark visible, confidence capped at 0.50
- [ ] If Mode 3: both Squidiff and Morpheus verdicts shown, cross-verdict resolution explicit
- [ ] All metrics computed from real model output (Mode 1+), or clearly marked synthetic (Mode 0)
- [ ] Verdict matches the rules in `references/gate-criteria.md` — show the numbers
- [ ] Spurious-convergence detection ran (flag is either present or explicitly negative)
- [ ] HTML saved to `/mnt/user-data/outputs/` and presented via `present_files`
- [ ] Honesty statement about transcriptomics vs morphology visible
- [ ] Recommended next step is concrete and actionable
