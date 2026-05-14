# Protocol and Decouple Paradigm

Detail reference for the 4-scenario design, the decouple test scoring, and cross-stage synthesis.

- §1 The 4-scenario protocol — design rationale and confidence calibration
- §2 The decouple paradigm — scoring rubric and transcriptomic predictions
- §3 Cross-stage synthesis — when ≥2 stages

---

## §1 The 4-scenario protocol

For each developmental stage being perturbed, run exactly 4 scenarios. This is "máxima probabilidad de éxito" — calibrated for causal inference quality, not minimum cost.

### 1.1 Modes

**Mode A — stage-specific with washout**

Perturbation ON only during the stage's window, then released. Wet-lab analog: photo-activated blebbistatin pulse + photo-released. **Isolates causality OF the stage** — if the phenotype appears after washout, it must originate from the stage's window.

**Mode B — persistent**

Perturbation starts at the stage's window onset and continues. Wet-lab analog: maternal-zygotic mutant. **Captures cascade ACCUMULATIVE effects** but cannot isolate stage-specific causality from downstream effects — Mode B is a *reference* and *contrast*, not isolated evidence.

### 1.2 Doses

**Hipomorfo (~50% activity reduction)** — sub-letal. Modal phenotype detectable with best signal-to-noise. Default "best evidence" dose.

**KO (~95% activity reduction)** — near-complete loss. Strong but variable. Often catastrophic with reduced survival. Useful as control positive of extreme or to detect threshold effects.

### 1.3 The 4-scenario matrix

|        | Mode A washout | Mode B persistent |
|--------|----------------|--------------------|
| **Hipo (~50%)** | {N}A-hipo · highest causal value | {N}B-hipo · reference |
| **KO (~95%)**   | {N}A-KO · strong with variance   | {N}B-KO · control positive |

### 1.4 Why exactly 4

- **A vs B at same dose** distinguishes stage-specific causality from cascade. Without this contrast, all claims confound.
- **Hipo vs KO at same mode** maps the dose-fenotipo curve. Without this, cannot tell modal from catastrophic.
- Together, the 4 mitigate (not eliminate) Gate 4 parsimonia.

Fewer scenarios = ambiguous attribution. More scenarios (intermediate doses, additional timing variants) = marginal gain for substantial cost in scenario tracking, narrative complexity, and downstream wet-lab planning.

### 1.5 Confidence calibration heuristics

Pre-validation prior bounds per scenario family:

- **{N}A-hipo**: typically 0.75–0.85 — highest of the 4 within a stage
- **{N}A-KO**: typically 0.70–0.80 — high but more varianced
- **{N}B-hipo**: typically 0.60–0.70 — confounded with cascade
- **{N}B-KO**: typically 0.55–0.65 — catastrophic, attribution lost

Tighten these prior bounds when wet-lab data arrive. The substrate's calibration pipeline (isotonic regression / histogram binning) must update them post-hoc.

### 1.6 Proximity-of-mechanism principle

Confidence within a tissue/cascade tracks the **number of causal mediators between the perturbation and the measured phenotype**:

| Mediadores | Example (pronefro) | Expected confianza |
|---|---|---|
| 0 (direct) | actomiosina → constricción apical → lumen (Etapa 3) | ~0.82 |
| 2 (indirect) | actomiosina → intercalación → IM elongado → fenotipo (Etapa 2) | ~0.80 |
| 3+ (deeply indirect) | actomiosina → C-E → posicionamiento LPM → IM → fenotipo (Etapa 1) | ~0.78 |

When designing a cascade for a new tissue:
1. Identify which window has the mechanism most proximal to the terminal phenotype.
2. Predict that window will yield cleanest causal signal.
3. Prioritize wet-lab validation accordingly.

---

## §2 The decouple paradigm

Every scenario gets scored on the **morphology-vs-identity test**.

### 2.1 The test

> Does the perturbation alter morphology *without* altering identity-defining transcripts?

This is the operational definition of a "morphological ablation". A perturbation that scrambles identity is not a morphological ablation — it's a developmental defect of specification.

### 2.2 Scoring rubric

**PASA — identity preserved, morphology altered**

- Identity bulk RNA-seq: indistinguishable from control
- Spatial identity markers: present in correct cells (may be in wrong spatial positions — that *is* the morphological defect)
- Morphology: clearly altered (dislocación / compresión / arquitectura rota)
- Reading: ablation is morphologically pure ✓

Examples in pronefro cascade: 1A-hipo, 2A-hipo, 3A-hipo, 3A-KO. The cleanest is **3B-KO**: identity transcriptionally pristine, morphology completely abolished — *control positivo del paradigma*.

**PARCIAL — identity transcriptionally attenuated, identity preserved**

- Identity bulk RNA-seq: normal levels
- Mechanical/stress-response transcripts: persistently altered (sostenido↑ stress, sostenido↓ YAP)
- Apical/MET-related transcripts (if relevant): suppressed or delayed
- Reading: ablation has secondary effects on transcription beyond pure morphology

Examples: 1B-hipo, 2B-hipo, 3B-hipo (all persistent hipomorfos).

**FALLA — identity markers corrupted**

- Identity bulk RNA-seq: depleted, chaotic, or fragmented
- Reading: ablation contaminates upstream specification programs; this is no longer a morphological ablation

Examples: 1B-KO (early window + persistent + catastrophic combo). When you see this signature, flag in the scenario's `gap_flags` explicitly.

### 2.3 When the paradigm fails

The paradigm holds for:
- Hipomorfo at any mode
- KO Mode A at any stage
- KO Mode B at later stages (post-specification)

The paradigm fails for:
- KO Mode B applied during early specification windows

Reason: persistent catastrophic perturbation destroys not only morphology but also the upstream regulatory programs that establish identity. The 1B-KO signature is the canonical example.

When the paradigm fails for a scenario, report it as evidence of *scope limit* — not as evidence against the cascade hypothesis. The scenario simply lies outside the conditions where "morphological ablation" is meaningful.

### 2.4 Transcriptome readout predictions per scenario

Per scenario, predict in **three categories**:

**Should remain unchanged** (purity controls)

- Identity markers expected to persist
  - For pronefro mesendodermo: `gsc, ntl/tbxta, sox17, eve1`
  - For pronefro IM: `pax2a, lhx1a, wt1a, hand2`
  - For pronefro túbulo: `cdh17, pax2a, wt1a`
- Pathway machinery NOT regulated by the perturbed mechanism (e.g., PCP molecular components are not regulated by contractility — they may be downstream-affected functionally but not transcriptionally)

**Should change transiently** (mechanical signature)

- Stress response: `fos, jun, egr1, hspa` ↑ during ablation
- YAP/TAZ targets: `ctgf/ccn2, cyr61/ccn1, ankrd1` ↓ during ablation (less cortical tension)
- Recovery after Mode A washout; sostenido in Mode B

**Should show spatial dislocation without level change** (morphological signature)

- Identity markers present in **wrong spatial positions** — bulk levels normal, spatial distribution altered
- **Requires spatial transcriptomics or HCR-FISH cuantitativa to detect** — bulk RNA-seq INSUFFICIENT

State the resolution requirement explicitly in the report. Most cascades require spatial transcriptomics for full validation.

---

## §3 Cross-stage synthesis (when ≥2 stages)

When the cascade involves 2+ stages, the report MUST include the following components.

### 3.1 Cross-stage comparison table

Minimum 8 rows comparing dimensions across stages:

| Dimension (recommended) |
|---|
| Evento mecánico dominante |
| Tipo de defecto en Modo A hipo |
| Tipo de defecto en Modo A KO |
| Mecanismo causal (directo / indirecto + mediadores) |
| Identidad transcripcional en Modo A |
| Identidad bajo KO Modo B (preserve / pierde) |
| Confianza ventana óptima |
| Resolución validación transcriptómica requerida |

Color-code stage columns for visual clarity (e.g., stage 1 orange, stage 2 purple, stage 3 cyan).

### 3.2 Proximity-of-mechanism analysis

Render as a confidence ladder. For each stage, show the causal chain and the number of mediadores:

```
Etapa 1: actomiosina → C-E → posicionamiento LPM → IM → pronefro    [3 mediadores]  conf 0.78
Etapa 2: actomiosina → intercalación PCP → IM elongado → pronefro   [2 mediadores]  conf 0.80
Etapa 3: actomiosina → constricción apical → lumen pronéfrico        [0 mediadores]  conf 0.82
```

The confidence escalation is *predicted* by the principle — and should be a *consistency check* on the simulation: if confidences don't track mediadores, something is mis-calibrated.

### 3.3 Main finding callout

Name the **qualitative divergence**:

- Are the stage phenotypes *qualitatively distinct* (= multi-stage causality hypothesis supported)?
- Or *graduated* (= single mechanism with intensity differences only — null hypothesis)?

The qualitative divergence claim is the stronger finding. State it explicitly in a prominent callout. If observed, this is the central output of the cascade.

### 3.4 Decouple paradigm tabular summary

Score all scenarios. Highlight:
- The cleanest decouple — typically KO Mode B from the latest stage (control positivo del paradigma)
- The decouple failure(s) — typically early + persistent + catastrophic (e.g., 1B-KO style)

Provide a single-paragraph reading of the paradigm at the cascade level.

### 3.5 Validation wet-lab priorities

Numbered list, ordered by:

1. Confidence (highest first)
2. Mechanistic proximity (directo > indirecto)
3. Detectability with available techniques
4. Cost / feasibility (note explicitly when relevant)

For each priority, state:
- What scenario to validate
- Why this one first
- Required technique (microscopy modality + transcriptomic resolution)
- Expected outcome if hypothesis correct

### 3.6 Closure document

After 3+ stages completed, generate `cierre-<topic>-completa.html` consolidating:

- TL;DR (1 paragraph executive summary)
- Three (or N) signature fenotípicas as visual cards
- Cross-stage table
- Proximity-of-mechanism analysis
- Decouple paradigm consolidated
- Validation priorities
- Calibration breakdown per scenario
- Aggregated limits
- Siguientes pasos (with substrate-value and composite-auditor recommendations)

This is the document to share with stakeholders (co-fundadores, partners). Per-stage HTMLs remain for depth.

### 3.7 Version discipline

When adding stages to an existing cascade:

- **Per-stage HTMLs**: never modify existing. Add new `etapaN-conclusion.html` for the new stage.
- **Visualizations**: never modify existing v1 files. Create v2, v3, etc.
- **Closure**: regenerate `cierre-*.html`; can overwrite if it has no version suffix yet, otherwise add v2.

Reason: user explicitly wanted versions to coexist so differences are visible. This is non-negotiable per the hard rules in SKILL.md §10.
