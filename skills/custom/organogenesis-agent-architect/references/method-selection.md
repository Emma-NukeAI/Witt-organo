# Method Selection — Method 1 vs Method 2 vs Hybrid

> **When to read this file:** During Phase 2 (method selection) of the Mode A pipeline, or when the user invokes `/method-compare`. This file is the decision framework for choosing how a workflow will be agent-ified.
> 
> **Maintenance note:** This file is expected to be updated as the project learns which method works for which workflow types. Bump the version footer when updating. Last updated: April 30, 2026.

---

## TL;DR

The two methods serve different epistemics. Choose based on **what kind of evidence the workflow needs to generate** and **how much human judgment the question demands per step**.

| | **Method 1** (Orchestrated swarm) | **Method 2** (Human-driven) |
|---|---|---|
| **Default mental model** | "The system drives, humans gate" | "Humans drive, the system instruments" |
| **Throughput** | High (minutes–hours per cycle) | Low (hours–days per cycle) |
| **Substrate evidence** | Tests 1, 2, 4 | Tests 1, 3, 5 |
| **Human cognitive load** | At gates only | At every step |
| **Best for** | Routine, repeatable, well-defined | Novel, exploratory, cross-field |
| **Failure mode if mis-applied** | Confidently wrong outputs at scale | Bottlenecks; team can't keep up with thinking |

---

## When to use Method 1 (Orchestrated swarm)

Method 1 is the orchestrator-led path: a 24/7 orchestrator agent dispatches to a swarm of specialist agents (via MCPs), an auditor filters their output, a human gate approves, then a simulation orchestrator runs the proposed thesis through simulation specialists, another auditor filters, another human gate approves, and the result lands in the simulation outputs DB.

### Use Method 1 when ALL of the following are true:

- ✅ The workflow is **well-defined** with clear success criteria
- ✅ The work is **high-volume** or **repeatable** (parameter sweeps, literature syntheses, batch experiment design)
- ✅ The substrate has **accumulated calibration coverage** for this question type (or you're explicitly building that coverage)
- ✅ The team needs **throughput** (you'd otherwise bottleneck on humans)
- ✅ Failure modes are **bounded and reversible** (worst case: a wasted simulation batch, not a wasted lab run)

### Method 1 worked examples

**Example A: Pruning loop iteration**
- Question: "Find the next-most-informative ablation to test in the active-learning pruning loop"
- Why Method 1: 100+ iterations needed, each iteration is well-bounded, the substrate is being trained on this exact question type (Test 4 calibration data is the byproduct)
- Agents: `sim-orchestrator` → `causal-pruner` → `auditor` → HUMAN GATE → `experiment-designer` → `auditor` → HUMAN GATE → outputs DB

**Example B: Weekly literature triage**
- Question: "Which of this week's 47 new papers in organogenesis/causal ML are relevant?"
- Why Method 1: Repeatable, well-defined relevance criteria, throughput matters
- Agents: `literature-monitor` → specialist swarm scores each paper → `auditor` filters by threshold → human reviews top 5

**Example C: Confirmatory analytics on finalist samples**
- Question: "Does sample S-2026-091 hit the four success gates?"
- Why Method 1: Standardized analysis pipeline, multiple modalities running in parallel
- Agents: dispatcher → `scrna-seq-analyst` ‖ `spatial-omics-analyst` ‖ `histology-reviewer` ‖ `marker-validator` → `cross-modality-integrator` → HUMAN GATE → outputs DB

### Substrate evidence Method 1 produces well

- **Test 1 (AI capabilities):** Each specialist agent produces structured outputs with confidence — every one is a Test 1 data point.
- **Test 2 (agency):** Multi-step workflows with explicit checkpoints — the structural shape Test 2 measures.
- **Test 4 (calibration):** Volume of confidence-tagged outputs needed for ECE and reliability diagrams.
- *Limited:* Test 3 (each Method 1 cycle is shallow; case capture is thinner than Method 2).
- *Limited:* Test 5 (cross-field requires deeper per-step reasoning that Method 2 does better).

---

## When to use Method 2 (Human-driven)

Method 2 has no orchestrator. The human queries individual specialists directly, in whatever order they want. An accumulator agent assembles their outputs into a coherent thesis. The human approves the thesis. Then either Sim Agent A or Sim Agent B runs validation. Output lands in the simulation outputs DB.

### Use Method 2 when ANY of the following are true:

- ✅ The question is **novel** — substrate doesn't have calibration coverage yet
- ✅ The decision is **high-stakes** — irreversible commitments, large budget allocations, ethics-adjacent
- ✅ The work is **cross-field** — spans organogenesis + an adjacent biological domain (cardiology, ophthalmology — TBD)
- ✅ You're **deliberately training the substrate** — Method 2 sessions are particularly rich case captures
- ✅ The team is **early in trusting the agents** — better to over-include humans than under-include

### Method 2 worked examples

**Example A: Designing the Test 5 cross-field benchmark**
- Question: "Which 15-20 organogenesis questions should we use to test cross-field partner-field integration?"
- Why Method 2: Novel, cross-field by definition (Test 5), needs human judgment about which questions are well-bridged vs. forced
- Agents: HUMAN → `cross-field-bridge-agent` (suggest partner-field framings) ‖ HUMAN → `domain-knowledge-curator` (find candidate organogenesis questions) → `accumulator` → HUMAN approves → `cross-field-bridge-agent` (validates bridge quality) → outputs DB

**Example B: Phase II → Phase III transition planning**
- Question: "Which findings from the mouse work should we prioritize for human PSC organoid translation?"
- Why Method 2: One-time decision, high-stakes (sets the direction of $M+ in Phase III), needs deep human judgment
- Agents: HUMAN queries `mouse-results-analyst`, `morizane-coordinator`, `regulatory-ethics-advisor` individually → `accumulator` → HUMAN GATE → no sim needed (this is a planning decision)

**Example C: Investor data package framing**
- Question: "How should we present the substrate validation test results to make the substrate framing legible to a generalist investor?"
- Why Method 2: One-time, narrative-heavy, needs human judgment on framing
- Agents: HUMAN queries `evaluation-runner` (raw test results), `calibration-tracker` (calibration narrative), `investor-relations-drafter` (framing options) → `accumulator` → HUMAN GATE → handoff to `client-presentation` skill

### Substrate evidence Method 2 produces well

- **Test 1 (AI capabilities):** Each specialist response is a Test 1 data point, especially for novel question types not covered by Method 1's repeated questions.
- **Test 3 (iteration loop):** Method 2 sessions are case-capture gold. The human's reasoning about why they queried agent X then agent Y is the substrate's training signal.
- **Test 5 (cross-field):** Cross-field judgment is what humans currently do better than orchestrators. Method 2 captures that judgment for the substrate.
- *Limited:* Test 2 (no multi-step autonomous workflow — humans drive each step).
- *Limited:* Test 4 (volume too low for tight calibration metrics, but per-prediction context is much richer).

---

## When to use Hybrid

Most real workflows have both modes. The principle: **Method 2 outer loop, Method 1 inner loop** — humans drive strategic decisions, the orchestrator handles tactical execution.

### Hybrid worked examples

**Example A: Full kidney POC iteration cycle**
- Outer (Method 2): Human decides "this week we focus on RA timing variation." Queries `causal-pruner` for ranked recipes, `experiment-designer` for protocol options, `bwh-coordinator` for lab capacity. `accumulator` synthesizes. Human approves the iteration plan.
- Inner (Method 1): Orchestrator dispatches the approved plan. Pruner runs the sweep, sim-orchestrator handles compute, experiment-designer drafts protocols, auditor filters, second human gate approves the lab run.

**Example B: Weekly substrate evidence review**
- Outer (Method 2): Human asks `evaluation-runner` for week's test results, `calibration-tracker` for calibration delta, `risk-register` for any test 3 anomalies. `accumulator` synthesizes a narrative.
- Inner (Method 1): The substrate-instrumentation agents (calibration-tracker, evaluation-runner) ran their batched analyses overnight on Method 1.

### Document hybrid systems explicitly

When proposing a hybrid, name **which method handles which slice**. Don't just say "hybrid" — say "Method 2 for the strategic planning, Method 1 for the execution loop, with the human gate at the boundary." Future iterations of the system depend on knowing where the human/automation seam sits.

---

## Decision tree

If you're unsure, walk this:

```
1. Does the substrate have calibration coverage for this question type?
   ├── YES → Continue to step 2.
   └── NO → Method 2 (you'd be deploying uncalibrated automation).

2. Is the failure mode bounded and reversible?
   ├── YES → Continue to step 3.
   └── NO → Method 2 (high stakes need humans per step).

3. Is the work high-volume / repeatable?
   ├── YES → Continue to step 4.
   └── NO → Method 2 (low volume doesn't justify orchestration overhead).

4. Does the work span structurally different fields?
   ├── YES → Hybrid (Method 2 for cross-field judgment, Method 1 for in-field execution).
   └── NO → Method 1.

5. Are you deliberately training the substrate (case capture)?
   ├── YES → Hybrid (Method 2 for the rich capture, Method 1 if there's bulk work alongside).
   └── NO → Method 1 confirmed.
```

---

## Substrate evidence cross-reference

Each method generates evidence for some validation tests but not others. To cover all five tests across the project, you need both methods running in parallel.

|  | Method 1 evidence | Method 2 evidence |
|--|-------------------|-------------------|
| **Test 1** (AI capabilities) | ✅ Volume — many question types | ✅ Depth — novel question types |
| **Test 2** (agency) | ✅ Direct — this IS Test 2's measurement context | ✗ Not the right shape |
| **Test 3** (iteration loop) | △ Shallow case captures | ✅ Rich case captures |
| **Test 4** (calibration) | ✅ Volume needed for ECE | △ Per-prediction depth, low volume |
| **Test 5** (cross-field) | △ Limited — orchestrator may not invoke the partner field | ✅ Human can deliberately bridge fields |

**Implication:** A pure-Method-1 project will have weak Test 3 and Test 5 evidence. A pure-Method-2 project will have weak Test 2 and Test 4 evidence. **Both methods should be running by Phase I month 2.**

---

## Anti-patterns

1. **Forcing Method 1 because it feels more "agent-y."** Method 2 is fully agent-based; the agents just don't have an orchestrator above them.
2. **Forcing Method 2 because the team is anxious about automation.** Anxiety is real; Method 1 with strong human gates and reasoning-exposer is often the right answer instead.
3. **"Hybrid" used as an escape from making a choice.** Hybrid is a real option, but if you can't say which slice is which method, you don't have a hybrid — you have an unclear design.
4. **Skipping the calibration-coverage question.** Deploying Method 1 on a question type the substrate hasn't been calibrated on produces confident wrong outputs at scale. This is Test 4's worst-case failure mode and it's an architectural mistake, not a model mistake.
5. **Treating method as a permanent property of the system.** Workflows can migrate from Method 2 → Method 1 as calibration coverage accumulates. Plan for that migration; don't lock in.

---

## v2.2 update — Method 1 as minority case in Phase I (derived from stress-test)

The April 30, 2026 stress-test of the architecture against 2025+ LLM evidence produced a strong recommendation: **in Phase I, Method 1 should be a minority case, not a primary mode of operation**. The reasoning is structural.

For Method 1, the documented LLM problems are cumulative across the pipeline: the orchestrator makes routing decisions (with the calibration and faithfulness limitations documented in 2025 literature), the swarm produces outputs (with brittleness to perturbations), the auditor filters (inheriting all prior problems and adding its own), and only then does the human intervene. Each layer multiplies the failure modes. Trehan & Chopra (January 2026, arXiv:2601.03315) reported that fully autonomous research pipelines fail roughly 75% of the time even in controlled settings.

For Method 2, the human directs strategic decisions and the models execute more bounded tasks. The individual failure modes are the same but their impact is contained by frequent human presence. The human is the calibrator-of-confidence by default, which sidesteps the documented poor calibration of LLMs.

### Recommended Phase I assignment of tasks to methods

**Method 1 in Phase I — reserved for low-risk tasks where errors are easily reversible:**

- Literature monitoring (collect and summarize new papers)
- Operational scheduling (calendar, reminders, deadline tracking)
- Output formatting and document templating
- Reagent inventory tracking
- Simple consistency checks (e.g., "do the cited references actually exist?")
- Routine batch processing of well-characterized question types where calibration coverage exists

**Method 2 in Phase I — used for everything else:**

- All scientific reasoning over experimental design
- All causal-pruner ranking workflows (per agent-catalog.md v2.2 update)
- All cross-field bridging (per agent-catalog.md v2.2 update)
- All compliance and regulatory reasoning
- All decisions affecting budget burn or experimental direction
- All novel question types where substrate calibration is not yet established

### Phase II and III progression

Method 1 is considered for progressive expansion to additional task types in Phase II and III, **conditional on substrate evidence accumulated in Phase I demonstrating that calibration is reliable enough to support autonomous judgment in those domains**. The decision to migrate a task from Method 2 to Method 1 should be data-driven, not aspirational.

This Phase I recommendation does not change the architecture itself — both methods remain available, both have agent specifications, both can be invoked. What changes is **how tasks are assigned to methods during the first eight months**.

---

### Wet-lab proposal protocol (v1.2 addition)

When any conversation, agent, or skill proposes wet-lab work that crosses budget or compliance thresholds, the **first turn** introducing the wet-lab proposal must include a visible callout. Position the callout above the substantive analysis, not below or buried in a §X subsection of a long document. Required content of the callout:

- Estimated cost (a range is acceptable; "TBD" is not)
- Required gates: IACUC / IBC / ISSCR depending on the work
- Approval owner: human gate per CLAUDE.md §7

**Markdown format for HTML reports:**

```html
<div class="callout danger">
  <strong>⚠️ Budget & compliance gates required.</strong>
  Estimated cost: $X-$Y. Gates: IACUC pending, IBC if applicable, founder approval required.
  This proposal is not actionable without explicit approval.
</div>
```

**Why this is mandatory.** The 2026-05-09 session surfaced the budget/compliance gates at the END of the experiment document, sections 11-12 of 16. The retrospective flagged this as a delayed surfacing of a hard rule. The fix is structural: the callout precedes the analysis. The reader cannot miss it.

**Thresholds for triggering:**

- Any computational work proposing wet-lab: trigger
- Any cost > $5,000: trigger regardless of mode
- Any use of animals (zebrafish, mouse): trigger regardless of cost
- Any use of patient-derived material: trigger regardless of cost
- Any Squidiff Mode 2 invocation (Runpod fine-tune at $200-500): trigger

When in doubt, trigger. False positives are cheap; missed gates are catastrophic.

---

— End of method-selection.md v1.2 —
