# Gate Criteria — Verdict Logic (v2.0.1)

This file is the source of truth for how the gate verdict is computed. Every figure produced by this skill carries a verdict that follows these rules. Do not improvise — the verdict is the substrate-evidence signal, and consistency across runs is what makes the calibration data useful for Witt's Test 4.

## Table of Contents
1. The four verdict states
2. Thresholds by operation type
3. Mode-specific verdict computation
4. PASS-DECOUPLE — the new category
5. Spurious-convergence detection
6. Confidence estimates
7. Recommended next-step language
8. Determinism — non-negotiable for gate figures
9. When to refuse a verdict

---

## 1. The Four Verdict States

v2.0 introduces a fourth verdict: **PASS-DECOUPLE**, which v1.0 missed.

| Verdict | Meaning | Color | Action |
|---|---|---|---|
| **PASS** | Hypothesis consistent with Squidiff prediction. Commit resources. | Green `#2f855a` | Proceed |
| **PASS-DECOUPLE** | Identity preserved transcriptomically AND architecture decouples morphologically. The paradigm case (e.g., user's 2B-KO). | Indigo `#6366f1` | Proceed — paradigm-relevant |
| **MODERATE** | Partially supported. Refine or escalate before committing. | Amber `#b7791f` | Refine |
| **FAIL** | Inconsistent with prediction. Reject or rework. | Red `#c53030` | Reject |

The verdict is **not** a research conclusion. It is a triage signal. Every verdict carries the disclaimer about transcriptomics vs morphology.

---

## 2. Thresholds by Operation Type

The same as v1.0, but Mode 1 (real inference) trusts the numbers directly. Mode 0 (synthetic proxy) caps confidence at 0.50 regardless of metrics.

### Operation 2 — Addition (most common in pronephros work)

| Threshold | Verdict |
|---|---|
| Pearson r ≥ 0.80 AND directional accuracy ≥ 75% | PASS |
| Pearson r 0.55–0.80 OR directional accuracy 50–75% | MODERATE |
| Pearson r < 0.55 OR directional accuracy < 50% | FAIL |

**Transfer-learning distance penalty** (Mode 1):
- `far` distance → downgrade by one level
- `mid` distance → confidence × 0.90, verdict unchanged
- `near` distance → unchanged
- `unknown` → confidence × 0.85

This is what makes pronephros predictions honest. The iPSC checkpoint applied to pronephros gets `mid` distance — a PASS becomes a PASS with confidence 0.90× of nominal.

### Other operations

Same thresholds as v1.0 — see `methodology.md` for per-operation specifics. Interpolation, two-gene combination, drug response, and drug adapter all retain their v1.0 thresholds.

---

## 3. Mode-Specific Verdict Computation

### Mode 1 — Real inference

Take the Pearson r and directional accuracy directly from the model output. Apply the threshold table. Apply the transfer-distance penalty. Done.

### Mode 0 — Synthetic proxy

Same threshold table, but:
- Final confidence capped at **0.50**
- Recommended next step is always "Escalate to Mode 1 with real data"
- Verdict cannot be PASS-DECOUPLE in Mode 0 (it requires a morphology signal we don't have)

### Mode 3 — Cross-verdict with Morpheus

Run Mode 1 first to get the Squidiff verdict, then consolidate per Section 4 (PASS-DECOUPLE) and Section 5 (spurious convergence).

---

## 4. PASS-DECOUPLE — The New Category

PASS-DECOUPLE is for the case where:

1. **Transcriptomically**, the cellular identity is preserved (Squidiff verdict would be PASS or MODERATE with markers showing minimal change), AND
2. **Morphologically**, the tissue architecture is disrupted in a coherent, reproducible way (Morpheus verdict reports "decouple" or "extreme but identity-preserved phenotype")

The user's 2B-KO scenario is the prototype: contractility loss in stage 2 produces "no túbulo, foci dispersos wt1a+, identidad preservada". The cells are still pronephric — but the pronephros isn't there.

**Conditions for PASS-DECOUPLE:**

```
Squidiff verdict ∈ {PASS, MODERATE}
AND Morpheus phenotype_class indicates preserved-identity-but-disrupted-architecture
AND morphology_decouple == "pass-paradigm" or equivalent
```

PASS-DECOUPLE is **substrate-relevant**: it identifies the cases that test the causal-pruning hypothesis most directly. These are high-priority for wet validation.

Without a Morpheus signal (Mode 1 only), the skill **cannot** emit PASS-DECOUPLE. It is strictly a cross-verdict result.

---

## 5. Spurious-Convergence Detection

The failure mode v1.0 missed: Squidiff says PASS because transcriptomics is normal, but morphology is wildly abnormal (3A-KO "Swiss cheese", 3B-KO "masa sin arquitectura"). Both gates appear to converge on "OK", but they're answering different questions.

**Detection rule:**

```
IF Squidiff verdict ∈ {PASS, PASS-DECOUPLE}
   AND Morpheus phenotype_severity == "extreme"
   AND Morpheus phenotype_class ∈ {"swiss_cheese", "masa_sin_arquitectura",
                                    "catastrophic", "no_recognizable_organ"}
THEN
   flag = SPURIOUS_CONVERGENCE
   consolidated_verdict = MODERATE (downgraded)
   consolidated_label = "TRANSCRIPTOMIC-ONLY PASS (morphology contradicts)"
   confidence *= 0.5
```

The flag must be **visible** in the figure header, not hidden in a caption. This is the core substrate-integrity contract: we don't let a clean transcriptomic signal hide a destroyed tissue.

**When Mode 3 cannot run** (no Morpheus output available), the skill emits Mode 1 verdict but marks the figure with: "Transcriptomic-only — morphology not evaluated. Spurious-convergence check unavailable."

---

## 6. Confidence Estimates

v2.0 confidence calibration:

```
confidence = base × transfer_multiplier × mode_cap × sample_adequacy

base (from threshold table):
  PASS: 0.80
  PASS-DECOUPLE: 0.75 (slightly lower — it's a rarer call)
  MODERATE: 0.60
  FAIL: 0.70 (high confidence in fail)

transfer_multiplier (Mode 1):
  near: 1.00
  mid: 0.90
  far: 0.75
  unknown: 0.85

mode_cap:
  Mode 0: cap at 0.50
  Mode 1: cap at 0.85
  Mode 3 reinforcing: bonus × 1.10, cap at 0.95
  Mode 3 spurious: × 0.50, cap at 0.60

sample_adequacy:
  n_cells_per_state ≥ 200: 1.0
  50–200: 0.85
  < 50: 0.60
```

The confidence is logged for every verdict. Calibration evidence for Test 4 is the relationship between confidence and downstream wet-experiment outcome.

---

## 7. Recommended Next-Step Language

Every verdict carries a concrete next step. Don't hedge.

**PASS:**
- "Proceed to wet validation. Budget ~$Xk against [workstream]."
- "Lock for next sprint. Other candidates can be deprioritized."
- "Confirm with a Mode 2 fine-tune on POC data before scaling."

**PASS-DECOUPLE:**
- "Prioritize this hypothesis — it tests the paradigm directly. Allocate wet experiment in next 4 weeks."
- "Run replicate at higher n before committing publication budget."
- "Cross-check with the partner field (Test 5) — paradigm cases are the best generalization tests."

**MODERATE:**
- "Collect [specific data] to upgrade to Mode 1. Estimated time: X weeks."
- "Run a smaller version of this hypothesis first — [reduced experiment]."
- "Fine-tune Squidiff on closer reference data; ~$200 Runpod, 1 week."

**FAIL:**
- "Reject. Predicted DE pattern contradicts [specific known biology]."
- "Reformulate the operation. Likely the [interpolation/addition] doesn't match the question."
- "Pause and consult [domain expert] — proxy or model cannot resolve this."

**SPURIOUS CONVERGENCE (Mode 3 only):**
- "Do NOT proceed on transcriptomic signal alone. Morphology contradicts. Run wet validation focused on architectural phenotype."
- "This is the case where Squidiff is structurally blind. Trust Morpheus's morphology verdict over Squidiff's identity verdict."

Always end with one concrete action for the next 24–48h.

---

## 8. Determinism — Non-Negotiable for Gate Figures

Every figure produced by this skill **must be deterministic** — the same input produces the same output, every time, regardless of when or how often it is generated. This is non-negotiable for HUMAN GATE artifacts.

**Why:** A reviewer at HUMAN GATE 1 or 2 must be able to:
- Cite specific numerical values (Pearson r, Δzsem, DE genes) in meeting notes
- Compare two figures generated at different times for the same hypothesis
- Re-open a figure days later and see the same content
- Trust that a divergence between two figures reflects a real difference in inputs, not in random seeds

A figure whose values change on refresh fails all four. It cannot be used for substrate evidence (Test 4 calibration tracking specifically requires reproducible numbers), cannot be archived (the file isn't its own ground truth), and undermines reviewer confidence ("which value is the real one?").

**Implementation requirement:**

- Mode 0 (`synthetic_fallback.py`): pass `--seed N`, default 42. The PRNG (numpy default_rng) is seeded once before any sampling.
- Mode 1 (`run_inference.py`): pass `--seed N`, default 42. Seeds set on numpy, torch, and CUDA before any inference begins. `torch.backends.cudnn.deterministic = True`.
- Mode 3 (`pair_with_morpheus.py`): no stochastic component, deterministic by construction.
- HTML output (`render_figure.py`): if any JS embedded in the figure uses randomness (e.g., for jitter or layout), it must use a seeded PRNG (mulberry32 or equivalent), not `Math.random()`.

**The seed is reported in three places:**
- The metrics JSON has a top-level `seed` field
- The figure header has a `Seed: N (deterministic)` badge
- The verdict rationale references the seed when relevant

**Changing the seed is not a workaround.** A figure that produces different verdicts under different seeds is unstable; that instability is a signal that the hypothesis is not robustly testable in this mode and should be escalated. Do not "shop for" a favorable seed.

**Historical note:** Prior to May 14, 2026, HTML outputs from the conceptual mode used unseeded `Math.random()` in client-side JS, causing values and cluster positions to change on every page refresh. The v1.0 HTML shared with the team on May 13 had this bug. The fix is in v2.0.1 (this update) and is applied retroactively to the shared file.

---
---

## 9. When to Refuse a Verdict

Refuse and emit `NO VERDICT` when:

- Hypothesis is unfalsifiable
- Data is structurally incompatible with the operation (e.g., addition without labeled control + perturbed pairs)
- Hypothesis is outside Phase I scope (see PROJECT_SCOPE-v1.2.md)
- Hypothesis involves human embryos in any form (ISSCR 2025 non-negotiable)
- User intends to quote the verdict externally without the methodology disclaimer
- Mode 1 setup failed AND Mode 0 was not explicitly requested — better to refuse than mislead with a proxy the user didn't choose
- **The figure cannot be made deterministic** (see Section 8) — refuse rather than ship a figure whose values change on refresh

In refusal, produce the figure (it is still useful for thinking) with the verdict card showing:

```
NO VERDICT — [reason]
This figure is informational only. No gate evaluation performed.
```

Refusing is a substrate-integrity action. The skill's calibration value depends on it.

---
