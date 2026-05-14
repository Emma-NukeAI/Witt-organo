# Project Organogenesis × Witt — Master Scope Document

**Version:** 1.2  
**Date:** May 04, 2026  
**Status:** Working document — update as the project evolves  
**Owner:** Emmanuel  
**Purpose:** Single source of truth for the integrated Witt substrate × Organogenesis POC project. Use this doc as the persistent reference for analysis, planning, and skill iteration.

**Changelog:**
- **v1.2 (May 04, 2026)** — Recalibration of Tests 3, 4, 5 thresholds derived from April 30 stress-test of architecture against 2025+ LLM evidence. Three-tier threshold reporting introduced (defensive / ambitious / per-category). Test 5 explicitly framed as exploratory in Phase I. Reference to companion stress-test brief added. No structural changes to the five tests themselves.
- **v1.1 (Apr 30, 2026)** — Test 5 partner field changed from TDA (topological data analysis) to TBD adjacent biological domain (cardiology or ophthalmology, decision pending). Added operating principle from Martín's April 29 conversation. Reasoning frameworks integrated as transversal evidence stream within substrate (not a separate hierarchy). Cross-field-bridge-agent updated to be partner-field-agnostic. Glossary updated.
- **v1.0 (Apr 30, 2026)** — Initial release.

---

## Operating Principle (from Martín, April 29 conversation)

> **Prueba pequeño antes de armar bien.** Creativity comes from constraints, not from their absence. What gets tested badly informs more than what gets designed well. Mental structure orders itself from information, not from planning. Every component of this system — agents, flows, reasoning frameworks, the system as a whole — must pass through a "rough but running" version before chasing an "elegant but theoretical" version. This applies at every level. Discussion is welcome and frequent; standing still while having brilliant conversations is the failure mode to avoid.

This principle governs every decision in this scope document. When in doubt, build the rough version first.

---

## Table of Contents

1. [Executive framing](#1-executive-framing)
2. [The two layers — substrate vs. domain](#2-the-two-layers--substrate-vs-domain)
3. [Witt substrate — what it is, what it isn't](#3-witt-substrate--what-it-is-what-it-isnt)
4. [Organogenesis POC — what it is, what it isn't](#4-organogenesis-poc--what-it-is-what-it-isnt)
5. [The five substrate validation tests](#5-the-five-substrate-validation-tests)
6. [Architecture — the dual-method system](#6-architecture--the-dual-method-system)
7. [Agent catalog (substrate-aware)](#7-agent-catalog-substrate-aware)
8. [Phase plan](#8-phase-plan)
9. [Hiring profile](#9-hiring-profile)
10. [Risks, honestly characterized](#10-risks-honestly-characterized)
11. [Open questions](#11-open-questions)
12. [Glossary](#12-glossary)
13. [Document maintenance](#13-document-maintenance)

---

## 1. Executive framing

**One paragraph.** Witt is a substrate (an underlying AI capability layer) that captures expert calibrated judgment, exposes its reasoning, and grows with use. Project Organogenesis is the first deployment domain — a research program in causal organogenesis with a zebrafish pronephros POC. The POC year produces two categories of output: the biological result itself (does causal-pruning produce coherent kidney development?) and the substrate-foundational evidence (do the substrate's reasoning, agency, learning, calibration, and cross-field capabilities actually work?). Both outputs matter; conflating them produces bad strategic decisions.

**The non-obvious move.** Most teams running a biology POC build agents to ship the biology result. Witt builds agents that ship the biology result *and* generate substrate-quality evidence at every step. Every agent action is also a calibration data point, a learning signal, a piece of cross-field evidence. The agents are not the deliverable — they are instrumented infrastructure.

**The strategic stake.** If the substrate framing proves out, Witt is positioned as the cognitive infrastructure for many expert domains over 5–10 years. If only the biology proves out, the team has built a regenerative-medicine research tool. Both are valuable; the difference matters for hiring, capital strategy, and how every agent is designed.

---

## 2. The two layers — substrate vs. domain

The most important distinction in the project. Conflating these layers is the most common analysis error.

| Aspect | Substrate layer (Witt) | Domain layer (Organogenesis) |
|--------|------------------------|------------------------------|
| **What it is** | Reusable AI infrastructure for capturing and applying calibrated expert judgment | A research program on causal-pruning models for zebrafish pronephros development |
| **What it produces** | Calibration data, learning evidence, cross-field operation evidence, deployment history | Biological hypotheses, simulation results, wet-lab outcomes, kidney-formation evidence |
| **Who values it** | Investors, technical advisors, future expert communities | Regenerative medicine researchers, journals, developmental biology field |
| **Time horizon** | 5–10 years to maturity | 8 months to POC completion, then translation steps |
| **Defensibility moat** | Accumulated deployment history, captured judgment, cross-field integration | Domain expertise + scientific publication + IP filings |
| **First-year metric** | Five validation tests (orchestration, agency, learning, calibration, cross-field) | Four success gates (Induction, Specificity, Identity, Parsimony) |
| **What "success" looks like** | Substrate is structurally capable, well-calibrated, learns from use, operates across fields | Reproducible pronephric structures with marker confirmation in zebrafish embryos |

**Implication for everything.** When designing an agent, ask: does it advance the substrate layer, the domain layer, or both? Agents that only advance the domain layer are valuable but generic. Agents that also advance the substrate layer (capture confidence estimates, log calibration data, expose reasoning, generate cross-field evidence) are what makes Witt different from a vertical biology tool.

---

## 3. Witt substrate — what it is, what it isn't

### Definition

A substrate that captures the **calibrated judgment of expert communities** and uses that captured judgment to:

1. **Amplify** expert capability in real time
2. **Transfer** expertise to junior practitioners
3. **Generate** new insights through human-system collaboration
4. **Act** on routine decisions on behalf of expert communities

These are the "four pillars." None is fully testable in the POC year — they emerge from substrate maturity over years.

### Three structural commitments

1. **Grows through use.** Every interaction is an opportunity to extend the substrate. Calibrated feedback compounds.
2. **Exposes its reasoning at every step.** No black boxes. Every output includes confidence, evidence, and considered alternatives.
3. **Accumulates moat.** Defensibility comes from accumulated deployment history, not from features or distribution.

### Substrate vs. product (critical distinction)

A **product** company picks one of the four pillars (most plausibly amplification in cardiology) and builds a focused tool. Competes against Caresyntax, Theator. Ceiling bounded by vertical market size.

A **substrate** company builds the underlying capability that all four pillars eventually emerge from. Takes longer to validate, attracts different capital, produces dramatically larger outcomes when it succeeds. **Witt is committing to substrate.**

### Five technical layers

| Layer | Maturity | Notes |
|-------|----------|-------|
| **Capture** | Partially mature | Structured artifact capture is mature; deep judgment elicitation is research-grade |
| **Reasoning** | Feasible now | Foundation models with tool use + retrieval — buildable today |
| **Calibration** | Hardest piece | Foundation models poorly calibrated by default; production-grade calibration is the substrate's most demanding research investment |
| **Compound-through-use** | Partially mature | Retrieval from growing KB is mature; deep cross-heterogeneous compounding is research-grade |
| **Cross-field operation** | Partially feasible at small scale | The venture's long-horizon ambition; structurally unsolved at scale |

### What the substrate is NOT

- It is not a knowledge base. It captures judgment under uncertainty, not facts.
- It is not a chatbot. It produces structured, calibrated, source-cited reasoning.
- It is not a vertical AI tool. Medicine is the first domain, not the defining domain.
- It does not generate new science from scratch. It reasons over existing knowledge well, calibrates judgments, integrates feedback, operates across fields.

---

## 4. Organogenesis POC — what it is, what it isn't

### The science

A research program in **causal organogenesis** — using computational models that prune over-connected developmental signaling networks to produce coherent organ-formation pathways. The POC is structured around a **zebrafish pronephros model**: a kidney-like organ that develops in zebrafish embryos through well-characterized signaling cascades (BMP, Nodal, retinoic acid).

### Phase I budget — $297,000

| Workstream | Cap |
|------------|-----|
| Simulation engineering + benchmark design | $46k |
| Causal-pruning model + Runpod compute | $29k (compute hard-capped at ~$3k) |
| Boston zebrafish execution | $96k |
| Constructs + reagents | $34k |
| Confirmatory analytics (scRNA-seq + spatial + histology) | $49k |
| Program operations | $20k |
| Contingency | $23k |

### Phase I timeline — 0–8 months

| Window | Primary work | Decision criterion |
|--------|--------------|-------------------|
| 0–2 mo | Simulation engineering, kidney priors, benchmark tasks, low-cost Runpod sweeps | Model produces ranked candidate programs + chaperone-tissue design list |
| 2–4 mo | Pilot embryo runs, optimize chaperone-patch delivery, establish imaging readouts | At least one candidate shows interpretable renal developmental activity |
| 4–6 mo | Full candidate panel, repeat cohorts, kidney marker assays | Reproducible pronephric/early-kidney induction above controls |
| 6–8 mo | Confirmatory omics, spatial, histology + investor data package | Identity and parsimony claims hold up |

### Four biological success gates

| Gate | What it means |
|------|---------------|
| **Induction** | Reproducible ectopic kidney structures above negative controls across independent batches |
| **Specificity** | Structures localize to the chaperone tissue and follow planned timeline (not nonspecific teratogenesis) |
| **Identity** | Marker + transcriptomic evidence supports renal identity (wt1a, pax2a, pax8, hnf1b) — not generic mesoderm |
| **Parsimony** | Pruned program matches/beats fuller-cue baseline with fewer cues, tighter timing, simpler chaperone context |

### Validation ladder

Zebrafish (Phase I) → Mouse (Phase II) → Human PSC-derived organoids (Phase III). **No human embryo experimentation, ever** (per ISSCR 2025).

### Partner map (operational reality)

| Stage | Partners |
|-------|----------|
| **Phase I** | BWH Aquatics Facility (Boston), SeqMatic (Bay Area), Morizane Lab (MGH), Runpod |
| **Phase II** | Boston Children's Mouse Gene Manipulation Core, UCI Transgenic Mouse Facility |
| **Phase III** | UCSD HUMANOID, iXCells Biotechnologies, Cedars-Sinai Regenerative Medicine Institute |

### What the POC is NOT

- Not a clinical-translation program. Zebrafish work is research, not therapeutic development.
- Not a near-term path to revenue. Substrate's commercial value emerges from later deployments.
- Not a defining commitment to regenerative medicine as Witt's vertical. Organogenesis is the first domain, not the defining domain.
- Not a substrate maturity proof. POC year proves substrate *foundations*, not maturity.

---

## 5. The five substrate validation tests

Each test runs **alongside** the biological POC. Together they evaluate whether Witt's substrate foundations are real and buildable on current AI capabilities. Each test is illustrative — what would actually be tested, not a locked execution plan.

### Test 1 — AI capabilities (orchestration + reasoning)

**Question:** Can the substrate's reasoning layer (foundation model + tool use + retrieval) produce outputs that working organogenesis researchers would actually act on?

**Setup:** 30–50 question bank from real POC research. System has access to scientific literature retrieval, public organogenesis datasets, simulation tools, basic computational tools.

**Success thresholds (illustrative):**
- ≥40% of questions: response surfaces something the engineer wouldn't have produced
- ≥70% of high-confidence responses: technically accurate
- Confidence-accuracy correlation: r > 0.5
- ≥30% prefer system output over isolated literature search

**What success means for the substrate:** Foundational reasoning layer is buildable on existing AI capabilities. Other layers become tractable.

### Test 2 — Agent capabilities (bounded multi-step workflows)

**Question:** Can the substrate execute well-specified workflows autonomously with appropriate human checkpoints?

**Setup:** 5–10 bounded workflows (parameter sweeps, literature syntheses, experiment proposal generation). Explicit checkpoints for human approval. System logs every decision.

**Success thresholds (illustrative):**
- ≥70% completion rate on first attempt
- ≥80% checkpoint accuracy (asks for input when needed; proceeds when appropriate)
- ≥60% of completed workflows rated useful
- ≥50% time savings vs. manual execution
- **Zero workflows with substantive irreversible decisions made without checkpointing** (non-negotiable safety criterion)

**What success means for the substrate:** Agentic layer is real for bounded workflows. Foundation for the eventual amplification value proposition.

### Test 3 — Iteration loop (compound-through-use)

**Question:** Does the substrate measurably improve through engineer feedback over the POC year? This tests Witt's central defensibility claim.

**Setup:** Held-out evaluation set of 60–80 questions/workflows. Performance measured at start, midpoint (month 4), end (month 8). Engineers use system normally between measurements; their corrections, ratings, case captures, and calibration flags accumulate into the substrate.

**v1.2 update (from stress-test):** Per Mirzadeh October 2024 (not refuted by 2025 work) and Roh June 2025, LLM performance is brittle to perturbations. Single-pass evaluation will produce noisy and over-optimistic results. The `evaluation-runner` agent must run each batch with controlled perturbations (numerical, order, surface) and report mean ± standard deviation. See agent-catalog.md v2.2.

**Success thresholds (recalibrated v1.2 — three tiers):**
- **Defensive threshold (project commitment):** ≥5 percentage points improvement on primary accuracy metric, baseline → year-end. Calibration improvement: confidence-accuracy correlation rises by ≥0.05. No significant degradation on any dimension. Reachable based on current literature.
- **Ambitious threshold (aspirational):** ≥15 percentage points improvement on primary accuracy metric. Calibration improvement: ≥0.15. Reportable as aspirational, not as success criterion.
- **Per-perturbation reporting:** improvement reported separately for unperturbed eval and for perturbed eval, to distinguish genuine improvement from luck on a particular phrasing.

**What success means for the substrate:** Compound-through-use mechanism works on POC-year time scales. Direct evidence for the substrate's defensibility argument.

**The most uncomfortable failure mode:** No measurable improvement across the year would be the most informative outcome of all five tests, and the most uncomfortable. It would mean either feedback types weren't right, volume was insufficient, or the compounding mechanism needs more careful design.

### Test 4 — Calibration tracking

**Question:** Are the substrate's confidence estimates well-calibrated, and do they improve with use?

**Setup:** Every output throughout the year tagged with confidence. Outcomes recorded where observable. Calibration metrics computed quarterly (months 2, 5, 8): Brier score, expected calibration error, reliability diagram. Calibration broken down by **objective prediction type** (binary classification, ranking, extraction, generation) AND by self-reported `framework_applied` field — with the objective decomposition trusted more than the framework decomposition.

**v1.2 update (from stress-test):** Vega et al. (February 2025, bioRxiv doi:10.1101/2025.02.11.637373) established that biomedical LLM calibration is approximately 30% off-target by default. Post-hoc correction methods (isotonic regression, histogram binning, Platt scaling) substantially improve calibration but require tailored application per task type. The original strict threshold (ECE < 0.10) is approximately 3x more stringent than what literature suggests achievable in 8 months. Recalibrated to three-tier reporting.

**Success thresholds (recalibrated v1.2 — three tiers):**
- **Defensive threshold (project commitment):** ECE < 0.20 on aggregate. Achievable with standard post-hoc calibration methods (isotonic regression, histogram binning) applied from day 1. Defensible as real improvement over baseline.
- **Ambitious threshold (aspirational):** ECE < 0.10 on aggregate. Maintained as aspirational target, reported separately from success criterion.
- **Per-category breakdown:** calibration reported by objective task category (binary classification, ranking, extraction, generation), not only as single aggregate number. The Vega et al. finding that "one-size-fits-all approach is not sufficient" implies per-category targeting.
- **High-confidence predictions correct on ≥85% of cases** (this remains as a sub-threshold).

**Operational requirement (v1.2):** the `calibration-tracker` agent applies post-hoc calibration methods (isotonic regression, histogram binning) from day 1 of the evaluation pipeline, not as later optimization. The "model + post-hoc correction" combination is the baseline measured against, not the model alone. See agent-catalog.md v2.2.

**What success means for the substrate:** Foundation for the eventual selective-action value proposition. Substrate can identify cases where it should act vs. defer to humans. **This is the test most likely to produce an uncomfortable result if the ambitious threshold is taken as success criterion.** With recalibrated thresholds, defensible substrate evidence is reachable; ambitious thresholds remain as aspiration.

### Test 5 — Cross-field operation

**Question:** Can the substrate productively integrate knowledge from a structurally distinct biological field into organogenesis questions?

**v1.2 update (from stress-test):** Test 5 is now explicitly framed as **exploratory in Phase I**, not as a criterion of success. Magraner et al. (August 2025, arXiv:2508.10777) demonstrates that integration between domains the model knows is structurally weak in current LLMs — even when the model possesses both bodies of knowledge separately. The cross-field bridge is therefore high-uncertainty research. Modest preliminary evidence in Phase I is the realistic positive outcome; full demonstration is deferred to Phase II or III.

**Partner field:** **TBD.** The cross-field partner will be an adjacent biological domain — most likely cardiology (maximum sinergy with Latido's cath lab Phase II) or ophthalmology (existing domain familiarity). Decision deferred until early Phase I; tracked in Section 11 (Open questions). Rationale: an adjacent biological domain is more realistic for first-year evidence than a structurally lejano field (finance, linguistics) and connects directly to the venture's operational reality.

**Setup:** 15–20 organogenesis questions designed to be amenable to cross-field framing once the partner field is chosen. System has access to standard tools and knowledge for the partner field (specifics depend on choice — e.g., for cardiology this would include cardiac developmental biology references, vascular biology priors, ECG/imaging data structures; for ophthalmology this would include eye development literature, corneal/retinal references). **No pre-training on the bridge** — testing whether current AI can navigate it.

**Success thresholds (recalibrated v1.2 — exploratory):**
- ≥30% of questions: system invokes cross-field tools or references (recognizes relevance)
- ≥50% of invocations: technically appropriate use
- ≥10% of questions: cross-field integration surfaces something engineers wouldn't have produced
- **Zero misleading or incorrect organogenesis interpretations from cross-field misuse** (safety criterion — unchanged, this is non-negotiable)

**Aspirational thresholds (maintained for Phase II or III, not Phase I success criterion):** the original ≥60% / ≥70% / ≥30% framing remains as aspirational target. Phase I primary criterion is "the system produces preliminary evidence (even modest) that cross-field transfer is possible."

**What success means for the substrate:** First empirical evidence that cross-field operation is real, even at modest scale. The seed of the substrate framing's most ambitious claim. With an adjacent biological domain as partner, this also produces immediate operational value: cross-field findings inform Phase II and Phase III roadmaps.

**Operating mode (v1.2):** the `cross-field-bridge-agent` operates in Method 2 only during Phase I — queried by a human, never autonomously dispatched. See agent-catalog.md v2.2.

### What the five tests collectively prove

If all five succeed: substrate framing has clear empirical grounding. **Strong year.**  
Most succeed + a few partial: most likely realistic outcome, also strong. Characterizes which capabilities are mature now and where investment is needed.  
A few fail outright: informative, not catastrophic. The substrate framing is a long-term commitment; the POC year is one year of evidence. Failures tell us where to invest.

### What the tests do NOT prove (audit discipline)

- Substrate maturity at scale (5–10 years away)
- Multi-domain commercial deployment
- Autonomous action on routine cases
- Generation of novel cross-field insights at production volume
- Integration with academic networks beyond the POC team
- Cath lab domain operation (year 2 work)

---

## 6. Architecture — the dual-method system

The architecture is structured around a shared inamovable data foundation that feeds **two parallel methods**. Method choice is a runtime decision, not a fixed pipeline.

### The shared foundation

**`DATA GENERAL INAMOVIBLE`** — a curated, versioned knowledge base containing zebrafish biology priors, kidney development literature, simulation tool documentation, prior experiment archives, and cross-field references for the Test 5 partner field (TBD — see Section 11).

This is **not necessarily a RAG** — could be RAG, could be a structured knowledge graph, could be hybrid. Decision deferred to technical implementation. What matters architecturally:

- **Read-only by default** (preserves baseline integrity for Test 3 measurement)
- **Versioned** (so calibration trends can be measured against a stable substrate)
- **Distinct from outputs** (the simulation outputs that the system *generates* live in a separate `SIMULATION OUTPUTS DB`)

### Method 1 — Orchestrated swarm (autonomous-leaning)

```
DATA INAMOVIBLE
      ↓
Orchestrator Agent (24/7)
      ↓ (via MCPs)
  ┌──────────────────────────────────┐
  │  Specialist Swarm (N agents):    │
  │  • Tissue Biomechanics           │
  │  • Ocular Biology                │
  │  • Tissue Engineering            │
  │  • [...domain experts as needed] │
  └──────────────────────────────────┘
      ↓
Auditor Agent (Yes/No filter on output)
      ↓
HUMAN GATE 1 (founder + dev-bio adviser)
      ↓
Simulation Orchestrator
      ↓
  ┌──────────────────────────────────┐
  │  Simulation Specialists:         │
  │  • Agent AS — Morpheus           │
  │  • Agent BS — BioDynamo          │
  │  • Agent CS — AlphaFold          │
  └──────────────────────────────────┘
      ↓
Auditor Agent (Yes/No filter on simulation output)
      ↓
HUMAN GATE 2 (validate findings)
      ↓
SIMULATION OUTPUTS DB ← (positive reinforcement for next iteration)
                       ← (negative signals fed back to specialist swarm for improvement)
```

**When to use Method 1:**
- High-volume, repeatable analyses (parameter sweeps, literature syntheses)
- Questions with clear success criteria
- When the substrate has accumulated enough calibration data on this question type to trust autonomous routing
- For Tests 1, 2, 4 (orchestration, agency, calibration evidence)

**Substrate evidence Method 1 produces:**
- Test 1 evidence (orchestrator + specialists answer real questions)
- Test 2 evidence (multi-step workflow execution with checkpoints)
- Test 3 evidence (feedback loops feed back into substrate)
- Test 4 evidence (every agent output is confidence-tagged for calibration tracking)

### Method 2 — Human-driven (high-touch, exploratory)

```
DATA INAMOVIBLE
      ↓
HUMAN INPUT 1 → Specialist Agent (e.g., Tissue Biomechanics)
HUMAN INPUT 2 → Specialist Agent (e.g., Cornea Chemistry)
HUMAN INPUT N → Specialist Agent (e.g., [as needed])
      ↓
Accumulator Agent (assembles individual outputs into a thesis)
      ↓
HUMAN GATE
      ↓
  ┌──────────────────────────┐
  │  Sim Agent A             │
  │       OR                 │
  │  Sim Agent B             │
  └──────────────────────────┘
      ↓
SIMULATION OUTPUTS DB
```

**When to use Method 2:**
- Novel questions where the substrate doesn't yet have calibration coverage
- High-stakes decisions where human judgment is required at every step
- Cross-field integration tasks (Test 5 — partner field TBD)
- When training the substrate (Method 2 conversations are particularly rich case captures for compound-through-use)

**Substrate evidence Method 2 produces:**
- Test 1 evidence (specialists answer scoped questions)
- Test 3 evidence (rich case captures from human-led conversations)
- Test 5 evidence (cross-field integration handled with explicit human reasoning)
- Calibration validation (compare substrate confidence to actual outcomes when humans drove)

### Method choice as a runtime decision

The orchestrator does not choose between methods. **The human user does.** Method 1 = "I want the system to drive." Method 2 = "I want to drive, with the system as instrument." The two methods coexist. Both write to the same `SIMULATION OUTPUTS DB` so the substrate accumulates evidence regardless of which method generated it.

### Comparison

| Dimension | Method 1 (Orchestrated swarm) | Method 2 (Human-driven) |
|-----------|-------------------------------|-------------------------|
| Throughput | High | Low |
| Human cognitive load | Low (only at gates) | High (at every step) |
| Best for | Routine analyses, parameter sweeps, literature syntheses | Novel questions, cross-field, exploratory |
| Substrate evidence type | Tests 1, 2, 4 | Tests 1, 3, 5 |
| Calibration data quality | Wide coverage, lower per-case depth | Narrow coverage, deep per-case context |
| Latency | Minutes to hours | Hours to days |
| Trust required | High (substrate must be calibrated) | Low (human is the judge) |

### The "ERP de Ciencia"

The empty placeholder at the top of the architecture sketch labeled "erp ciencia" — this is the long-term integration target. An **ERP for science**: not just an agent system but the cognitive infrastructure that integrates data, agents, simulation outputs, calibration tracking, expert participation logs, and decision history into a coherent operational layer for a research organization.

This is the substrate at maturity. The dual-method architecture above is the seed; the ERP de Ciencia is what it becomes when it accumulates 5–10 years of deployment history across multiple domains.

---

## 7. Agent catalog (substrate-aware)

**Update from v1.1:** Every agent now has a "substrate evidence" line — what evidence it generates for the five validation tests. Generic-utility agents (e.g., literature monitor) without clear substrate evidence are deprioritized.

### Compute & Simulation

- **`sim-orchestrator`** — Runs Runpod batches. *Substrate evidence:* Test 2 (workflow execution), Test 4 (cost/runtime calibration data).
- **`causal-pruner`** — Trains and queries pruning model with active learning. *Substrate evidence:* Test 1 (reasoning over simulation outputs), Test 3 (active learning IS compound-through-use), Test 4 (every prune ranked with confidence).
- **`benchmark-designer`** — Versions digital-organism benchmarks. *Substrate evidence:* Test 4 (benchmarks are calibration ground truth).
- **`fitness-curator`** — Maintains fitness functions. *Substrate evidence:* Test 1 (codifies expert judgment about what "organ-like order" means).

### Wet-Lab & Experiment

- **`experiment-designer`** — Translates pruned recipes to wet-lab protocols. *Substrate evidence:* Test 2 (multi-step workflow with HUMAN GATE), Test 4 (predicts experimental outcome with confidence — calibration test).
- **`bwh-coordinator`** — BWH Aquatics scheduling, IACUC, embryo production. *Substrate evidence:* Limited — operational support agent.
- **`reagent-procurement`** — Tracks DNA/RNA/protein orders, lead times. *Substrate evidence:* Limited — operational support.
- **`imaging-analyst`** — Processes live imaging, scores morphology. *Substrate evidence:* Test 1 (reasoning over imaging data), Test 4 (scoring confidence vs. ground truth).
- **`marker-validator`** — Scores against canonical kidney markers. *Substrate evidence:* Test 1, Test 4 (per-sample identity confidence).

### Data & Omics

- **`scrna-seq-analyst`** — Single-cell RNA-seq pipeline. *Substrate evidence:* Test 1, Test 4.
- **`spatial-omics-analyst`** — Visium/CytAssist spatial. *Substrate evidence:* Test 1, Test 4.
- **`histology-reviewer`** — Tissue architecture scoring. *Substrate evidence:* Test 1, Test 4.
- **`cross-modality-integrator`** — Combines all readouts into the four-success-gate evidence package. *Substrate evidence:* Test 1 (synthesis reasoning), Test 4 (gate-level confidence). **Highest-leverage agent in the system.**

### Knowledge & Strategy

- **`literature-monitor`** — Tracks new papers in organogenesis, causal ML, bioelectric morphogenesis. *Substrate evidence:* Test 1 (relevance ranking is judgment), Test 3 (relevance criteria refine over time).
- **`ip-patent-watcher`** — Patent landscape monitoring. *Substrate evidence:* Limited.
- **`regulatory-ethics-advisor`** — ISSCR / IACUC / IBC compliance gate. *Substrate evidence:* Limited but **mission-critical** (enforces no human embryo work).
- **`domain-knowledge-curator`** — Maintains the project's knowledge base. *Substrate evidence:* Test 3 (curates the substrate that grows).

### Operations & Reporting

- **`program-manager`** — Phase I timeline + budget against milestones. *Substrate evidence:* Limited.
- **`budget-tracker`** — Burn against $297k workstream caps. *Substrate evidence:* Limited.
- **`risk-register-agent`** — Risk tracking + escalation. *Substrate evidence:* Limited.
- **`investor-relations-drafter`** — Monthly investor updates, milestone packaging. *Substrate evidence:* Limited.

### Substrate-specific agents (NEW in v2.0)

These agents exist to instrument the substrate validation tests directly. They have no domain analog — they are pure substrate infrastructure.

- **`calibration-tracker`** — Tags every system output with confidence, records observable outcomes, computes Brier scores, ECE, reliability diagrams. **Owns Test 4 directly.**
- **`evaluation-runner`** — Maintains the held-out 60–80 question evaluation set. Runs it at month 0, 4, 8. **Owns Test 3 measurement.**
- **`case-capture-elicitor`** — Structured elicitation protocol that turns engineer feedback into substrate-quality training data. *Substrate evidence:* Test 3 (the input mechanism for compound-through-use).
- **`cross-field-bridge-agent`** — Recognizes when cross-field framing applies to an organogenesis question, invokes partner-field tools and references appropriately, interprets outputs in developmental biology terms. Partner field TBD (see Section 11). **Owns Test 5 directly.**
- **`reasoning-exposer`** — Wraps any agent output to enforce the structured-output contract: direct answer + confidence + evidence + considered alternatives + gap flags. Enforces Witt's "exposes its reasoning at every step" commitment.
- **`accumulator`** — Method 2-specific. Aggregates outputs from individual specialist agents queried by humans into a coherent thesis. *Substrate evidence:* Test 3 (rich case captures from Method 2 sessions).

---

## 8. Phase plan

### Phase I (months 0–8) — Foundation + first evidence

**Biological:**
- Zebrafish pronephros POC (already scoped above)
- Four success gates measured by month 8

**Substrate:**
- All five validation tests instrumented and running by month 2
- Baseline measurements at month 0
- Midpoint measurements at month 4
- End-of-year measurements at month 8

**Hiring (Phase I):**
- 1 senior ML researcher (calibration / uncertainty quantification)
- 1 senior engineer (agent system reliability)
- 1 part-time cognitive scientist (case-elicitation protocol)
- Existing biomedical engineers continue organogenesis work

### Phase II (year 2) — Mouse + cath lab pilot

**Biological:**
- Translation to mouse kidney development (Boston Children's Mouse Gene Manipulation Core)
- Continued organogenesis substrate evidence accumulation

**Substrate:**
- Cath lab pilot in 1–2 hospitals within Latido's network
- First cross-domain substrate evidence (organogenesis ↔ cardiology)
- Substrate maturity measurements continue

**Capital:**
- Seed round (justified by Phase I substrate evidence + cath lab plan)

### Phase III (year 3+) — Human PSC organoids + cath lab scale

**Biological:**
- Human PSC-derived kidney organoids (Morizane Lab + UCSD HUMANOID + iXCells)
- Translation toward regenerative medicine therapeutics

**Substrate:**
- Multi-domain commercial deployment in cath lab
- Selective autonomous action on routine cases (where calibration coverage supports it)
- Series A justified by accumulated substrate maturity

### Year 5 — Maturity inflection

- Substrate operating commercially in organogenesis (research) + cardiology (clinical)
- Compound-through-use mechanism empirically validated
- Calibration measurably improved across years
- Capital event justified by substrate maturity, not by features

### Year 10 — Cross-field substrate

- Five+ structurally different fields
- Calibration coverage sufficient for selective autonomous action in multiple domains
- Accumulated deployment history is the primary defensibility moat

---

## 9. Hiring profile

The validation tests are simultaneously a **hiring specification**. Strong technical hires who read the test designs will recognize Witt as building on existing research with novel integration work, not as inventing capabilities. The hiring profile this implies:

| Role | Background | Why |
|------|------------|-----|
| **Senior ML researcher** | Calibration / uncertainty quantification (OATML, NYU, Cambridge ML alumni) | Calibration is the substrate's hardest piece — most research investment required |
| **Senior researcher** | Cross-domain or foundation-model integration (Tool Universe alumni or adjacent) | Built systems that orchestrate across heterogeneous knowledge bases |
| **Senior engineer** | Agent system reliability at production scale | Test 2's hardest piece is reliability across multi-step workflows |
| **Cognitive scientist / domain methodologist** | Cognitive task analysis adapted for AI systems | Drives Test 3's case-elicitation protocol — unusual hiring is itself a substrate-quality signal |
| **Existing biomedical engineers** | Latido R&D team (already in place) | Continue organogenesis POC science |

The four-pillar hiring shape signals a substrate company, not a product company.

---

## 10. Risks, honestly characterized

### Technical risk

The substrate's hardest layer is calibration that compounds across prediction types and eventually across fields. Research foundations exist; the integration is novel; full maturity requires years.

**Mitigation:** Hire calibration-focused researchers early. Treat Test 4 as the test most likely to produce uncomfortable results and plan for staged improvement, not first-shot success.

### Deployment risk

Substrate value depends on real expert participation, IP/data governance, academic partnerships, hospital deployment. Many places this can go wrong.

**Mitigation:** Latido's parent-company operational access. Methodical pre-work on partnerships before they need to land. Phase II cath lab work begins formal partnerships now, not at year 2.

### Capital risk

Substrate ventures need longer runway than product ventures. Capital environment for substrate-style AI ventures could degrade.

**Mitigation:** Staged capital structure (SAFE → Seed → Series A) with clear milestones. Phase I substrate evidence is what justifies Seed pricing at substrate-company multiples vs. vertical-AI multiples.

### Existential risk

1. **AI capability inflection reverses or slows.** Foundation model progress was the necessary condition for the substrate framing.
2. **Regulatory environment changes block substrate deployment.** Especially in medicine.
3. **Calibration proves fundamentally unachievable** at the levels the substrate framing requires.

**Mitigation:** Audit discipline throughout. Regular reassessment. Honest characterization of which claims are tempered by which findings.

### What we are NOT claiming (audit discipline)

- We do not claim guaranteed substrate maturity
- We do not claim the four pillars are imminent
- We do not claim cross-field operation works at scale
- We do not claim calibration meets production thresholds out of the box
- We do not claim the substrate framing is the only viable path — we claim it is the most ambitious and best-supported path given current evidence

---

## 11. Open questions

These are unresolved and need attention as the project develops. Update this section as questions get answered (or replaced with new ones).

### Architecture

- [ ] Is `DATA GENERAL INAMOVIBLE` actually a RAG, a knowledge graph, a hybrid, or something else? Decision needed before Phase I month 2.
- [ ] How do Method 1 and Method 2 share state without contaminating each other's evidence streams?
- [ ] What is the structured-output contract that `reasoning-exposer` enforces? Needs concrete schema.
- [ ] Should the `accumulator` agent be Method 2-only or shared between methods?

### Substrate

- [ ] Which calibration approach (temperature scaling, Platt, isotonic, post-hoc, fine-tuning) for Test 4 baseline? Senior ML researcher hire to decide.
- [ ] What is the case-elicitation protocol for Test 3? Cognitive scientist hire to define.
- [ ] How do we handle disagreement between specialist agents in Method 1 (currently no conflict-resolution layer)?

### Domain

- [ ] **Which adjacent biological domain is the Test 5 partner field?** Options: cardiology (max sinergia con cath lab Phase II) or oftalmología (familiarity). Decision needed before Phase I month 2. Senior researcher hire input desirable.
- [ ] Confirmatory analytics partner — SeqMatic or 10x Genomics direct? Cost difference $4k.
- [ ] When does the imaging-analyst agent come online (currently scheduled week 12)? Could be earlier with academic partnership.

### Operations

- [ ] What is the weekly cadence and who attends the integrated review? Currently unspecified.
- [ ] How are agent decisions logged, versioned, and made auditable for substrate-evidence purposes?
- [ ] What does the Phase II → Phase III handoff look like for accumulated substrate evidence?

### Strategic

- [ ] When do we formally bring Witt's substrate framing to investors vs. lead with the organogenesis biology story?
- [ ] What is the academic engagement plan beyond the immediate POC team?
- [ ] How do we evaluate whether Phase I evidence justifies Seed pricing at substrate vs. product multiples?

---

## 12. Glossary

**Audit discipline** — The commitment to honestly characterize what is feasible now, partial, hardest, and unsolved/speculative. Used in all Witt technical communication.

**Calibrated judgment** — Expert reasoning under uncertainty with appropriate confidence levels, based on patterns learned from many cases. Not facts. Not generic knowledge.

**Cath lab** — Catheterization laboratory; interventional cardiology procedure room. Witt's second deployment domain.

**Causal organogenesis** — Computational approach using simulation models that prune over-connected developmental signaling networks to produce coherent organ-formation pathways.

**Chaperone tissue** — Transient signal-emitting tissue patch that delivers minimum developmental cues at the right times to induce a target organ program in adjacent competent tissue.

**Compound-through-use** — Witt substrate's central defensibility mechanism. The substrate accumulates value (calibration data, learned judgment, integrated knowledge) through every deployment, producing a moat that competitors cannot replicate without comparable accumulated history.

**Data general inamovible** — The shared, versioned, read-only knowledge base that feeds both Method 1 and Method 2. May or may not be a RAG.

**ECE** — Expected Calibration Error. Test 4's primary aggregate metric.

**ERP de Ciencia** — The long-term substrate maturity vision. An "ERP for science" that integrates data, agents, simulation outputs, calibration, expert participation, and decision history into operational infrastructure for research organizations.

**Foundation model** — Large-scale language/multimodal model with tool use and retrieval capabilities. The substrate's reasoning layer is built on foundation models.

**Four pillars** — Witt's four eventual value propositions: amplify, transfer, generate, act. None fully testable in the POC year.

**Latido Médico Mexicano** — Witt's parent company. Provides operational substrate access (organogenesis R&D team, cath lab presence in Mexican private hospital network).

**Method 1 (Orchestrated swarm)** — Architecture pattern: orchestrator → specialist swarm → audit → human gate → simulation orchestrator → simulation specialists → audit → human gate → outputs DB.

**Method 2 (Human-driven)** — Architecture pattern: human queries individual specialists → accumulator assembles → human gate → sim agent A or B → outputs DB. No orchestrators.

**MCP** — Model Context Protocol. Standard for connecting agents to tools and data sources.

**POC** — Proof of concept. Phase I of Project Organogenesis (months 0–8).

**Pronephros** — Embryonic kidney in zebrafish; the Phase I biological target.

**Substrate** — Witt's core thesis. Underlying AI capability layer that captures expert calibrated judgment. Distinct from product (vertical) AI tools.

**Test 5 partner field** — The adjacent biological domain (TBD: cardiology or ophthalmology) chosen as the cross-field test partner for Test 5. Replaces the earlier topological-data-analysis (TDA) framing.

**Test 1–5** — The five substrate validation tests: AI capabilities, agent capabilities, iteration loop, calibration tracking, cross-field operation.

**Witt** — The substrate venture. Named after Wittgenstein ("The limits of my language are the limits of my world.").

---

## 13. Document maintenance

This doc is a **living scope document**. It should be updated when:

- A workstream's scope changes (cross-reference Section 4 timeline + Section 8 phase plan)
- An open question gets answered (move from Section 11 to relevant section as a stated decision)
- A new agent is added to the catalog (Section 7) — must include substrate evidence line
- A risk materializes or is mitigated (Section 10)
- The architecture evolves (Section 6 — particularly if Methods 1 and 2 develop sub-patterns)
- A validation test design changes (Section 5)

**Versioning:** Bump the version line at top whenever a structural change is made. Maintain a changelog as Section 14 if iterations get dense.

**Distribution:** This doc is internal-confidential. Vision-forward derivatives (investor decks, partner one-pagers) should be derived from this doc but never claim more than the doc supports. The audit discipline applies to derivatives.

**Consistency check before sharing:** When in doubt, ask whether a claim in the document maps to an audit-disciplined characterization in the source thesis or validation tests. If not, temper the claim.

— End of master scope document v1.0 —
