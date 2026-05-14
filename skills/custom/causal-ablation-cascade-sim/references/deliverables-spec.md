# Deliverables Specification

Both deliverables are HTML files, **always separate**. Canonical examples in `reports/`:

- Report: `reports/cierre-cascada-completa.html` (multi-stage closure) or `reports/etapa1-mesendodermo-conclusion.html` (single stage)
- Single-scenario viz: `reports/visualizacion-cascada-pronefro-v2.html`
- Comparison viz: `reports/visualizacion-comparacion-pronefro-v2.html`

When in doubt about format, **match these files**. They are the reference implementation.

---

## §1 HTML Quantitative Report

### 1.1 File path convention

| Type | Path |
|---|---|
| Single stage | `reports/<topic>-<stage-short>-conclusion.html` |
| Multi-stage closure | `reports/cierre-<topic>-completa.html` |

Example: `reports/etapa1-mesendodermo-conclusion.html`, `reports/cierre-cascada-completa.html`.

### 1.2 Visual identity

Reuse the same CSS custom properties across all reports of a cascade for visual continuity. Key colors:

```css
:root {
  --bg: #fafaf8;           /* background */
  --surface: #ffffff;       /* card / panel */
  --ink: #1a1a1a;          /* primary text */
  --ink-soft: #4a4a4a;      /* secondary text */
  --ink-faint: #777;        /* tertiary text */
  --rule: #e4e2dd;          /* borders */
  --accent: #5a4a3a;        /* warm brown — section accents */
  --accent-soft: #f3efe8;
  --pass: #2d6a4f;          /* status: pass */
  --warn: #b8860b;          /* status: warn */
  --fail: #8b3a3a;          /* status: fail */
  --stage1: #D4724E;        /* orange */
  --stage2: #9B5A8A;        /* purple */
  --stage3: #4A8FA5;        /* cyan */
  --cross: #3a4a6a;         /* cross-cascade callout */
  --cross-soft: #eef1f7;
}
```

Font: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif` for body; `ui-monospace, SFMono-Regular, Menlo, monospace` for code blocks.

Max width: 880–920px centered. Padding: `48px 32px 96px`.

### 1.3 Required structure

```
<header.title>
  <div.eyebrow>"Proyecto Organogenesis × Witt · ..."</div>
  <h1>Clear title</h1>
  <p.subtitle>Subtitle</p>
  <dl.meta>Fecha · Modo · Marco · Nichos · Fase · Estado · etc.</dl>
</header>

<div.gate>Puerta humana obligatoria notice (always)</div>

<div.tldr>           <!-- only when ≥2 stages -->
  TL;DR label + 1-paragraph executive summary
</div>

<div.toc>            <!-- recommended -->
  Numbered TOC with anchor links
</div>

<section id="contexto">       Context y pregunta
<section id="diseno">          Diseño table
<section id="escenarios">      Scenarios (color-coded blocks per stage)
<section id="sintesis">        Síntesis comparativa table
<section id="cruzada">         Cross-stage comparison (≥2 stages — mandatory)
<section id="hallazgo">        Hallazgo principal (callout.finding)
<section id="desacople">       Test de desacople consolidado (≥2 stages)
<section id="validacion">      Validación wet-lab · prioridades (priority-list)
<section id="calibracion">     Calibración de confianza (conf-grid)
<section id="limites">         Límites e incertidumbres (ul.flags)
<section id="siguiente">       Siguientes pasos (priority-list)

<footer>
  Generated date
  Links to sibling reports
  Contract reference
  Status
  Source disclaimer
</footer>
```

### 1.4 Scenario block formats

**Per-stage report** (e.g., `etapa1-mesendodermo-conclusion.html`):

Render each scenario as a YAML-like code block plus the `gap_flags` list:

```
1A-hipo · stage-specific, hipomorfo (washout)
[YAML block with direct_answer, confidence, transcriptome_validation_predicted, alternatives_considered, gap_flags, framework_applied]
```

Border-left color: `--pass` (best), `--warn` (confounded), `--fail` (catastrophic).

**Closure document** (e.g., `cierre-cascada-completa.html`):

Render the *signature* of each stage as a card (grid of 3 for 3 stages):

```
<div.signature-card.stage{N}>
  <div.signature-stage>Etapa N · X–Y hpf</div>
  <div.signature-name>DISLOCACIÓN | COMPRESIÓN | FALLA DE PARED</div>
  <div.signature-aspect>Defecto de POSITION | FORMA | ARQUITECTURA</div>
  <div.signature-desc>1-paragraph description</div>
  <div.signature-mech>Mechanism with mediadores count</div>
  <div.signature-conf>Confianza NA-hipo: X.XX</div>
</div>
```

### 1.5 Mandatory elements per report

- Gate notice at top
- `framework_applied` self-report disclaimer in footer
- Each scenario contains all 6 fields of the output contract
- `gap_flags` is conspicuous (not hidden)
- `transcriptome_validation_predicted` separates *during ablation*, *post washout (Mode A)*, and *decouple test result*
- Cross-stage table when ≥2 stages
- Validation priorities listed when ≥2 stages

---

## §2 HTML Interactive 4D Visualization

Built on `morpheus-4d-viz` skill (Three.js + OrbitControls). Adapts the boilerplate with multi-scenario extensions.

### 2.1 File path convention

| Variant | Path |
|---|---|
| Single-scenario | `reports/visualizacion-<topic>-<variant>.html` |
| Comparison side-by-side | `reports/visualizacion-comparacion-<topic>-<variant>.html` |
| Versioning | suffix `-v2`, `-v3`, etc. when scenarios added |

Example: `reports/visualizacion-cascada-pronefro-v2.html`, `reports/visualizacion-comparacion-pronefro-v2.html`.

### 2.2 SCENARIOS data structure

```javascript
const SCENARIOS = {
  'control': {
    label: 'Control (WT)',
    etapa: 0,
    ablationWindow: null,      // [tStart, tEnd] or null
    ablationMode: null,         // 'A' | 'B' | null
    dose: 0,                    // 0..1
    confidence: 1.00,
    decouple: 'na',             // 'pass' | 'partial' | 'fail' | 'na'
    decoupleLabel: 'N/A',
    pheno: '<one-sentence phenotype>',
    tx: {                       // transcriptomic signature
      identity: 'normal',
      stress: 'baseline',
      yap: 'baseline'
    },
  },
  '{N}A-hipo': {
    label: '{N}A · stage-specific · hipo',
    etapa: {N},
    ablationWindow: [<tStart>, <tEnd>],
    ablationMode: 'A',
    dose: 0.50,
    confidence: <value>,
    decouple: 'pass',
    decoupleLabel: 'PASA',
    pheno: '<one-sentence>',
    tx: { ... },
  },
  // ... etc for all scenarios
};
```

Group in `SCENARIO_GROUPS` for UI rendering:

```javascript
const SCENARIO_GROUPS = {
  'Referencia':       ['control'],
  'Etapa 1 (...)':    ['1A-hipo','1A-KO','1B-hipo','1B-KO'],
  'Etapa 2 (...)':    ['2A-hipo','2A-KO','2B-hipo','2B-KO'],
  'Etapa 3 (...)':    ['3A-hipo','3A-KO','3B-hipo','3B-KO'],
};
```

### 2.3 Time normalization

Internal `t ∈ [0, 1]` maps to biological time via:

```javascript
function tToHpf(t) { return (3 + t * 21).toFixed(1); }  // zebrafish 3–24 hpf
```

Adjust the constants for other tissues.

For zebrafish pronephros, the stage windows on the normalized timeline:

| Stage | t window | hpf |
|---|---|---|
| Blástula | [0.00, 0.13] | 3–6 |
| Gastrul · mesendodermo | [0.13, 0.30] | 6–10 |
| LPM/IM | [0.30, 0.50] | 10–14 |
| MET · pre-tubulogénesis | [0.50, 0.72] | 14–18 |
| Túbulo · lumenogénesis | [0.72, 1.00] | 18–24 |

Canonical ablation windows for the pronephros cascade:

| Etapa | t window | hpf |
|---|---|---|
| 1 (mesendodermo) | [0.13, 0.27] | 6–8 |
| 2 (LPM/IM) | [0.32, 0.46] | 10–12 |
| 3 (pre-MET) | [0.52, 0.62] | 14–16 |

### 2.4 Perturbation logic (the engineering)

Three signature behaviors implemented in `computeCellPosition(cellId, t, scenario)`. The function classifies the scenario by ablation window start:

```javascript
const isStage1 = wStart < 0.25;
const isStage2 = wStart >= 0.25 && wStart < 0.50;
const isStage3 = wStart >= 0.50;
```

Each stage gets a distinct geometric signature on the cells.

**Stage 1 → DISLOCATION** (positional scatter, possible asymmetric flip)

```javascript
posX += rand_offset * perturbStrength * 0.45;
posY += rand_offset * perturbStrength * 0.20;
posZ += rand_offset * perturbStrength * 0.55;
if (perturbStrength > 0.6 && random() < 0.18) posX *= -0.6;  // asymmetric flip for high dose
```

Catastrophic 1B-KO adds heavy isotropic chaos when `dose > 0.9 && mode === 'B'`.

**Stage 2 → COMPRESSION** (AP-axis scaling, cluster formation for KO)

```javascript
posZ *= (1.0 - perturbStrength * 0.55);  // compress AP
if (dose > 0.8) {
  posZ *= 0.6;                            // tighter compression for KO
  posX *= (1.0 - perturbStrength * 0.15);
  // small jitter for cluster formation
}
```

**Stage 3 → LUMEN/WALL FAILURE** (three sub-modes by dose × mode)

```javascript
const isPersistent = scenario.ablationMode === 'B';
const isKO = dose > 0.8;

if (isPersistent && isKO) {
  // 3B-KO: AMORPHOUS MASS — cells pulled to center with heavy chaos
  posZ *= (1 - perturbStrength * 0.45);   // pull to center
  posX += rand_offset * perturbStrength * 0.35;
  posY += rand_offset * perturbStrength * 0.25;
  posZ += rand_offset * perturbStrength * 0.30;
} else if (isKO) {
  // 3A-KO: SWISS CHEESE — clusters along AP
  const clusterId = Math.floor(apIndex / 8);  // ~7 clusters per side
  const clusterCenterZ = (clusterIndex_normalized) * apFactor;
  posZ = posZ * (1 - perturbStrength * 0.55) + clusterCenterZ * perturbStrength * 0.55;
  // small intra-cluster jitter
} else {
  // 3A-hipo / 3B-hipo: BUMPY WALL — slight radial disorganization + outward expansion
  posX += rand_offset * perturbStrength * 0.22;
  posY += rand_offset * perturbStrength * 0.16;
  posX *= 1.0 + perturbStrength * 0.14;
}
```

### 2.5 Mode A vs Mode B residual strength

Post-ablation residual strength (when `t > wEnd` in Mode A):

```javascript
if (isStage1) perturbStrength = dose * 0.35;  // dislocation partially set, recovery
if (isStage2) perturbStrength = dose * 0.55;  // compression partially permanent
if (isStage3) perturbStrength = dose * 0.75;  // lumen damage permanent
```

The escalation reflects the proximity-of-mechanism principle: later stages have less recovery potential because the damage is more proximal to the terminal phenotype.

Mode B persistent: `perturbStrength = dose * 0.75` from window start onwards (slight adaptation factor).

### 2.6 Color rules

Identity (fate) colors progress over time **independently of perturbation**:

```javascript
const COL_MESODERM   = new THREE.Color(0xD6856B);
const COL_IM         = new THREE.Color(0xD4724E);
const COL_PROGENITOR = new THREE.Color(0x9B5A8A);
const COL_TUBULE     = new THREE.Color(0x4A8FA5);

function fateColor(t) {
  if (t < 0.20) return COL_MESODERM;
  if (t < 0.42) return lerp(MESODERM, IM, (t - 0.20) / 0.22);
  if (t < 0.58) return lerp(IM, PROGENITOR, (t - 0.42) / 0.16);
  return lerp(PROGENITOR, TUBULE, min(1, (t - 0.58) / 0.20));
}
```

During the ablation window, cells lerp 45% toward `COL_PERTURB = 0xE63946` (red). After window, they revert to fate color. This visualizes the decouple: cells maintain identity-colored fate even when their positions are scrambled.

### 2.7 UI panels

**Single-scenario viz**:
- Top HUD: title, version pill, time, stage, scenario, ablation status (lights up red when active)
- Left panel: scenario picker, grouped by stage with color-coded headers (orange/purple/cyan)
- Right panel: stage bar, confidence + bar, decouple tag (pass/partial/fail), phenotype text, transcriptomic signature line
- Bottom: timeline with ablation markers + play/pause button
- Floating: gate notice

**Comparison viz**:
- Same top HUD + layout switcher (2/3/4 panels)
- Per panel: scenario dropdown using `<optgroup>` for stage grouping, stage pill, confidence pill + decouple pill + ablation tag, phenotype text (2 lines max)
- Shared bottom: timeline with per-panel ablation bands stacked vertically
- Shared camera: all viewports show the same orbit angle

### 2.8 Default panel layouts (comparison viz)

```javascript
const DEFAULT_SCENARIOS = {
  2: ['control', '<latest A-hipo>'],            // ref + endpoint
  3: ['1A-hipo', '2A-hipo', '3A-hipo'],          // cascade signatures
  4: ['control', '1A-hipo', '2A-hipo', '3A-hipo'], // ref + cascade
};
```

When user switches N panels, reset to defaults for the new N. User can then change individual panel scenarios via dropdown.

### 2.9 Camera + controls

- Position: `(2.8, 1.6, 3.2)` — oblique dorso-lateral, both LPM stripes visible
- Auto-rotate: yes, ~0.4 rad/sec
- Damping: 0.06
- Timeline scrubbing pauses playback
- Keyboard: Space = play/pause, Arrow = ±10 frames, R = reset

### 2.10 Performance budget

- Vertex count ≤ 10K total per panel (embryo body ~2048 + cells 120 × 8 ≈ 3000 vertices)
- Frame rate target 60fps
- Single renderer, multi-viewport for comparison (`setViewport` + `setScissor` per panel)
- Shared geometry between panels (deform once per frame)

### 2.11 Gate notice in viz

Always include a floating div: "Hipótesis-generación · puerta humana antes de uso aguas abajo (CLAUDE.md §7)". Position at bottom-center above timeline.

### 2.12 Extending to new stages or tissues

When adding a new stage:
1. Add scenario entries to `SCENARIOS` with new ablation window
2. Add the new stage's stage-class to `SCENARIO_GROUPS`
3. Extend `computeCellPosition` with the new stage's signature behavior
4. Update `DEFAULT_SCENARIOS` to showcase the cascade
5. Save as new versioned file (`-v3.html`)

When adapting to a new tissue:
1. Replace `tToHpf` constants for that tissue's timeline
2. Redesign cell migration trajectories (`lateralFactor`, `apFactor`, `dorsalFactor` per t bucket)
3. Redesign embryo body deformation to match tissue morphogenesis
4. Update color palette if different fate categories
5. Redesign perturbation signatures based on the mechanical events specific to that tissue
