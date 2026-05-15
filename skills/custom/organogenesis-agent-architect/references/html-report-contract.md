# HTML report contract

> **When to read this file:** when emitting an HTML report at conclusion / checkpoint of any analytical work that produces substrate evidence. This is the canonical structure spec for the 4 report TYPES the project produces. Authority per ADR-0007 (2026-05-14, Accepted) + CLAUDE.md §5/§7/§11 v2.5.
>
> **Companion to:** `substrate-evidence-guide.md` (defines WHAT the §5 contract requires); this file (defines HOW to render it as HTML).
>
> **Last updated:** 2026-05-14 · v1.0 initial release alongside ADR-0007.

---

## §1 · Why this file exists

CLAUDE.md §5 v2.5 mandates that every conclusion / checkpoint of substrate-evidence-producing work emit a self-contained HTML report. The HTML IS the audit trail — pure markdown / JSON does not satisfy this requirement for substrate-evidence outputs.

The project has organically produced 4 TYPES of HTML reports through May 2026. This file formalizes that practice. It does NOT invent new structures — it codifies what works.

---

## §2 · The 4 TYPES

| TYPE | Purpose | Canonical exemplar |
|---|---|---|
| **A — Comprehensive analytical** | Full research answer with prose synthesis + structured evidence + claim records. Default for substantive analytical questions. | [`reports/SESION-COMPLETA-pronephros-proteomics-20260514.html`](../../../../reports/SESION-COMPLETA-pronephros-proteomics-20260514.html) |
| **B — Interactive viz grid** | Structured data display (candidates × dimensions, scenarios × verdict). Click-to-expand modals. | [`reports/proteoma-pronefro-viz-14candidates-v1.html`](../../../../reports/proteoma-pronefro-viz-14candidates-v1.html), [`reports/cascade-multi-candidate-pronefro-v1.html`](../../../../reports/cascade-multi-candidate-pronefro-v1.html) |
| **C — Simulation-backed Three.js** | 3D/4D scene with timeline scrubber. **MANDATORY when conclusion is simulation-backed (per §7 hard rule).** | [`reports/visualizacion-cascada-pronefro-v2.html`](../../../../reports/visualizacion-cascada-pronefro-v2.html), [`reports/visualizacion-comparacion-pronefro-v2.html`](../../../../reports/visualizacion-comparacion-pronefro-v2.html) |
| **D — Formal retrospective** | Session retrospective / meta-analysis / composite-audit. Light theme, stakeholder-ready. | [`docs/reports/2026-05-09_meta_analysis_session.html`](../../../../docs/reports/2026-05-09_meta_analysis_session.html) |

**Multiple TYPES may coexist for a single conclusion.** Common pattern: one TYPE A consolidated + one TYPE C viz cross-linked. Do NOT generate 4 parallel views of the same evidence (composite-audit 2026-05-14 AP-N9 flagged artifact proliferation as `prueba pequeño` violation).

---

## §3 · Mandatory sections (all TYPES)

Every conclusion HTML MUST include these 8 sections (visible UI, not buried in metadata):

| § | Section | Content |
|---|---|---|
| 1 | **Header** | Title, session ID/timestamp, framework_applied chip, confidence badge |
| 2 | **Executive summary** | `direct_answer` prose near top — 2-3 sentences max; TL;DR card pattern |
| 3 | **Methodology** | Framework with catalog citation `§<number>` (per §4 strengthen), `agents_invoked` summary box |
| 4 | **Evidence & results** | Tables, badges, color-coded callouts, embedded data — the analytical core |
| 5 | **Synthesis** | `alternatives_considered` as callout box or collapsed panel |
| 6 | **Limitations** | `gap_flags` as dedicated section; observable_at for unfalsified claims |
| 7 | **Validation roadmap / next steps** | Wet-lab priorities, follow-up questions, what would falsify the claim |
| 8 | **Footer** | Timestamp, references, links to raw cache, predecessor reports per ADR-0002, related artifacts |

---

## §4 · Visible §5 contract fields — required UI

Every CLAUDE.md §5 contract field must appear as readable UI in the HTML body (NOT only as metadata or hidden script):

| Field | UI element |
|---|---|
| `direct_answer` | Executive summary section §2 |
| `confidence` OR `confidence_by_subclaim` | Numeric badge OR gradient bar OR verbal pill (PASS/MODERATE/FAIL) at top; breakdown table if by-subclaim |
| `evidence_cited` | Hyperlinks in body + reference list in footer |
| `alternatives_considered` | Callout box or collapsed panel in §5 (synthesis) |
| `gap_flags` | §6 (limitations) section, bulleted |
| `framework_applied` | Header chip with catalog citation §<number>: "<quote>" |
| `agents_invoked` | Footer or appendix box listing agents engaged / skipped-ad-hoc / not-applicable |

---

## §5 · Visual elements

**Mandatory** (per element availability):
- **Tables** for structured data (candidates × windows, scenarios × verdict, claim records)
- **Color-coded badges** — status (DETECT, LoF, PARADIGM, etc.) and verdicts (PASA/PARCIAL/FALLA, PASS/MODERATE/FAIL, REDUN)
- **Confidence visualizations** — gradient bar OR numeric badge OR verbal pill
- **Callout boxes** — `.good`, `.warn`, `.bad`, `.paradigm` for semantic emphasis
- **Embedded data inline** — `<script>const X = [...]</script>` blocks; NEVER external files (reports are self-contained)

**Encouraged when applicable:**
- Charts — confidence trajectory line, ECE curve, candidate × window heatmap (use Canvas / SVG inline; NO external CDN)
- Modal dialogs for expanded detail (TYPE B/C pattern)
- TOC sidebar (TYPE A) or sticky top-nav (TYPE D)
- Stats grid dashboard (4-6 key numbers at top)
- Signature cards for closure patterns (per `cierre-cascada-completa.html`)
- Cross-links to predecessor reports per ADR-0002

**Prohibited:**
- External CDN dependencies (chart.js, jquery, fonts.googleapis.com) — reports MUST be self-contained for offline review
- External data files (`../data/x.json`) — embed inline
- Mixing dark + light themes in a single HTML — use `<iframe>` if dark viz must embed in light report

---

## §6 · CSS conventions

Two aesthetic families. Pick one per HTML; do NOT mix.

### Dark (noir) — TYPES A, B, C

```css
:root {
  --bg-deep: #0f172a;
  --bg-mid: #1e293b;
  --bg-card: #25314a;
  --border: #334155;
  --text-main: #e2e8f0;
  --text-dim: #94a3b8;
  --text-faint: #64748b;
  --text-bright: #f1f5f9;
  --accent: #38bdf8;
  --good: #16a34a;
  --warn: #f59e0b;
  --bad: #dc2626;
  --paradigm: #a855f7;
  --w1: #f59e0b;  /* mesendodermo / window 1 — amber */
  --w2: #3b82f6;  /* LPM/IM / window 2 — blue */
  --w3: #10b981;  /* MET / window 3 — green */
  --w4: #f43f5e;  /* lumenogénesis / window 4 — rose */
}
```

### Light (editorial) — TYPE D

```css
:root {
  --c-bg: #fafaf7;
  --c-surface: #ffffff;
  --c-border: #e5e3dd;
  --c-text: #1a1a1a;
  --c-muted: #5a5a5a;
  --c-witt: #1d4e6e;
  --c-organo: #3a6a3f;
  --c-warn: #8a5a00;
  --c-critical: #8a2a2a;
}
```

**Layout patterns:**
- TYPE A: fixed left sidebar TOC (280px) + main content (max 1100px)
- TYPE B: full-width, stats grid + legend bar + 4-column grid + modal
- TYPE C: full-viewport canvas + HUD top + left panel (250px) + right panel (295px) + timeline bottom
- TYPE D: sticky top-nav + centered main content (max 1100px)

**Font conventions:**
- Body: system fonts (`'Segoe UI', system-ui, -apple-system, sans-serif`)
- Code / accession / monospace: `'Cascadia Code', 'Consolas', monospace`
- TYPE D may use serif body (optional)

---

## §7 · Data embedding pattern

All data embedded inline in `<script>` tags as JS arrays of objects:

```html
<script>
const CANDIDATES = [
  { gene: 'pax2a', acc: 'Q90268', window: 2, ... },
  ...
];
const SCENARIOS = [
  { g: 'vangl2', a: 'Q8UVJ6', w: 1, s: [...] },
  ...
];
// Render functions read from these arrays; tables / cards / viz generated at DOMContentLoaded
</script>
```

**Never reference external `.json` files.** The HTML is the artifact; if it can't be opened in a browser offline, it's not a valid report.

---

## §8 · Naming convention + version preservation

Per ADR-0002 (version preservation rule):

| Naming pattern | When |
|---|---|
| `<topic>-<context>-v1.html` | First version of a report |
| `<topic>-<context>-v2.html` (NEW file) | Iterative version with new evidence — **NEVER modify v1** |
| `SESION-COMPLETA-<topic>-<YYYYMMDD>.html` | Session-level consolidated TYPE A report |
| `visualizacion-<topic>-vN.html` | Single-scenario TYPE C viz |
| `visualizacion-comparacion-<topic>-vN.html` | Side-by-side TYPE C viz |
| `cierre-<topic>-<phase>.html` | Closure / signature-cards TYPE A sub-pattern |
| `cross-verdict-<topic>-vN.html` | When ≥2 simulators support same conclusion |
| `<YYYY-MM-DD>_<topic>_retrospective.html` | TYPE D session retrospective |

**Skill-emitted naming** (kept stable per skill SKILL.md):
- `causal-ablation-cascade-sim` → `etapa<N>-<event>-conclusion.html` + `visualizacion-cascada-<topic>-vN.html`
- `squidiff-in-silico-gate` → `squidiff-gate-<slug>.html`
- `morpheus-4d-viz` → custom per invocation

---

## §9 · Simulation-backed rule (per §7 hard rule)

If `agents_invoked` includes ANY of the simulators below, OR the conclusion references their outputs, a TYPE C visualization IS MANDATORY:

| Simulator | Output | Required TYPE C |
|---|---|---|
| `morpheus-4d-viz` skill | 3D/4D developmental scene | YES — invoke the skill, include its HTML output |
| `causal-ablation-cascade-sim` skill | Cascade scenarios | YES — `visualizacion-cascada-<topic>-vN.html` |
| `squidiff-in-silico-gate` skill | Transcriptomic Mode 1/3 | YES — 5-panel Nature Methods HTML |
| BioDynaMo (external) | Agent-based cell sim | YES — pipe through morpheus-4d-viz |
| `sim-orchestrator` catalog agent | Runpod batches | YES — viz the batch results |
| Future / custom simulators | Any | YES — TYPE C HTML required |

**Static screenshot is NOT sufficient.** The visual must be self-contained and interactively explorable (scrub, click, orbit).

**Cross-verdict pattern (when ≥2 simulators support same conclusion):**
- One HTML showing the cross-verdict — e.g., Squidiff Mode 3 + Morpheus combined per `squidiff-in-silico-gate/references/morpheus-pairing.md`
- Naming: `cross-verdict-<topic>-vN.html` OR include in main TYPE A as embedded panel

---

## §10 · Trigger conditions (per CLAUDE.md §11 visual-offer reflex)

**TRIGGERS** (HTML emission required at end of work):
- Any output populating §5 contract (confidence + evidence + framework)
- User signals end-of-inquiry ("pausamos", "cerramos", "lo dejamos aquí", "ya")
- Phase or named checkpoint completes
- Substantive analytical question reaches direct_answer with confidence ≥ 0.5
- Composite audit / retrospective / session meta-analysis
- Claim record written (one per claim → one HTML linking the chain)

**EXEMPT** (HTML NOT required):
- Conversational responses without analytical claim
- Status updates
- Trivial file operations (ls, cat, format)
- Pure search / tool-use producing no substrate evidence
- Sub-tasks within larger session (only the conclusion at the end requires HTML)
- Plan mode planning (the plan file is the artifact)

---

## §11 · Visual-offer reflex format

After emitting the mandatory base HTML, the agent MUST ask ONE single-line question offering additional visual artifacts. Templates:

**If simulation-backed:**
> *"HTML base entregado. Adicionalmente quieres: (a) 3D Three.js scrubable de los escenarios, (b) side-by-side comparison de 2+ scenarios, (c) animated timeline, o (d) seguimos como está?"*

**If data-heavy (candidates / scenarios / records):**
> *"HTML base entregado. Adicionalmente quieres: (a) interactive grid viz (TYPE B), (b) heatmap candidates × dimensions, o (c) seguimos como está?"*

**If analytical synthesis only:**
> *"HTML base entregado (TYPE A comprehensive). ¿Quieres algún visual adicional como charts de confidence trajectory o tabla expanded de evidence? O seguimos como está."*

**If retrospective:**
> *"Retrospective HTML entregado (TYPE D formal). ¿Quieres además una versión summary (TYPE A) o seguimos como está?"*

**Opt-in additive.** User's "seguimos como está" closes the checkpoint. Skip is allowed but tracked in `agents_invoked` field with `status: skipped-ad-hoc` and reason.

**Persistence within session:** if user declines extra viz for a topic, do NOT re-ask for the same conclusion. Re-ask is permitted when the conclusion changes (e.g., new evidence arrives, version bump).

---

## §12 · Skill-level HTML mandates (pre-existing, governed by their own SKILL.md)

These skills already mandate HTML output per their own spec. The project-level rule extends, does not override:

- **`causal-ablation-cascade-sim` §7-8:** TWO HTML files per invocation (quantitative report + viz)
- **`squidiff-in-silico-gate` Output Format:** Single self-contained HTML, Nature Methods style 5-panel
- **`morpheus-4d-viz`:** Single interactive HTML, Three.js 4D scene with timeline + orbit

The new project rule applies when the skill is NOT being invoked (manual session work that reaches a conclusion).

---

## §13 · Verification

Future session can verify rule compliance by:

1. **Smoke test:** ask analytical question, verify HTML emitted to `reports/` with all 8 mandatory sections.
2. **Simulation-backed test:** invoke simulator, verify TYPE A + TYPE C both emitted and cross-linked.
3. **Composite-auditor sweep:** periodic check that every claim record's `session_id` field references an existing HTML file in `reports/`.
4. **Schema validation (future):** `scripts/validate_html_reports.py` (planned but not yet built) checks every HTML in `reports/` has the 8 mandatory sections + visible contract fields + no external dependencies.

---

## §14 · Maintenance

- This file is **versioned alongside the substrate-evidence-guide.md**. When the output contract §5 changes, this file's §3-§4 should be updated.
- When a new TYPE emerges in practice, document it here BEFORE codifying as canonical (proposed via ADR, accepted via update to this file).
- When a new simulator is added to the project, update §9 simulation-backed rule with a row.
- Backwards-incompatible changes (e.g., new mandatory section) require a new ADR.

— v1.0 · ADR-0007 · 2026-05-14 —
