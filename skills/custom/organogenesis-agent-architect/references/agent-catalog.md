# Agent Catalog — Project Organogenesis

> **When to read this file:** When the user asks "what agents do I need?", uses /catalog, or you need a grounded starting list of agents tailored to the Organogenesis project. Use these as building blocks; cut, combine, or rename them based on the workflow at hand. Don't dump the whole catalog when only a slice is needed.

This catalog is organized by category. For each agent, you get: **purpose**, **owns**, **does NOT own**, **inputs**, **outputs**, **upstream/downstream**, and a **draft frontmatter description** (under 1024 chars, bilingual triggers) that you can refine into a full SKILL.md.

The catalog is opinionated for **Phase I (sub-$300k POC)** by default. Phase II (mouse) and Phase III (human PSC organoids) annotations note where agents extend, swap, or scale.

---

## Quick-Pick Defaults

For common requests, here are the default subsets and patterns. Use these as starting points; customize based on the specific workflow. Don't propose 20 agents to a 4-person Phase I team. Substrate-instrumentation agents are added on top of the domain-agent counts.

| Request | Method | Default agents | Pattern | Slash command |
|---------|--------|---------------|---------|---------------|
| "Plan the simulation → wet-lab loop" | Method 1 | 4–5 domain + reasoning-exposer + calibration-tracker | Iterative refinement + human gate | `/design-system` |
| "Set up the omics confirmation pipeline" | Method 1 | 4 domain + reasoning-exposer + calibration-tracker | Parallel + Aggregator | `/design-system` |
| "Set up Test 5 cross-field partner-field integration" | Method 2 | cross-field-bridge-agent + accumulator + on-demand specialists | Human-driven | `/design-system` |
| "Substrate evidence weekly review" | Hybrid | evaluation-runner + calibration-tracker + risk-register + accumulator + Method 1 inner loop | Method 2 outer / Method 1 inner | `/design-system` |
| "Weekly project ops cadence" | Method 1 | 3–4 ops domain | Event-driven (weekly trigger) | `/design-system` |
| "Lab logistics for Phase I zebrafish" | Method 1 | 3 domain (bwh-coordinator, reagent-procurement, sample-tracker) | Pipeline | `/design-system` |
| "Phase I full system" | Hybrid | 14–16 across 4 supervisors + substrate-instrumentation crosscut | Hierarchical | `/design-system` |
| "Phase II expansion (mouse)" | Hybrid | +3–5 to Phase I (mouse-coordinator, IBC-compliance-checker, mammalian-omics-analyst) | Hierarchical, extend existing | `/design-system` |
| "Single agent for X" | n/a | 1 | Specialist skill | `/generate-skill` |
| "Audit my existing setup" | n/a | n/a (now includes substrate-evidence audit) | n/a | `/audit-architecture` |
| "Audit one SKILL.md" | n/a | n/a | n/a | `/audit-md` |
| "What agents could exist" | n/a | n/a | n/a | `/catalog` |
| "Help me decide Method 1 vs Method 2" | n/a | n/a | n/a | `/method-compare` |
| "Visualize my proposed architecture" | n/a | n/a | n/a | `/diagram` |
| "Check substrate-evidence coverage" | n/a | n/a | n/a | `/substrate-check` |

**Stage caps to respect:** Phase I ≤16 agents (was 14, now 16 to accommodate substrate-instrumentation), Phase II ≤22, Phase III no hard cap. The 4-person virtual biotech that's running Phase I cannot babysit 22 agents.

> **GWT v1.1 Cycle-1 swap (ADR-0008):** `+hypothesis-generator` (Category 4), `−investor-relations-drafter` (suspended in Phase I; recover at the Phase-II financing gate). Net Phase-I active count stays **16**; `ip-patent-watcher` retained (IP moat → C.8). A second slot for the `retrospector` agent is **reserved** (ADR-0009, built Cycle 3, cedes `risk-register-agent` then) — not yet active.

---

## Category 1: Compute & Simulation

### sim-orchestrator

**Purpose:** Plan, launch, monitor, and tear down digital-organism simulation batches on Runpod (or equivalent). Owns the GPU lifecycle for the simulation engine.

**Owns:** Runpod pod selection, batch parameter sweeps, run logs, cost tracking against the ~$2-3k Phase I compute cap, artifact upload to shared storage.

**Does NOT own:** What the simulation is, how to score fitness, what the digital organisms should evolve toward (those are `benchmark-designer` and `fitness-curator`).

**Inputs:** Run config (params, fitness function ref, generations), benchmark spec, budget headroom.

**Outputs:** Run manifest, logs, evolved-organism artifacts, cost report.

**Upstream:** `benchmark-designer`, computational lead.
**Downstream:** `causal-pruner`, `sim-result-analyst`.

**Draft description (~700 chars):**
> "Orquesta corridas de simulación de organismos digitales en Runpod para Project Organogenesis. Planea sweeps, lanza pods, monitorea costos contra el cap de ~$3k de Phase I, y entrega artefactos. Use when someone says: launch a sim batch, run digital organisms, schedule Runpod pods, monitor sim costs, lanzar simulación, correr organismos digitales, programar pods. Also: digital organism evolution, fitness landscape sweep, GPU batch, sim manifest, Runpod budget. Bilingüe."

---

### causal-pruner

**Purpose:** Train and query the causal-pruning ML model that compresses successful digital-organism programs into minimal, timed intervention recipes.

**v2.2 interpretive note (from stress-test):** Magraner et al. (August 2025, arXiv:2508.10777) and Khalid et al. (March 2025) document that LLM-based reasoning over causal/disjunctive structures is among the weakest capabilities in current models. The `causal-pruner` therefore must be operated as a **hypothesis-generation tool, not as a decision-maker**. Each ranking output requires human review before it influences the actual experiment. Mini-benchmark validation against known ground truth is mandatory before deploying the pruner on novel intervention spaces.

**Owns:** Model training loops, active-learning prune-selection policy, intervention ranking output, interpretability artifacts.

**Does NOT own:** The simulation that generates training data (`sim-orchestrator`), the wet-lab translation of pruned programs (`experiment-designer`), **the final decision on which intervention to advance (always human-gated)**.

**Inputs:** Causal benchmark library (from sim runs), target organ program (e.g., pronephros), prior pruning state.

**Outputs:** Ranked intervention recipes (signal set, timing, chaperone-tissue spec), interpretability report, "next most informative prune" suggestion. **All outputs are advisory and require human gate before downstream consumption.**

**Upstream:** `sim-orchestrator`, `benchmark-designer`.
**Downstream:** `experiment-designer` (after human gate), computational lead, founder-scientist.

**Recommended composite pattern (v2.2):** the pruner proposes → a Logic-LM verifier checks internal consistency of the proposal → human reviews and decides. This three-step pattern compensates for the documented weaknesses in LLM causal reasoning.

**Draft description (~750 chars):**
> "Entrena y consulta el modelo de causal pruning para comprimir programas de organismos digitales exitosos en recetas mínimas de intervención (señales, timing, chaperone tissue). Active learning para reducir corridas necesarias. Outputs are advisory only — all rankings require human review before downstream use. Use when: train pruning model, rank interventions, find minimal program, suggest next prune, entrenar pruning, ranking de intervenciones, programa mínimo, próximo prune, comprimir programa. Also: causal pruning, intervention compression, active learning. Bilingüe."

---

### benchmark-designer

**Purpose:** Design and version the digital-organism benchmarks (target structures, fitness functions, perturbation suites) the simulation engine evolves toward.

**Owns:** Benchmark specs, fitness function definitions, perturbation/noise protocols, organ-program target descriptions grounded in real biology (e.g., pronephros field with cohesion + lumen formation).

**Does NOT own:** Running simulations or training the pruner.

**Inputs:** Project goals, biology priors (from `domain-knowledge-curator` or literature), existing benchmark library.

**Outputs:** Versioned benchmark specs, target organ programs, fitness rubrics.

**Upstream:** Founder-scientist, dev-bio adviser, `domain-knowledge-curator`.
**Downstream:** `sim-orchestrator`, `causal-pruner`.

---

### fitness-curator

**Purpose:** Maintain, propose, and stress-test the fitness functions that select for organ-like order (cohesion, compartmentalization, lumenization, reproducibility under noise, repair after perturbation).

**Owns:** Fitness function library, ablation studies on fitness criteria, fitness-vs-phenotype calibration.

**Does NOT own:** The benchmark target structures themselves (`benchmark-designer`).

**Inputs:** Benchmark specs, evolved-organism samples, dev-bio priors.

**Outputs:** Fitness function definitions (code or formal spec), calibration reports.

> Often this can be a sub-skill of `benchmark-designer` rather than a standalone agent in Phase I. Split only when the team grows.

---

### squidiff-in-silico-gate

**Purpose:** Apply Squidiff diffusion model (real pretrained or fine-tuned) as a transcriptomic-prediction gate for hypothesis testing. Produces HUMAN GATE figures and four-state verdicts (PASS / PASS-DECOUPLE / MODERATE / FAIL). Skill implementation: `skills/custom/squidiff-in-silico-gate/`.

**Owns:** Transcriptomic predictions via real Squidiff inference, fine-tuning pipeline for Mode 2 Runpod recipe, cross-verdict consolidation with Morpheus (Mode 3), spurious-convergence detection, synthetic Mode 0 fallback.

**Does NOT own:** Morphological prediction (Morpheus owns it). Wet-lab interpretation (cross-modality-integrator owns it). Multi-agent orchestration (sim-orchestrator owns it).

**Inputs:** scRNA-seq h5ad or CSV, optional Morpheus JSON for cross-verdict, hypothesis description, source/target labels.

**Outputs:** Single HTML figure to `/mnt/user-data/outputs/squidiff-gate-<slug>.html`, metrics JSON to `SIMULATION_OUTPUTS_DB/<hypothesis_id>/squidiff_metrics.json`, cross-verdict JSON when paired with Morpheus, calibration claim record to `substrate_calibration/records/` for Mode 1/3 with checkable outcomes.

**Substrate evidence:** Test 1 (reasoning over simulation outputs — Squidiff is itself an instrumented predictor), Test 4 (every verdict carries calibrated confidence; Pearson r against ground-truth is the calibration ground truth). Limited Test 2 (single-step inference, not a workflow). No Test 3 contribution unless used iteratively across many hypotheses (then yes — calibration drift tracking via the claim record stream).

**Tools / data sources:** `pip install Squidiff`, pretrained weights from `Squidiff_reproducibility` repo, optional Runpod for Mode 2 fine-tuning, optional Morpheus output JSON for Mode 3.

**Triggered by:** Human user invoking `/predict transcriptomic` or equivalent natural-language trigger; sim-orchestrator routing transcriptomic-prediction hypothesis; HUMAN GATE 1 review needing transcriptomic evidence.

**Hands off to:** cross-modality-integrator (when transcriptomic + morphological + wet-lab evidence converge into the gate scorecard); SIMULATION_OUTPUTS_DB (always); HUMAN GATE 1 or 2 (always, with figure as artifact); substrate_calibration/records (Mode 1/3 only).

**Quality gates:**
- Description ≤ 1024 chars (validated 948)
- Honesty statement about transcriptomics vs morphology visible in every output
- Spurious-convergence flag visible when Mode 3 detects it
- Mode 0 confidence capped at 0.50 with watermark
- Transfer-learning distance reported in every Mode 1 verdict
- Claim record written for Mode 1/3 with checkable outcomes

**Failure modes & fallbacks:**
- `pip install Squidiff` fails → fall back to Mode 0 (synthetic proxy) with explicit user notification
- Pretrained checkpoint missing → use nearest available with confidence penalty
- Morpheus JSON missing → emit transcriptomic-only verdict with discount
- Spurious convergence detected → downgrade verdict, do not allow PASS to ship without flag

---

## Category 2: Wet-Lab & Experiment

### experiment-designer

**Purpose:** Translate top-ranked pruned intervention programs into concrete wet-lab interventions (constructs, injection protocols, chaperone-tissue delivery, imaging readouts, marker assays).

**Owns:** Wet-lab protocol drafts, reagent/construct specs, success-criteria definition per experiment, chaperone-patch delivery design.

**Does NOT own:** Lab logistics (`bwh-coordinator`), reagent ordering (`reagent-procurement`), data analysis (`omics-analyst`).

**Inputs:** Ranked intervention recipes from `causal-pruner`, biology priors, available reagents, lab capacity from `bwh-coordinator`.

**Outputs:** Experiment design doc, reagent BOM, success criteria, expected timeline.

**Upstream:** `causal-pruner`, founder-scientist.
**Downstream:** `bwh-coordinator`, `reagent-procurement`, `imaging-analyst`, `marker-validator`.

**Draft description (~700 chars):**
> "Traduce programas de intervención pruned a protocolos wet-lab concretos para zebrafish kidney (Phase I): constructs, inyecciones, chaperone tissue, imaging readouts, marker assays. Use when: design experiment, draft protocol, translate intervention to wet lab, plan injection, diseñar experimento, traducir intervención a wet lab, plan de inyección, protocolo zebrafish. Also: chaperone tissue delivery, pronephros induction, kidney POC. Bilingüe."

---

### bwh-coordinator

**Purpose:** Manage the working relationship with the BWH Aquatics Facility (and equivalent at Phase II/III). Handles scheduling, IACUC compliance, embryo production requests, microinjection slots, imaging support.

**Owns:** BWH calendar, IACUC protocol references, embryo batch requests, lab-side communication thread.

**Does NOT own:** Experiment design (`experiment-designer`), data analysis.

**Inputs:** Experiment plan from `experiment-designer`, BWH availability, IACUC status.

**Outputs:** Booked slots, embryo batch confirmations, status updates, escalation flags.

**Phase II/III scaling:** Becomes `lab-vendor-coordinator` covering BWH + Boston Children's Mouse Gene Manipulation Core (Phase II) + Morizane Lab + iXCells + UCSD HUMANOID (Phase III).

---

### reagent-procurement

**Purpose:** Track DNA/RNA/protein synthesis orders, inducible constructs, reporter-line access, consumables. Manages vendor selection, lead times, and the reagent budget (~$34k in Phase I).

**Owns:** Reagent BOM tracking, vendor orders, lead-time forecasting, reagent inventory at lab sites.

**Does NOT own:** What constructs to design (`experiment-designer`), or budget reallocation across workstreams (`budget-tracker`).

**Inputs:** Reagent specs from `experiment-designer`, vendor catalogs, current inventory.

**Outputs:** Order status, ETA reports, inventory snapshot, budget burn against $34k cap.

---

### imaging-analyst

**Purpose:** Process live imaging data from zebrafish embryos and produce morphology + induction-event scores for downstream review.

**Owns:** Imaging pipelines, segmentation, morphology metrics, time-lapse event detection.

**Does NOT own:** Identity confirmation via markers/omics (`marker-validator`, `scrna-seq-analyst`).

**Inputs:** Raw imaging data from BWH/lab, experiment metadata.

**Outputs:** Morphology scores, time-lapse event maps, candidate-induction flags for finalist selection.

---

### marker-validator

**Purpose:** Score finalist embryos against canonical kidney marker panels (wt1a, pax2a, pax8, hnf1b, etc.) to confirm pronephric/early-kidney identity, not just shape.

**Owns:** Marker assay protocols, scoring rubrics, identity-vs-shape disambiguation.

**Does NOT own:** Imaging-only morphology (`imaging-analyst`), single-cell or spatial omics (`scrna-seq-analyst`, `spatial-omics-analyst`).

**Inputs:** Finalist samples from `imaging-analyst`, marker reference panels, assay results.

**Outputs:** Per-sample identity scores, finalist confirmation report.

---

## Category 3: Data & Omics

### scrna-seq-analyst

**Purpose:** Run and interpret single-cell RNA-seq pipelines on confirmatory finalist samples (Phase I budget: ~$49k for confirmatory analytics, vendor SeqMatic by default).

**Owns:** scRNA-seq pipeline (10x Genomics workflow), QC, cell-type annotation, trajectory analysis, comparison vs. published kidney atlases.

**Does NOT own:** Spatial transcriptomics (`spatial-omics-analyst`), histopathology (`histology-reviewer`).

**Inputs:** Finalist samples, vendor sequencing data from SeqMatic.

**Outputs:** Cell-type annotation report, trajectory plots, identity-confirmation evidence.

**Phase II/III:** Same agent, scales to mouse and human PSC-derived organoid samples without architectural change.

---

### spatial-omics-analyst

**Purpose:** Run Visium/CytAssist or equivalent spatial transcriptomics on finalist samples to confirm spatial organization of induced kidney structures.

**Owns:** Spatial pipeline, gene-expression-in-context analysis, structure-marker co-localization.

**Does NOT own:** Single-cell-only analysis (`scrna-seq-analyst`).

**Inputs:** Spatial data from SeqMatic, paired imaging from `imaging-analyst`.

**Outputs:** Spatial expression maps, co-localization confirmation.

---

### histology-reviewer

**Purpose:** Score histopathology samples for tissue architecture, lumen formation, and structural integrity.

**Owns:** Histology scoring rubrics, IHC interpretation, comparison vs. canonical kidney histology.

**Does NOT own:** Molecular identity (`marker-validator`, `scrna-seq-analyst`).

**Inputs:** Histology slides, IHC results from SeqMatic or equivalent.

**Outputs:** Histology scores, structural integrity report.

---

### cross-modality-integrator

**Purpose:** Combine imaging + scRNA-seq + spatial + histology + marker data into a single per-sample evidence package for the four success gates (Induction, Specificity, Identity, Parsimony).

**Owns:** Cross-modality joins, gate-by-gate evidence scoring, finalist ranking for the investor data package.

**Does NOT own:** Any single modality's analysis (those are the specialist agents).

**Inputs:** Outputs from `imaging-analyst`, `scrna-seq-analyst`, `spatial-omics-analyst`, `histology-reviewer`, `marker-validator`.

**Outputs:** Per-sample evidence package, success-gate scorecard, finalist rankings.

> This is one of the **highest-leverage agents** in the Phase I system. Without it, each modality lives in its own silo and the team has no single source of truth for "did the POC succeed?"

---

## Category 4: Knowledge & Strategy

### literature-monitor

**Purpose:** Track new papers in organogenesis, kidney development, causal ML, bioelectric morphogenesis, and embryo models. Feeds priors back to `benchmark-designer`, `fitness-curator`, and `experiment-designer`.

**Owns:** Search queries (PubMed, bioRxiv, Nature, Science, Cell), relevance scoring, weekly digest generation.

**Does NOT own:** Translating findings into benchmarks or experiments (consumers do that).

**Inputs:** Project topic taxonomy, prior digest history.

**Outputs:** Weekly digest with relevance-ranked papers, alerts on landmark findings.

**Draft description (~600 chars):**
> "Monitorea literatura nueva (PubMed, bioRxiv, Nature, Science, Cell) en organogenesis, kidney development, causal ML, bioelectric morphogenesis, embryo models. Use when: weekly literature review, find new papers on, monitor publications, set up alert for, revisar literatura, papers nuevos sobre, monitorear publicaciones. Also: organoid screens, morphogen timing, pronephros, chaperone induction. Bilingüe."

---

### ip-patent-watcher

**Purpose:** Monitor patent filings adjacent to the Organogenesis platform (extracorporeal support, organoid manufacturing, causal ML for biology, chaperone-tissue delivery) for both freedom-to-operate and competitive intelligence.

**Owns:** Patent search queries (USPTO, EPO, WIPO, Google Patents), filing alerts, claim-overlap flagging.

**Does NOT own:** Filing the project's own patents (founder + counsel) or strategic IP planning.

**Inputs:** Project IP taxonomy, claim watchlist.

**Outputs:** Monthly patent landscape report, urgent overlap alerts.

---

### regulatory-ethics-advisor

**Purpose:** Surface relevant guidelines for any proposed experiment (ISSCR 2025 update for stem-cell embryo models, IACUC for animal work, IBC for genetic manipulation).

**Owns:** Compliance checks against ISSCR / IACUC / IBC, ethics escalation flags, "this proposal would violate X" warnings.

**Does NOT own:** Filing protocols (institutional cores own that), final ethical decisions (humans own that).

**Inputs:** Proposed experiment from `experiment-designer`, current guideline versions.

**Outputs:** Compliance check report, escalation flags.

> **Critical guardrail:** This agent enforces the project's hard line — no human embryo experimentation. Translation to human work goes through PSC-derived organoids only.

---

### domain-knowledge-curator

**Purpose:** Maintain the project's living knowledge base — key biology priors (kidney developmental signaling, BMP/Nodal/RA cascade, wt1a/pax2a/pax8/hnf1b roles), benchmark targets, partner capabilities, decision history.

**Owns:** Knowledge base structure, priors update, source attribution, glossary.

**Does NOT own:** Generating new knowledge (researchers do that), or any analysis output.

**Inputs:** Curated outputs from `literature-monitor`, founder-scientist notes, partner docs.

**Outputs:** Versioned KB, lookup answers, "what we know vs. what we assume" disambiguation.

---

### hypothesis-generator (NEW v1.1, PR-01)

**Purpose:** Generate calibrated, evidence-grounded research hypotheses. Consults the
source-of-truth (verified identifiers + prior artifacts, DATA INAMOVIBLE v1) BEFORE generating,
then complements via MCP / Tool Universe to verify, complete, and check coverage. Each hypothesis
carries supporting AND contradicting evidence (obligatory), a testable prediction, a proposed
experiment, required controls, possible confounders, and calibrated confidence.

**Owns:** Hypothesis generation + the §5 contract per PRE-1 (11→6). Pre-registered prediction +
confidence (honesty clause) for the Reasoning-Improvement Loop.

**Does NOT own:** Ranking for wet-lab commitment (that is `causal-pruner` + HUMAN GATE), the
adopt/reject verdict (human), or writing to the source-of-truth (read-only; writes are
`domain-knowledge-curator` + human gate).

**Inputs:** Seed question (Method 2: human), `resolve_id` / `lookup_prior` results, MCP / Tool
Universe evidence, `domain-knowledge-curator` KB.

**Outputs:** N structured hypotheses (§5 contract); `requires_ethics_review` flag; governance-proposal
triggers (contradiction-section-empty, domain-recall-drop).

**Method:** Method 2 default. **Method 1 only on wet-lab escalation, with a 100% human gate** — a
hypothesis that proposes a wet-lab experiment is ranked-candidate work and routes through
`causal-pruner` discipline + `regulatory-ethics-advisor` + HUMAN GATE; never auto-dispatched.

**Framework:** Self-Consistency (Tier 1) for candidate ranking; Logic-LM (Tier 1, §5) when criteria
are formalizable. `framework_applied` is self-report, not introspection (CLAUDE.md §5).

**Substrate evidence:** Test 3 + Test 4 (direct — each hypothesis is a pre-registered, calibratable
prediction feeding the RIL). Test 1 + Test 2 deferred (`gap_flag`; C.2/C.3 → PR-04/PR-08).

**Reference:** `docs/autoresearch-handoff/research-hypothesis-generation-guide.md` (canonical output
shape + §4 quality rubric), `docs/autoresearch-handoff/proposals/PR-01-hypothesis-generator.md`,
`docs/autoresearch-handoff/prerequisites/contract-11-to-6-mapping.md` (PRE-1).

---

## Category 5: Operations & Reporting

### program-manager

**Purpose:** Coordinate the Phase I 0-8 month timeline against the $297k budget. Tracks milestones, vendor handoffs, sample logistics, weekly review preparation.

**Owns:** Project timeline, milestone tracking, vendor handoff coordination, weekly integrated review prep.

**Does NOT own:** Technical decisions (those route to specialists), budget reallocation (`budget-tracker`).

**Inputs:** Status from all workstream agents, calendar, milestone definitions.

**Outputs:** Weekly status report, milestone slip alerts, handoff readiness checks.

---

### budget-tracker

**Purpose:** Monitor actuals against the $297k Phase I budget by workstream (Sim Engineering $46k, Causal Pruning + Compute $29k, Boston Zebrafish $96k, Constructs/Reagents $34k, Confirmatory Analytics $49k, Program Ops $20k, Contingency $23k). Flag overruns early.

**Owns:** Burn-rate tracking, workstream-level variance, runway calculation, contingency drawdown alerts.

**Does NOT own:** Financial planning beyond Phase I, fundraising (founder).

**Inputs:** Vendor invoices, payroll, compute costs, contingency draws.

**Outputs:** Weekly burn report, variance flags, runway forecast.

---

### risk-register-agent

**Purpose:** Maintain and surface the project's risk register (sim-to-bio transfer, malformed tissue, academic-core access slowdowns, ethics drift, frontier-idea distortion). Asks the team for status per risk on a cadence and escalates when mitigations slip.

**Owns:** Risk register, mitigation status, escalation triggers.

**Does NOT own:** Implementing mitigations (specialists own that).

**Inputs:** Risk definitions from the investor memo, status updates from workstream agents.

**Outputs:** Weekly risk dashboard, escalation alerts.

---

### investor-relations-drafter

> **SUSPENDED in Phase I (GWT v1.1, ADR-0008).** Slot ceded to `hypothesis-generator`. Monthly
> investor-update drafting is manual in Phase I; reinstate at the Phase-II financing gate. Retained
> here for the reactivation criterion. (Substrate evidence: Limited — hence the low-cost cede.)

**Purpose:** Draft monthly investor updates and the milestone data package for the Phase II financing gate. Pulls evidence from `cross-modality-integrator`, `program-manager`, `budget-tracker`.

**Owns:** Investor update drafts, milestone evidence packaging, plain-language framing of technical results.

**Does NOT own:** Final approval (founder), investor relationships themselves.

**Inputs:** Cross-modality evidence, program status, budget status.

**Outputs:** Draft monthly update, draft milestone data package.

---

## Category 6: Substrate Instrumentation (NEW v2.0)

These agents exist specifically to instrument the five Witt substrate validation tests. They have no biological or operational job per se — they exist to produce substrate-quality evidence at every step. **A substrate-aware agent system MUST include at least `reasoning-exposer` and `calibration-tracker` unless explicitly justified.**

See `references/substrate-evidence-guide.md` for detailed evidence requirements per test.

### reasoning-exposer

**Purpose:** Wrap any agent's output to enforce the structured-output contract: direct answer + confidence (0–1) + evidence cited + alternatives considered + gap flags. Enforces Witt's "exposes its reasoning at every step" commitment.

**Owns:** The output schema enforcement. Validation that no agent ships raw prose.

**Does NOT own:** The actual reasoning (that belongs to the wrapped agent).

**Substrate evidence:** Tests 1, 2, 4 (enables them — without structured outputs, none of these tests have data).

**Inputs:** Any agent's draft output.
**Outputs:** Structured-contract-conforming output.

> Often deployed as middleware rather than a standalone callable agent.

### calibration-tracker

**Purpose:** Tag every system output with confidence at output time. Match outcomes when observable. Compute Brier scores, ECE, reliability diagrams quarterly. Decompose by prediction type.

**v2.2 update (from stress-test):** Vega et al. (February 2025) established that biomedical LLM calibration is approximately 30% off-target by default, and that post-hoc correction methods (isotonic regression, histogram binning, Platt scaling) substantially improve calibration but do not perfect it. Two operational consequences are now mandatory:

1. **Apply post-hoc calibration methods from day 1**, not as later optimization. Implementation is straightforward — sklearn provides isotonic regression and histogram binning out of the box. The "model + post-hoc correction" combination is the baseline, not the model alone.

2. **Decompose by objective task category in addition to `framework_applied`.** The framework field is self-reported (per Anthropic April 2025 faithfulness study, see substrate-evidence-guide.md v1.2) and is not a reliable axis for calibration analysis on its own. Decomposition by objective categories (binary classification, ranking, extraction, generation) is more reliable. Use both axes; trust the objective one more.

**Owns:** Test 4 directly. The calibration data stream. **The post-hoc correction pipeline (isotonic regression + histogram binning) is part of this agent's mandatory scope as of v2.2.**

**Does NOT own:** Generating the predictions (specialist agents do that). The choice of advanced calibration approach beyond the standard post-hoc baseline (that requires dedicated investment).

**Substrate evidence:** Test 4 primary; supports Test 3 (calibration improvement is an iteration loop signal).

**Inputs:** Every confidence-tagged output across the system, observable outcome records.

**Outputs:** Quarterly calibration report (months 2, 5, 8 of Phase I), structured in three tiers per the recalibrated Test 4 thresholds (PROJECT_SCOPE.md v1.2):
- **Defensive threshold reached / approached / missed** (ECE < 0.20, achievable target)
- **Ambitious threshold reached / approached / missed** (ECE < 0.10, aspirational target)
- **Per-category decomposition** (calibration broken out by objective task category)

### evaluation-runner

**Purpose:** Maintain the held-out evaluation set (60–80 questions/workflows frozen at month 0). Run it at months 0, 4, 8 to measure substrate performance across the year.

**v2.2 update (from stress-test):** The eval set must be run with **controlled perturbations**, not as a single pass per measurement point. Mirzadeh et al. (October 2024, conclusion not refuted by 2025 work) and Roh et al. (June 2025) document that LLM performance can drop substantially with cosmetic changes to the same problem. A single-pass eval will produce noisy and over-optimistic results.

**Owns:** Test 3 measurement directly. **As of v2.2: the perturbation protocol is part of the runner's mandatory scope.**

**Does NOT own:** Daily operations (the eval set is not part of normal use), or interpreting the results (the team does).

**Substrate evidence:** Test 3 primary, plus robustness signal (which is itself part of evidence quality).

**Inputs:** The frozen evaluation set, the substrate's current state.

**Outputs:** Three measurement snapshots producing the year's improvement trend, **with mean ± standard deviation per question across perturbation classes, plus an explicit flag list for questions that pass some perturbations and fail others.**

**Mandatory perturbation protocol (v2.2):**
- For each question in the eval set, run between 3 and 5 perturbed variants.
- Three perturbation classes are mandatory:
  - **Numerical perturbation** — if the question involves numbers, generate variants with different numerical values that preserve the underlying logic.
  - **Order perturbation** — if the question contains examples, list items, or sub-clauses, reorder them while preserving meaning.
  - **Surface perturbation** — reformulate the same question in 3–5 different ways (direct vs narrative, formal vs casual, etc.).
- Report mean ± standard deviation, not headline accuracy.
- Flag explicitly any question where the model passes some perturbed versions and fails others. These flagged questions are particularly informative for compound-through-use analysis.

> CRITICAL: the evaluation set must be isolated from normal use. Engineers must not encounter these questions in their daily workflow, or the measurement is contaminated.

> COMPUTE NOTE: the perturbation protocol increases evaluation cost approximately 3–5x. Since evaluations are infrequent (3 per year), the total compute impact is manageable.

### case-capture-elicitor

**Purpose:** Structured elicitation protocol that turns engineer feedback into substrate-quality training data. Drives the rich case captures that compound-through-use depends on.

**Owns:** The case-capture protocol. The structured-feedback ingestion path.

**Does NOT own:** What to do with the captures (substrate training pipeline does that), or driving normal work.

**Substrate evidence:** Test 3 primary (the input mechanism for compound-through-use).

**Inputs:** Engineer corrections, ratings, freeform notes during/after agent interactions.
**Outputs:** Structured case-capture records.

> Phase I dependency: the cognitive scientist hire (per hiring profile) defines the elicitation protocol. Until then, use a placeholder protocol but flag as interim.

### cross-field-bridge-agent

**Purpose:** Recognize when a partner-field framing applies to an organogenesis question, invoke partner-field tools and references appropriately, interpret outputs in developmental biology terms. Partner field for Test 5 is TBD (see PROJECT_SCOPE.md Section 11) — most likely an adjacent biological domain (cardiology or ophthalmology).

**v2.2 update (from stress-test):** Test 5 is now explicitly framed as **exploratory in Phase I**, not as a criterion of success. Magraner et al. (August 2025) on knowledge-reasoning dissociation suggests that even when a model possesses knowledge of multiple domains, integration between them is structurally weak in current LLMs. The cross-field bridge is therefore high-uncertainty research, not a deliverable to be optimized against ambitious thresholds. The recalibrated thresholds are in PROJECT_SCOPE.md v1.2.

**Owns:** Test 5 directly. As an exploratory component, it produces preliminary evidence of feasibility — not demonstrations of cross-field operation at scale.

**Does NOT own:** Other cross-field bridges (additional partner fields) until Phase II+ when those domains come online. Method 1 deployment of cross-field reasoning (it stays Method 2 until evidence justifies otherwise).

**Substrate evidence:** Test 5 primary (exploratory); contributes to Test 1 (structured outputs on cross-field questions).

**Inputs:** Organogenesis questions, optional partner-field framing hint from user. Once partner field is decided, the corresponding tools and references become inputs as well.

**Outputs:** Cross-field integrated response with the standard structured-output contract. Each output explicitly tagged as preliminary/exploratory.

> Hard veto: must NEVER produce misleading organogenesis interpretations through partner-field misuse. This is a safety design criterion, not a performance criterion.

> Operating mode: Method 2 only in Phase I. The agent is queried by a human, never autonomously dispatched, until cross-field reasoning has substrate evidence to support reliability.

### accumulator

**Purpose:** Method 2-specific. Aggregate outputs from individual specialist agents (queried in any order by a human) into a coherent thesis. Tracks the human's reasoning trail across the session.

**Owns:** Method 2 thesis assembly + session capture.

**Does NOT own:** Method 1 dispatch (orchestrator does that).

**Substrate evidence:** Test 3 (Method 2 sessions are particularly rich case captures); supports Test 5 when humans are deliberately bridging fields.

**Inputs:** Sequence of specialist outputs from a Method 2 session, plus the human's queries and decisions.
**Outputs:** Coherent thesis document + structured session capture for substrate ingestion.

### composite-auditor (NEW v2.2)

**Purpose:** Replaces the naive single-LLM SI/NO auditor with a composite component that selects an audit method based on output type. Mitigates the cascade-of-failures problem documented in the April 30 stress-test (Anthropic faithfulness 25-39%, Vega calibration ~30% off-target, Mirzadeh/Roh perturbation fragility).

**Background:** the original Method 1 architecture used a single LLM to filter outputs from the specialist swarm before the first human gate. This single-LLM auditor combines simultaneously the three worst-documented LLM problems (poor calibration, questionable faithfulness, perturbation fragility). As a cascade node in a pipeline, its errors propagate forward. v2.2 replaces it with a composite pattern.

**Three operating modes (selected by output type):**

1. **Self-Consistency mandatory mode** — for outputs where a correct answer can be majority-voted. The auditor runs 5–7 instances of the audit judgment in parallel (with temperature > 0) and reports both the majority decision and the agreement rate. If agreement is below threshold (e.g., <70%), the output is automatically escalated to a human gate without filtering.

2. **Logic-LM mandatory mode** — for outputs where the criteria are formalizable (regulatory compliance: IACUC, ISSCR, IBC; budget constraints; timeline constraints; safety constraints). Validation is done with a symbolic solver, not LLM judgment. This produces decisions perfectly calibrated by construction.

3. **Human gate before auditor mode** — for outputs above an impact threshold (decisions affecting budget burn, decisions changing experimental direction). These outputs do not pass through automatic filtering — they go directly to a human.

The original single-LLM auditor reduces to a residual case: only operates on outputs where Self-Consistency does not apply, Logic-LM does not apply, and impact is low. These cases will be few.

**Owns:** Routing logic between the three modes. Threshold definitions for impact escalation. Logic-LM solver integration (Z3 or equivalent).

**Does NOT own:** The decision criteria themselves (those come from compliance documents, scope decisions, and human judgment). The Self-Consistency frequency tuning (that's a Tier 1 framework parameter).

**Substrate evidence:** Tests 1, 2, 4 (the auditor's own decisions are themselves substrate-instrumented, with confidence and framework_applied per the contract).

**Inputs:** Outputs from specialist agents in Method 1 pipelines.
**Outputs:** Routing decisions (which mode is used), filtered outputs (when filtering is applied), escalation packets (when human gate is invoked).

> Implementation note: Self-Consistency mode is multiple parallel calls to the same model — no new infrastructure. Logic-LM mode requires a Python solver dependency (recommend Z3). Human gate mode just signals existing human-review queues.

> Important: this agent represents a **structural shift** in how Method 1 operates. With composite-auditor in place, Method 1 becomes safer to deploy in Phase I — but the recommendation per stress-test Ajuste 6 still holds: Method 1 remains a minority case in Phase I, reserved for low-risk tasks.

---

## How to Use This Catalog

When the user describes a workflow, **map it to the smallest sufficient subset** of this catalog. Don't propose all 26 agents for every request.

**Examples of right-sized subsets (v2.0 — substrate-aware):**

- *"Design the simulation → pruning → wet-lab handoff loop"* (Method 1) → `sim-orchestrator`, `causal-pruner`, `experiment-designer`, `reasoning-exposer` (middleware), `calibration-tracker`, plus a thin `loop-supervisor` orchestrator.
- *"Design the omics confirmation pipeline"* (Method 1, parallel) → `scrna-seq-analyst`, `spatial-omics-analyst`, `histology-reviewer`, `cross-modality-integrator`, `reasoning-exposer`, `calibration-tracker`.
- *"Set up the cross-field partner-field integration for Test 5"* (Method 2) → `cross-field-bridge-agent`, `accumulator`, plus on-demand specialist queries.
- *"Run the substrate evidence weekly review"* (Hybrid) → outer Method 2: human + `evaluation-runner` + `calibration-tracker` + `risk-register-agent` → `accumulator` → human GATE. Inner Method 1: substrate-instrumentation agents ran their batches overnight.
- *"Set up weekly project ops"* → `program-manager`, `budget-tracker`, `risk-register-agent`, optionally `investor-relations-drafter` (monthly cadence).
- *"Phase I full system"* → roughly 14–16 agents (12–14 domain + 2–4 substrate-instrumentation), organized into 4 supervisors (sim, lab, omics, ops) plus the substrate-instrumentation layer that crosscuts.

**When to split or combine:**

- Combine `fitness-curator` into `benchmark-designer` until the fitness library justifies its own owner.
- Combine `spatial-omics-analyst` and `histology-reviewer` into a single `spatial-pathology-analyst` if the volume is low in Phase I.
- Split `bwh-coordinator` into per-vendor coordinators only at Phase II+ when you're juggling 3+ partners.
- Never combine `calibration-tracker` and `evaluation-runner` — they serve different tests with different data lifecycles.

**When to invent new agents:**

- A new partner appears (e.g., a new compute provider, a new omics vendor) → coordinator agent for that partner.
- A new workflow emerges that doesn't map to any catalog entry — propose, justify with evidence (memo quote, transcript, observed need), and name it after the workflow it owns.
- A new cross-field bridge is needed (e.g., Phase II cardiology integration) → new `cross-field-bridge-agent` variant for that field pair.
- Each new agent needs a "Substrate evidence" line. If you can't fill it credibly, the agent might be domain-only and that's fine — just flag it explicitly.

Always end with the audit checklist from `SKILL.md` Phase 6 before delivering.
