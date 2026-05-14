---
name: causal-ablation-cascade-sim
description: "Simulate causal ablation cascades over developmental sequences (default: zebrafish pronephros Fase I; extensible to córnea, mouse, otros tejidos in later phases) and produce TWO SEPARATE deliverables per invocation: (1) HTML quantitative report with structured output per scenario applying the substrate-evidence contract, and (2) HTML interactive 4D visualization built on Three.js. The numerical results live in the report; the simulación visual lives in the viz. Never embed one in the other. Use when user says: 'simular ablaciones causales', 'simulate causal ablations', 'cascade simulation', 'multi-stage perturbation', 'simular cascada de perturbaciones'; when user describes a morphogenetic process and wants to test which stages contribute causally to a final phenotype; when user wants both numerical AND visual outputs from one analysis. Default protocol per stage: 4 scenarios (Mode A stage-specific washout × Mode B persistent) × (hipomorfo ~50% × KO ~95%). Default framework: Self-Consistency Tier 1, self-reported per CLAUDE.md v2.2. All outputs are causal-pruner type — require human gate downstream (CLAUDE.md §7). Bilingüe: español o inglés según el usuario."
---

# Causal Ablation Cascade Simulation

Run simulated causal ablation cascades on developmental processes and produce **two artifacts**, **as separate files**, every invocation:

1. **HTML quantitative report** — structured output per scenario with the substrate-evidence contract (CLAUDE.md §5).
2. **HTML interactive 4D visualization** — built on `morpheus-4d-viz` substrate, customized for the cascade analyzed.

The numerical results live in the report; the simulación visual lives in the viz. **Do not embed one in the other** — the user explicitly wants both available independently for cross-reference and so versions stay comparable.

Bilingual: respond in the user's language.

---

## 1. When to use

- User says "simular ablaciones causales" / "simulate causal ablations" / "cascade simulation" / "perturbación multi-etapa"
- User describes a morphogenetic process and wants to test stage-specific causal contributions
- User wants BOTH quantitative report AND interactive visualization from one analysis
- Continuation of an existing cascade (add stages, new perturbation type, refined viz)

## 2. When NOT to use

| If the request is | Use instead |
|---|---|
| Pure 3D viz without analytical structure | `morpheus-4d-viz` |
| Pure research / agent design without simulation | `organogenesis-agent-architect` |
| Single biology factoid | `tooluniverse` skill |
| Wet-lab experimental plan (not in silico) | Method 2 manual workflow + organogenesis-agent-architect |

---

## 3. Operating mode

Default = **Method 2 (humano-conducido)** per CLAUDE.md §2. If the user has not specified, **ASK** before running multi-stage work. Use `AskUserQuestion` to clarify:

1. Method (1 or 2)
2. Process / tissue (default zebrafish pronephros in Fase I)
3. Stages to perturb (one, multiple, cascade completa)
4. Perturbation type (signaling? cellular mechanics? gene? other?)
5. Starting cell type / developmental window

Do not infer scope — ask.

---

## 4. The 4-scenario protocol (per stage)

For each developmental stage being perturbed, run **exactly 4 scenarios**. This is "máxima probabilidad de éxito" — calibrated for causal inference quality, not minimum cost.

| Code | Mode | Dose | Causal value |
|---|---|---|---|
| **{N}A-hipo** | A (stage-specific, washout) | ~50% | **Highest — cleanest stage-specific signal** |
| **{N}A-KO**   | A (stage-specific, washout) | ~95% | High — strong fenotipo, more variance |
| **{N}B-hipo** | B (persistent)              | ~50% | Reference only — confounded with cascade |
| **{N}B-KO**   | B (persistent)              | ~95% | Control positive of extreme OR catastrophic confounder |

Where `{N}` is the stage number.

**Why exactly 4**: Mode A vs Mode B at same dose distinguishes stage-specific causality from cascade. Hipo vs KO maps the dose-fenotipo curve. Together, the 4 mitigate Gate 4 (parsimonia) without eliminating it. Fewer scenarios = ambiguous attribution; more scenarios = marginal gain for substantial tracking cost.

Full rationale and confidence calibration heuristics: `references/protocol-and-decouple.md` §1.

---

## 5. The decouple paradigm

Every scenario gets scored on the **morphology-vs-identity test**:

- **PASA**: identity transcripts preserved + morphology altered → ablation is morphologically pure
- **PARCIAL**: identity transcriptionally attenuated but identity preserved → confounded
- **FALLA**: identity markers corrupted → ablation contaminates specification

This is what distinguishes a *true morphological ablation* from a *developmental defect of identity*. The paradigm typically fails for: KO Mode B during early specification windows (e.g., 1B-KO in pronefro). Flag explicitly.

Scoring rubric and transcriptomic readout predictions: `references/protocol-and-decouple.md` §2.

---

## 6. Output contract (per scenario)

Each scenario produces a structured block:

```yaml
direct_answer: <prediction of phenotype>
confidence: <0..1>
evidence_cited: [<lit reference>, ...]
alternatives_considered: [<alt hypothesis>, ...]
gap_flags: [<known unknown>, ...]
framework_applied: "Self-Consistency (Tier 1, self-reported)"
transcriptome_validation_predicted:
  during_ablation: { ... }
  post_washout: { ... }      # Mode A only
  decouple_test: PASA | PARCIAL | FALLA
```

`framework_applied` is **self-report, not introspection** (CLAUDE.md v2.2). The label describes prompt-time strategy, not verified internal reasoning. Substrate calibration pipelines must apply isotonic regression / histogram binning post-hoc before treating these confidences as calibrated probabilities.

---

## 7. Deliverable 1 — HTML quantitative report

Save to:
- Single stage: `reports/<topic>-<stage-short>-conclusion.html` (e.g., `etapa1-mesendodermo-conclusion.html`)
- Multi-stage closure: `reports/cierre-<topic>-completa.html`

Required sections (full structure + CSS template in `references/deliverables-spec.md` §1):

1. Header + meta + gate notice
2. TL;DR (when ≥2 stages)
3. Context y pregunta
4. Diseño (tabla)
5. Resultados por escenario (color-coded blocks)
6. Síntesis comparativa
7. Comparación cruzada (when ≥2 stages — **mandatory**)
8. Hallazgo principal (callout)
9. Test de desacople consolidado
10. Validación wet-lab · prioridades
11. Calibración de confianza
12. Límites e incertidumbres
13. Siguientes pasos
14. Footer with cross-references

Canonical example: `reports/cierre-cascada-completa.html`.

---

## 8. Deliverable 2 — HTML 4D visualization

Save to:
- Single-scenario: `reports/visualizacion-<topic>-<variant>.html`
- Comparison: `reports/visualizacion-comparacion-<topic>-<variant>.html`

Version suffix `-v2`, `-v3` when scenarios are added to an existing cascade — **do not modify previous viz files** so users can compare versions.

Required features (Three.js architecture + perturbation logic in `references/deliverables-spec.md` §2):

- 3D embryo body deforming through developmental time
- Cell instancing (60+ cells/side; adjust per tissue)
- Scenario picker grouped by stage with color-coded headers
- Ablation window markers on timeline (Mode A: start + washout; Mode B: extended band)
- Decouple paradigm **visible**: cells colored by identity (fate) even when perturbation displaces them — this IS the visual evidence of decouple
- Per-scenario confidence + decouple pill + ablation activity tag
- Gate notice (always present)
- Auto-rotate camera + orbit controls + timeline scrubbing
- Two variants supported per cascade:
  - **single-scenario** — full info panel, scenario picker
  - **comparison side-by-side** — 2/3/4 synced viewports with shared camera/timeline

Canonical examples: `reports/visualizacion-cascada-pronefro-v2.html`, `reports/visualizacion-comparacion-pronefro-v2.html`.

---

## 9. Cross-stage synthesis (when ≥2 stages)

The report MUST include:

1. **Cross-stage comparison table** with ≥8 rows (mecanismo, tipo de defecto Mode A, identidad bajo Mode B, confianza, mediadores, resolución validación, etc.)
2. **Proximity-of-mechanism analysis** — confidence ladder (fewer mediadores → higher confianza)
3. **Main finding callout** — name the *qualitative divergence* between stages (not graduated phenotype)
4. **Decouple paradigm tabular summary** — score all scenarios, highlight cleanest decouple ("control positivo del paradigma") and any decouple failures
5. **Validation wet-lab priorities** — numbered list ordered by confidence + mechanistic proximity + detectability

After 3+ stages completed, produce `cierre-<topic>-completa.html` consolidated artifact (TL;DR-readable for stakeholders). The per-stage HTMLs remain for depth.

Full guidance: `references/protocol-and-decouple.md` §3.

---

## 10. Hard rules (non-negotiable)

- **Both deliverables in separate files. Every invocation. No exceptions.** This is the user's stated invariant.
- Output is `causal-pruner` evidence → puerta humana before downstream use (CLAUDE.md §7).
- `framework_applied` is self-report (v2.2). Do not claim verified reasoning.
- Cross-stage comparison is **mandatory** when ≥2 stages run.
- Each scenario is its own evidence unit. Do not collapse multiple scenarios into a single "average".
- Identity transcriptome predictions are **validation only**, never driver of causal claims.
- Mode B scenarios are reference / contrast only — never as evidence causal aislada.
- 1B-KO style (early + persistent + catastrophic) typically fails decouple — flag explicitly when it occurs.
- Adding to an existing cascade: **never modify prior reports/* or viz files**. Create new `etapaN-conclusion.html`, regenerate `cierre-*.html`, create `*-v2.html` for viz. Preserves comparability.
- Method 2 default. If multi-stage cascade and user has not specified method, ASK.

---

## 11. Workflow

1. **Clarify scope** — `AskUserQuestion` if not specified (method, tissue, stages, perturbation type, starting cell)
2. **Design** — pick stages, perturbation, windows; state hypothesis to test
3. **Execute one stage** — 4 scenarios in YAML format in chat reply
4. **Synthesize one stage** — synthesis table + decouple scoring per scenario in chat
5. **Pause** — user reviews, says continue / refine / next stage
6. **Repeat** for each stage
7. **Closure** — when cascade complete or stopping, produce `cierre-*.html`
8. **Visualize** — single-scenario + comparison HTML viz with all scenarios from the cascade
9. **Hand off** — gate notice, validation priorities, next steps; offer subsequent options

Each chat-side scenario block in step 3 follows the output contract (§6). The HTML deliverables in steps 7–8 are only produced when the user signals they want them — typically after completing a stage or the full cascade.

---

## 12. Canonical worked example

The Fase I zebrafish pronephros cascade (Etapas 1, 2, 3 — 12 scenarios + cierre + 2 visualizaciones) is the reference implementation. Files in `reports/`:

| File | Purpose |
|---|---|
| `etapa1-mesendodermo-conclusion.html` | Etapa 1 standalone report (Modo A/B × hipo/KO) |
| `etapa2-im-conclusion.html` | Etapa 2 standalone + cross-stage vs Etapa 1 |
| `cierre-cascada-completa.html` | Three-stage consolidated closure with TL;DR, signature cards, validation priorities |
| `visualizacion-cascada-pronefro-v2.html` | Single-scenario viz, 13 scenarios grouped by stage |
| `visualizacion-comparacion-pronefro-v2.html` | Side-by-side viz, 2/3/4 panels with cascade defaults |

When format is unclear, **match these files**. The v1 visualizations (9 scenarios, Etapas 1+2 only) are preserved for version comparison.

Biology specifics for Fase I (markers, mechanical events, transcriptome readouts): `references/zebrafish-pronefro-domain.md`.

---

## 13. Reference files

| File | Read when |
|---|---|
| `references/protocol-and-decouple.md` | Designing scenarios · applying decouple test · cross-stage synthesis |
| `references/deliverables-spec.md` | Generating the report HTML · generating the viz HTML · perturbation logic |
| `references/zebrafish-pronefro-domain.md` | Fase I biology — markers, stages, mechanical events |

Read selectively. Do not read all references every invocation.

---

## 14. Skill connections

- **Upstream**: `organogenesis-agent-architect` may design agent systems that include a cascade simulation as one workstream. That architect's output should reference *this* skill explicitly.
- **Substrate**: `morpheus-4d-viz` provides the Three.js rendering foundation; this skill extends it with multi-scenario logic, perturbation behaviors, and the decouple-paradigm-visible coloring.
- **Adjacent**: `tooluniverse` for biology lookups when `evidence_cited` needs grounding in primary literature.

---

## 15. Footer

- v1.0 · 2026-05-12
- Synchronized with `organogenesis-agent-architect@2.2.0` and `morpheus-4d-viz`
- Output contract per CLAUDE.md §5 v2.2 (self-report `framework_applied`)
- Fase I scope: zebrafish pronephros · Fase II/III: córnea + otros tejidos via partner field selection
- The Fase I pronephros cascade is the first calibration test case for the sustrato Witt
