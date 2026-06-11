# Agent invocation decision matrix

> **When to read this file:** when designing any output that will generate substrate evidence (i.e., any structured output contract per CLAUDE.md §5 with confidence/evidence/framework). This is the lookup table for **which catalog agents should be invoked given the work-type**. Use it as a reflex during CLAUDE.md §11 agent-invocation preflight.
>
> **Companion to:** `agent-catalog.md` (describes what each agent IS); this file (describes WHEN to invoke them).
>
> **Authority:** per ADR-0006 (2026-05-14). Updated as new agents enter the catalog or new work-types emerge.
>
> **Last updated:** 2026-06-11 · v1.2 (GWT v1.1) — added the anti-fabrication verification-gate Hard Rule row + `hypothesis-generator` routing (ADR-0008); `investor-relations-drafter` suspended Phase I; `retrospector` slot reserved (ADR-0009). · v1.1 (2026-05-14) — added html-report-emitter Hard Rule row per ADR-0007.

---

## How this matrix works

For each row, the columns mean:

- **Work-type signal** — what is the agent producing in this turn that triggers a catalog-agent invocation?
- **Required agent** — the catalog agent that owns this work-type per `agent-catalog.md`.
- **Gate level** —
  - **Hard Rule** = CLAUDE.md §7 explicitly enforces this; skipping is a Hard Rule violation.
  - **Required** = must be invoked OR explicitly skip-with-justification.
  - **Recommended** = should be invoked for default substrate quality; skip-with-justification is lower bar.
- **Composite pattern** — if the agent participates in a multi-agent pattern (e.g., pruner → Logic-LM → human gate), note it here.
- **Substrate evidence** — which of Tests 1-5 the invocation contributes to.

The matrix is consulted in CLAUDE.md §11 agent-invocation preflight. The output contract field `agents_invoked` records the result (invoked | skipped-ad-hoc | not-applicable) with justification when skipped.

---

## §1 · Hard-gated work (Hard Rule violations if skipped)

| Work-type signal | Required agent | Composite pattern | Substrate evidence |
|---|---|---|---|
| Generating ranked candidates / minimal sets / sufficiency hypotheses / pruning over signaling networks | **`causal-pruner`** | `causal-pruner` → `Logic-LM` verifier → **HUMAN GATE** (per §7.1) | Test 1, Test 3, Test 4 |
| Retrospective / audit of substrate-evidence outputs | **`composite-auditor`** (Mode 1 split-and-vote minimum) | 3+ parallel auditors → vote synthesis | Test 1, Test 4 |
| Cross-field framing of organogenesis question in Phase I | **`cross-field-bridge-agent`** (Method 2 only) | Standalone with explicit human invocation (per §7.2) | Test 5 (exploratory) |
| Wet-lab protocol translation from in-silico recipe | **`experiment-designer`** + budget/compliance preflight | Designer → `regulatory-ethics-advisor` review → HUMAN GATE (per §7 budget rule) | Test 2 |
| Any claim or output that affects compliance / budget / partner relationships | **`regulatory-ethics-advisor`** + HUMAN GATE | Direct human gate, no automatic filtering (per §7) | Mission-critical safety |
| **Conclusion / checkpoint of substrate-evidence-producing work** (per §5 contract; user signals end-of-inquiry; phase completion; substantive answer with confidence ≥ 0.5) | **`html-report-emitter`** (skill or ad-hoc) per `html-report-contract.md` | Emit HTML report in `reports/` with visible §5 contract UI; offer additional visuals (visual-offer reflex per §11 closing sub-step). **If conclusion is simulation-backed:** ALSO emit/cross-link TYPE C viz (Three.js). | Test 1 (orchestration / reasoning), Test 2 (workflow output materialized) |
| **Conclusion backed by simulation output** (`morpheus-4d-viz`, `causal-ablation-cascade-sim`, `squidiff-in-silico-gate`, BioDynaMo, `sim-orchestrator`, future simulators) | **TYPE C viz emitter** (the simulator's own HTML output OR `morpheus-4d-viz` skill) | Per simulator's SKILL.md spec; static screenshot NOT sufficient; must be interactively explorable | Test 1, Test 2 |
| **Any output containing an external identifier** (ENSDARG/ENSDARP, UniProt, PMID, GEO/SRA/PXD, DOI) (GWT v1.1) | **source-of-truth `resolve_id` + `verify_output` gate** (Logic-LM-class, NOT an LLM) | Each ID resolves through `verified_identifiers.json` or is flagged in `gap_flags`; unresolved ENSDARG = gate FAILURE. Owner: `domain-knowledge-curator` (PR-09, deferred) | Test 1, Test 4 |

## §2 · Required (must invoke or skip-with-justification)

| Work-type signal | Required agent | Composite pattern | Substrate evidence |
|---|---|---|---|
| Any structured output with `confidence` + `framework_applied` field per §5 | **`reasoning-exposer`** | Wraps the producing agent's output | Test 1 (forces visible reasoning) |
| Claim record with `confidence < 0.95` and checkable outcome | **`calibration-tracker`** | Registers record + applies post-hoc isotonic/histogram-binning per v2.2 | Test 4 |
| Perturbation-resistant evaluation against held-out set (Test 3 measurement) | **`evaluation-runner`** | Runs each batch with controlled perturbations, reports mean ± std (per v2.2) | Test 3 |
| scRNA-seq pipeline / spatial / histology / imaging analysis | corresponding analyst agent (`scrna-seq-analyst`, `spatial-omics-analyst`, `histology-reviewer`, `imaging-analyst`) | Output may chain to `cross-modality-integrator` | Test 1, Test 4 |
| Integration of multiple readout modalities into success-gate evidence | **`cross-modality-integrator`** | Highest-leverage agent per catalog; synthesizes scRNA + spatial + histology + sim | Test 1, Test 4 |
| Marker scoring against canonical kidney markers | **`marker-validator`** | May chain to `cross-modality-integrator` | Test 1, Test 4 |
| Generating a research hypothesis grounded in priors/literature (GWT v1.1) | **`hypothesis-generator`** (Method 2 default; Method 1 only on wet-lab escalation w/ 100% HUMAN GATE) | Consults source-of-truth → complements via MCP/ToolUniverse → `reasoning-exposer` → ethics deny-list; obligatory non-empty contradictory_evidence | Test 3, Test 4 (direct) |

## §3 · Recommended (skip-with-justification has lower bar)

| Work-type signal | Recommended agent | Notes |
|---|---|---|
| Literature monitoring / paper triage | `literature-monitor` | Method 1 task; suitable for orchestrated swarm |
| IP / patent landscape monitoring | `ip-patent-watcher` | Operational |
| Engineer-feedback case capture | `case-capture-elicitor` | Critical for Test 3 input but not synchronous |
| Method 2 aggregation of specialist outputs into thesis | `accumulator` | Method 2 only |
| Phase I timeline / budget tracking | `program-manager`, `budget-tracker` | Operational |
| Risk tracking / escalation | `risk-register-agent` | Operational; slot reserved for `retrospector` in Cycle 3 (ADR-0009) — register folds into `program-manager` then |
| Investor updates / milestone packaging | `investor-relations-drafter` | **SUSPENDED in Phase I (ADR-0008)** — manual until the Phase-II financing gate |
| Simulation orchestration (Runpod batches) | `sim-orchestrator` | Method 1 task |
| Benchmark task design | `benchmark-designer` | Test 4 ground-truth source |
| Domain-knowledge curation | `domain-knowledge-curator` | Test 3 substrate maintenance |

## §4 · Custom skills with role-equivalent behavior

These custom skills replicate / extend catalog agent roles. Invoking the skill counts as invoking the equivalent agent.

| Custom skill | Equivalent catalog role(s) | When triggered |
|---|---|---|
| `causal-ablation-cascade-sim` | Composite of `sim-orchestrator` + `cross-modality-integrator` for cascade ablations | Multi-stage perturbation cascade simulations with HTML report + 4D viz |
| `squidiff-in-silico-gate` | Composite of `experiment-designer` + transcriptomic prediction | Transcriptomic-response prediction at human-gate prior to wet-lab |
| `organogenesis-agent-architect` | Meta-agent — designs other agents per the substrate spec | When designing a new agent for the substrate |

---

## §5 · Output contract field — `agents_invoked`

Per ADR-0006, the structured output contract (CLAUDE.md §5) MUST include an `agents_invoked` field when work-type matches any matrix row. Schema:

```json
"agents_invoked": [
  {
    "agent": "causal-pruner",
    "status": "invoked | skipped-ad-hoc | not-applicable",
    "invocation_id": "<agent task ID if invoked>",
    "reason": "<required if status=skipped-ad-hoc>",
    "evidence_generated": ["test_1", "test_4"]
  }
]
```

**Status values:**

- `invoked` — agent was actually called (via Agent tool, skill, or scripted process). `invocation_id` required.
- `skipped-ad-hoc` — work matched the role but agent was not invoked; the agent ran the role ad-hoc. `reason` required (explicit justification, not boilerplate).
- `not-applicable` — work-type does not match this agent's role; field present for traceability.

Skipping without justification or without populating the field is a CLAUDE.md §11 audit failure.

---

## §6 · Common patterns

### Pattern A: Substrate-instrumented analytical output (e.g., the 2026-05-14 session)

Required invocations:
1. `reasoning-exposer` (or equivalent wrapping)
2. `calibration-tracker` if claim records are emitted
3. `cross-modality-integrator` if multiple evidence modalities are synthesized
4. `causal-pruner` if minimal-set / sufficiency claims are made
5. Closing: `composite-auditor` if the output will be cited as audit evidence

Note: Phase I sessions may operate with Method 2 humans driving — agent invocations may be skipped-with-justification when a human is in the loop performing the equivalent function. But the field must still be populated.

### Pattern B: Wet-lab proposal

Required invocations:
1. `experiment-designer`
2. `regulatory-ethics-advisor` (compliance check)
3. HUMAN GATE before submission
4. After execution: `imaging-analyst`, `marker-validator`, `scrna-seq-analyst` etc as relevant
5. Synthesis: `cross-modality-integrator`

### Pattern C: Method 1 batch (orchestrated swarm)

Required invocations:
1. `sim-orchestrator` or relevant orchestrator
2. Specialist swarm (per task type)
3. `composite-auditor` Mode 2/3 as filter
4. HUMAN GATE 1 (founder + dev-bio adviser)
5. (If simulation phase) `sim-orchestrator` for simulation specialists
6. `composite-auditor` again as filter
7. HUMAN GATE 2

---

## §7 · Maintenance

- This matrix is **versioned alongside `agent-catalog.md`**. When the catalog adds an agent, this matrix should add a row.
- The matrix is **scope-bounded** to the project's six niches (per CLAUDE.md §3). Agents not relevant to the niches are not listed.
- When a Hard Rule changes in CLAUDE.md §7, the matrix's §1 must be updated to reflect.
- Backwards-incompatible changes to gate levels (e.g., Recommended → Hard Rule) require a new ADR.

— v1.1 · ADR-0006 + ADR-0007 · 2026-05-14 —

**v1.1 changes vs v1.0:** Added 2 Hard Rule rows (§1) for `html-report-emitter` at conclusion + TYPE C viz emitter when simulation-backed. Tied to CLAUDE.md §5/§7/§11 v2.5 and `html-report-contract.md` v1.0 per ADR-0007.
