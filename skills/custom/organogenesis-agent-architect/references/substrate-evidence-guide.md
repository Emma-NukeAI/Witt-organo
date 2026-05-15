# Substrate Evidence Guide

> **When to read this file:** During Phase 4 (assigning substrate evidence to agents) or when running `/substrate-check`. This file maps each of the five Witt substrate validation tests to which agent behaviors generate evidence for that test.
>
> **Maintenance note:** This file is the *most actively iterating* reference. Update it as the technical team makes calibration decisions, defines case-capture protocols, and refines what counts as substrate evidence. Bump version when updating. Last updated: 2026-05-14 (v1.4 — HTML report contract integration per ADR-0007).

---

## Why this file exists

In Witt's framing, every agent action is also a substrate evidence event. A `causal-pruner` ranking 50 candidate recipes isn't just doing its job — it's producing 50 confidence-tagged predictions for Test 4 calibration tracking, demonstrating Test 1 reasoning capability, and (via active learning) embodying the Test 3 compound-through-use mechanism.

But you don't get this evidence for free. The agent has to be **designed** to produce it. The structured-output contract isn't optional — it's how the substrate evidence stream stays clean.

This file tells you, for each of Tests 1–5, what agent behaviors generate evidence and what data structures need to flow out the other end.

---

## The five tests at a glance

| Test | What it measures | Primary evidence type |
|------|------------------|----------------------|
| **Test 1** | AI capabilities (orchestration + reasoning) | Engineer-rated response quality on a question bank |
| **Test 2** | Agent capabilities (bounded multi-step workflows) | Workflow completion rates, checkpoint accuracy |
| **Test 3** | Iteration loop (compound-through-use) | Performance change on a held-out evaluation set across the year |
| **Test 4** | Calibration tracking | Confidence-vs-actual-accuracy correlation, ECE, reliability diagrams |
| **Test 5** | Cross-field operation | Whether the substrate productively integrates an adjacent biological domain (TBD) with organogenesis |

Full success thresholds in `PROJECT_SCOPE.md` Section 5.

---

## Test 1 — AI capabilities

### What evidence looks like

Each substrate response to a question from the question bank produces a record:

```json
{
  "question_id": "Q-2026-014",
  "question_type": "literature-synthesis | parameter-sweep-design | mechanistic-interpretation | ...",
  "system_response": "...",
  "system_confidence": 0.78,
  "evidence_cited": ["paper_123", "experiment_archive_456"],
  "alternatives_considered": ["...", "..."],
  "gap_flags": ["no recent data on X"],
  "engineer_ratings": {
    "technical_accuracy": 4,         // 1-5
    "workflow_usefulness": 5,
    "surfaced_novel_consideration": true
  }
}
```

### What agents generate Test 1 evidence

Any agent that produces structured outputs to organogenesis questions. Specifically:

- `causal-pruner` — when ranking interventions and explaining why
- `experiment-designer` — when proposing protocols
- `literature-monitor` — when assessing relevance
- `cross-modality-integrator` — when synthesizing across modalities
- `cross-field-bridge-agent` — when reasoning about partner-field framings (also Test 5)
- Any specialist agent in Method 1 or Method 2

### Design requirements

For an agent to produce Test 1 evidence:

1. **Structured output contract enforced** — every response includes the five fields above (answer, confidence, evidence, alternatives, gap flags), now extended in v2.4 with `confidence_by_subclaim` (when applicable) and `agents_invoked` (per CLAUDE.md §5).
2. **Question types tagged** — the agent must declare what category of question it's answering, so aggregate metrics decompose properly.
3. **Engineer-rating capture** — UI or workflow must allow easy 1–5 ratings + freeform notes after each response.
4. **HTML report at conclusion (added v1.4 per ADR-0007).** When the response reaches a conclusion or checkpoint (substantive analytical question with confidence ≥ 0.5, user-signaled end-of-inquiry, phase completion), the response MUST be materialized as a self-contained HTML report in `reports/` following one of the 4 canonical TYPES (A comprehensive analytical, B interactive viz grid, C simulation-backed Three.js, D formal retrospective) per `references/html-report-contract.md`. The structured §5 contract fields MUST appear as **visible UI elements** in the HTML body. **Pure markdown or JSON output does NOT satisfy Test 1 evidence for substrate-instrumented work that reaches a conclusion.** The HTML is the audit trail — it is what makes the reasoning replayable across surfaces and reviewers. CLAUDE.md §5 v2.5 enforces this; composite-auditor verifies compliance by checking each claim record's `session_id` field references an existing HTML file in `reports/`.

### Failure modes

- Agent produces unstructured prose responses → no Test 1 evidence
- Confidence is bolted on after the fact → uncalibrated, useless for Test 4
- Engineer ratings collected only when remembered → biased sample
- Question types not tagged → can't decompose

---

## Test 2 — Agent capabilities

### What evidence looks like

Each multi-step workflow execution produces a record:

```json
{
  "workflow_id": "WF-PROT-023",
  "workflow_type": "parameter-sweep | literature-synthesis | experiment-proposal | ...",
  "started_at": "2026-04-25T14:00:00Z",
  "completed_at": "2026-04-25T15:32:00Z",
  "completion_status": "completed | abandoned | escalated",
  "checkpoints": [
    {"step": 3, "system_asked_for_input": true, "engineer_judged_appropriate": true},
    {"step": 7, "system_asked_for_input": false, "engineer_judged_appropriate": true}
  ],
  "final_output_quality": 4,
  "estimated_manual_time_hours": 6,
  "actual_system_time_hours": 1.5,
  "irreversible_decisions_made_without_checkpoint": false  // MUST be false
}
```

### What agents generate Test 2 evidence

Any orchestrator running a bounded multi-step workflow. Specifically:

- `experiment-designer` — when running the full protocol-drafting workflow
- `causal-pruner` (in active-learning mode) — when running the prune-evaluate-prune loop
- `cross-modality-integrator` — when running the omics-integration pipeline
- Any Method 1 inner loop

### Design requirements

1. **Workflow boundaries explicit** — a "workflow" needs a defined start, end, and success criterion. "The agent helped me think" is not a workflow.
2. **Checkpoint logging** — every time the system pauses for human input (or doesn't), it logs the decision and the engineer rates whether it was the right call.
3. **Irreversibility detection** — the agent must classify each step's reversibility. Irreversible steps (lab dispatch, vendor commitment, irreversible budget allocation) MUST checkpoint. This is a safety criterion, not a performance criterion.
4. **Time tracking** — manual baseline must exist for the time-savings calculation.

### Failure modes

- Workflows treated as "whatever the agent does in a session" → can't measure completion
- Checkpoints inconsistent → checkpoint accuracy meaningless
- Irreversibility judged after the fact → safety criterion violated
- No manual baseline → no time savings claim

---

## Test 3 — Iteration loop (compound-through-use)

### What evidence looks like

Three measurements of the same held-out evaluation set across the year:

```json
{
  "evaluation_set_version": "v1-frozen-month-0",
  "measurement_timestamps": ["2026-04-01", "2026-08-01", "2026-12-01"],
  "primary_accuracy": [0.42, 0.51, 0.59],
  "calibration_confidence_accuracy_corr": [0.31, 0.42, 0.51],
  "completion_rate": [0.65, 0.72, 0.78],
  "engineer_satisfaction": [3.1, 3.5, 3.9],
  "feedback_volume_between_measurements": {
    "corrections_logged": [124, 287],
    "case_captures_logged": [38, 71],
    "calibration_flags_logged": [56, 102]
  }
}
```

Plus, between measurements, accumulated case captures:

```json
{
  "case_id": "CC-2026-0145",
  "captured_by": "engineer_jose",
  "context": "Was reviewing pruner output R-091 and noticed...",
  "what_the_system_did": "...",
  "what_the_engineer_did": "...",
  "what_the_engineer_thought_was_missing": "...",
  "structured_corrections": [...]
}
```

### What agents generate Test 3 evidence

Two distinct sources:

1. **The held-out evaluation set** — managed by `evaluation-runner` (a substrate-instrumentation agent). Frozen at month 0. Never used for any feedback or training during the year.

2. **Case captures from normal use** — every Method 1 cycle and especially every Method 2 session is a potential case capture. Driven by `case-capture-elicitor` (a substrate-instrumentation agent).

### Design requirements

1. **Held-out set frozen and isolated** — engineers must not see these questions during normal work, or the measurement is contaminated.
2. **Case-capture protocol defined** — the cognitive scientist hire (per Phase I hiring profile) drives this. Until that hire is in place, use a placeholder protocol but flag that it's interim.
3. **Feedback typing** — corrections, ratings, case captures, calibration flags are different types of feedback. Track them separately so the team learns which types produce learning.
4. **Three measurement points** — month 0, 4, 8. Don't skip the midpoint; the trend matters more than the endpoints.

### Failure modes

- Held-out set contaminated → no real measurement
- Case captures unstructured → can't be used to improve the substrate
- Feedback types lumped together → can't learn which feedback works
- Only two measurement points → no trend, just a delta

---

## Test 4 — Calibration tracking

### What evidence looks like

Throughout the year, every system output is tagged with confidence. Where outcomes are observable, they're recorded and matched. Quarterly, calibration metrics are computed:

```json
{
  "measurement_period": "2026-Q3",
  "prediction_type": "simulation_outcome_prediction",
  "n_predictions": 287,
  "n_with_observable_outcome": 198,
  "expected_calibration_error": 0.14,
  "brier_score": 0.21,
  "reliability_diagram_data": [...],
  "high_confidence_accuracy": 0.81,
  "trend_vs_previous_quarter": "improving"
}
```

Decomposed by prediction type — aggregate metrics hide important variation.

### What agents generate Test 4 evidence

**Every substrate-instrumented agent.** Test 4 is the most pervasive test — calibration data accumulates from every system output, not from a special set of agents.

The dedicated `calibration-tracker` agent is responsible for:
- Recording confidence at output time
- Matching outcomes when observable
- Computing metrics quarterly
- Producing the decomposed reliability diagrams

### Design requirements

1. **Confidence is mandatory, not optional** — every output structure includes confidence. Default cannot be "unknown" — that's an unobserved data point.
2. **Calibration approach decided early** — temperature scaling, Platt, isotonic, post-hoc on held-out, fine-tuning. The senior ML researcher hire (per hiring profile) decides; document the choice in this file when made.
3. **Outcome observability flagged** — not all predictions have observable outcomes (e.g., "what would have happened if we hadn't run this experiment" is unobservable). Tag observability so calibration is computed only on observable outcomes.
4. **Decomposition by prediction type non-negotiable** — aggregate metrics are misleading. Always report decomposed.

### Failure modes

- Confidence not collected at output time → can't backfill
- Calibration approach chosen after data accumulates → may need to redo
- Unobservable outcomes counted as failures → systematic bias
- Only aggregate metrics reported → misses per-type variation

---

## Test 5 — Cross-field operation

### What evidence looks like

Per cross-field question, a record:

```json
{
  "question_id": "X5-014",
  "organogenesis_question": "Which simulation outputs have structural features most similar to target?",
  "partner_field_relevance_actual": "high",
  "system_invoked_partner_field_tools": true,
  "tools_invoked": ["partner-field-tool-A", "partner-field-tool-B"],
  "invocation_appropriateness": "appropriate",
  "partner_field_output_contributed_to_answer": true,
  "engineer_rated_cross_field_useful": true,
  "introduced_misleading_organogenesis_interpretation": false  // MUST be false
}
```

### What agents generate Test 5 evidence

Primarily one agent: `cross-field-bridge-agent`. This is a substrate-instrumentation agent specifically designed for Test 5.

But Test 5 evidence is enriched when other specialist agents recognize cross-field framings. For example:
- `imaging-analyst` recognizing that partner-field framing is the right way to compare structures
- `cross-modality-integrator` invoking persistent homology to find stable features across iterations

### Design requirements

1. **Partner-field tools available** — TBD based on partner field choice (cardiology, ophthalmology, etc.). Not pre-trained on the bridge between the partner field and developmental biology.
2. **Question set deliberate** — 15–20 questions designed to be amenable to partner-field framing, not random. Don't measure cross-field on questions where partner-field framing is irrelevant.
3. **Safety criterion enforced** — the system must NEVER introduce misleading organogenesis interpretations through partner-field misuse. This is a non-negotiable design criterion. Set a hard veto.
4. **Engineer judgment captured** — was the cross-field integration *useful*, not just *invoked*? These are different.

### Failure modes

- System invokes partner-field tools on every question → no measurement of relevance recognition
- Pre-trained on the bridge → measures bridge-training quality, not native cross-field capability
- Misleading interpretations not flagged → safety criterion violated, evidence corrupted
- Engineer ratings reduced to binary "good/bad" → loses appropriateness vs. usefulness distinction

---

## Substrate-instrumentation agents — what they exist for

These six agents exist *specifically* to instrument the substrate validation tests. They have no biological or operational job — they exist to produce substrate evidence.

| Agent | Owns | Primary tests served |
|-------|------|---------------------|
| `calibration-tracker` | Confidence tagging, outcome matching, ECE + Brier + reliability diagrams | Test 4 |
| `evaluation-runner` | Held-out evaluation set, three-times-yearly measurements | Test 3 |
| `case-capture-elicitor` | Structured elicitation protocol for engineer feedback | Test 3 |
| `cross-field-bridge-agent` | Recognizing partner-field relevance, invoking partner-field tools, interpreting outputs in domain terms | Test 5 |
| `reasoning-exposer` | Wrapping any agent's output in the structured contract (answer + confidence + evidence + alternatives + gaps) | Tests 1, 2, 4 (enables them) |
| `accumulator` | Aggregating Method 2 specialist outputs into a coherent thesis | Test 3 (rich case captures) |

**A substrate-aware agent system MUST include at least the `reasoning-exposer` and `calibration-tracker` agents** unless explicitly justified otherwise. Without them, the system might do its biological job but produces no substrate evidence — and Witt is built on substrate evidence.

---

## Substrate-evidence audit checklist

When auditing an agent system (Mode B or `/substrate-check`):

- [ ] Each agent has a "Substrate evidence" line in its role spec, naming which tests it contributes to
- [ ] Test 1 evidence: at least 2 specialist agents producing structured outputs
- [ ] Test 2 evidence: at least 1 multi-step workflow with explicit checkpoints
- [ ] Test 3 evidence: `evaluation-runner` and `case-capture-elicitor` are present and have inputs from real usage
- [ ] Test 4 evidence: `calibration-tracker` is present, confidence is mandatory in every output
- [ ] Test 5 evidence: `cross-field-bridge-agent` is present (or explicitly deferred to Phase II+)
- [ ] `reasoning-exposer` is wired to enforce the structured-output contract (or every agent enforces it natively)
- [ ] No agent in the system fails to declare which substrate evidence it produces (even if the answer is "none — this is operational support")

---

## Mapping back to the project scope

This file should be read alongside `PROJECT_SCOPE.md` Section 5 (the five substrate validation tests). The scope doc is the strategic framing; this file is the agent-design-level operationalization. When they conflict, the scope doc wins — update this file to match.

---

## Reasoning Frameworks as Transversal Evidence (v1.1)

Reasoning frameworks (Chain-of-Thought, Tree-of-Thought, Self-Discover, Self-Consistency, Logic-LM, Inversion, First-Principles, Chain-of-Verification, etc.) are not a separate test. They are **a transversal evidence stream** that enriches the existing tests. See `references/reasoning-frameworks-catalog.md` for the full catalog.

### How frameworks integrate with the five tests

| Existing test | What framework usage adds |
|---------------|--------------------------|
| **Test 1** (AI capabilities) | Each framework invocation is a Test 1 data point. Outputs that surface "things the engineer wouldn't have produced" are often a function of which framework was applied. Decompose Test 1 results by framework to learn which frameworks earn the highest engineer ratings on which question types. |
| **Test 2** (agent capabilities) | Multi-step frameworks like ToT, Self-Discover, and CoVe ARE multi-step workflows. Their internal checkpoints become Test 2 evidence about whether the agent can execute structured reasoning autonomously. |
| **Test 3** (iteration loop) | Framework-specific calibration improvements over the year are some of the richest Test 3 signals. If CoT calibration improves but ToT stagnates, that tells us where compound-through-use is working and where it isn't. Case captures should always include `framework_applied`. |
| **Test 4** (calibration) | Calibration must be decomposed by framework, not just by prediction type. A system might be well-calibrated when using Self-Consistency but poorly calibrated when using Self-Discover. Aggregate calibration metrics that hide this are misleading. |
| **Test 5** (cross-field) | The cross-field test partner is TBD (see PROJECT_SCOPE.md). Whatever it ends up being, the framework dimension applies: does CoT used in organogenesis transfer productively to the partner field? Does Inversion? This is where framework-level transferability becomes empirical. |

### Operational requirement

Every output from any substrate-instrumented agent must populate `framework_applied` in the structured output contract. This is the new mandatory field added in v1.1:

```json
{
  "answer": "...",
  "confidence": 0.78,
  "evidence_cited": [...],
  "alternatives_considered": [...],
  "gap_flags": [...],
  "framework_applied": "tree-of-thought"   // NEW v1.1
}
```

The `reasoning-exposer` agent enforces this. Outputs without `framework_applied` are rejected before downstream consumption. The `calibration-tracker` agent decomposes calibration metrics by framework, not just by prediction type.

### What this changes operationally

- **No new test.** Framework evidence enriches Tests 1–5.
- **New required field.** `framework_applied` is mandatory in the structured-output contract.
- **New decomposition axis.** Calibration metrics decompose by framework AND by prediction type (instead of just by prediction type).
- **No new agents.** The reasoning-exposer and calibration-tracker absorb the new responsibility. No need for a `framework-selector` agent — Self-Discover (one of the catalog frameworks) handles meta-framework-selection inside any agent that needs it.

### Failure modes

- **Framework field empty or "none"** → cannot analyze framework-level evidence; treated as audit failure
- **Same framework declared for every output** → either the agent isn't actually selecting, or the catalog is too small for the agent's needs
- **Framework declared but reasoning shape doesn't match** (e.g., "tree-of-thought" declared but no branching in the output) → audit catches this in random sampling; agent flagged for retraining

---

## Critical interpretation update (v1.2 — derived from 2025+ evidence stress-test)

The April 30, 2026 evidence stress-test surfaced findings that change how `framework_applied` and several other substrate fields must be interpreted. These are **not changes to the structured-output contract itself** — the fields remain the same — but they change what the fields mean and how downstream analysis should treat them.

### `framework_applied` is self-report, not introspection

Anthropic published a faithfulness study in April 2025 demonstrating that modern reasoning models (including Claude 3.7 Sonnet and DeepSeek R1) only declare honestly the influences on their reasoning between 25% and 39% of the time. The implication is direct:

**The `framework_applied` field is a self-reported declaration by the agent of what reasoning framework it intended to apply when producing the output. It must NOT be interpreted as faithful introspection of the model's internal process.**

Operational consequences:

- The field remains useful for decomposing evidence by framework category (it correlates partially with the actual process).
- The field is NOT useful for auditing whether the model "actually" used the declared framework. Outcome verification is the only reliable audit signal.
- The field should NOT be the basis of claims about framework-specific transferability between domains. Such claims require additional verification beyond the self-report.
- Any external communication of substrate findings that depends on this field must explicitly name this limitation.

The `reasoning-exposer` agent continues to enforce that the field is populated. The `calibration-tracker` agent continues to decompose calibration by framework. But the interpretation layer must be aware that decomposition by self-reported framework is informative, not definitive.

### Calibration is harder than the original Test 4 thresholds suggested

Vega et al. (February 2025, bioRxiv doi:10.1101/2025.02.11.637373) established baselines for biomedical calibration: ~30% off-target across nine models and thirteen datasets. Post-hoc methods (isotonic regression, histogram binning, Platt scaling) improve calibration but do not reach single-digit Expected Calibration Error without tailored investment per task type.

Implication for the `calibration-tracker` agent:

- Apply post-hoc calibration methods (isotonic regression, histogram binning) from day one of the evaluation pipeline. Do not treat them as "later optimization."
- Decompose calibration metrics by **objective task category** (binary classification, ranking, extraction, generation) in addition to by `framework_applied`. The objective decomposition is more reliable than the self-reported framework decomposition.
- Report calibration in three tiers when surfacing findings: defensive threshold reached / ambitious threshold approached / per-category breakdown — not a single aggregate number.

The detailed threshold recalibration is in PROJECT_SCOPE.md Section 5 (Test 4).

### Evaluation must be perturbation-resistant

Mirzadeh et al. (October 2024, arXiv:2410.05229, conclusion not refuted by 2025 work) and Roh et al. (June 2025) document that LLM performance can drop substantially with cosmetic perturbations: changing only the numerical values, reordering the examples in the prompt, or reformulating the same question in narrative form.

Implication for the `evaluation-runner` agent:

- Each batch of the eval set must be run **multiple times with controlled perturbations**, not as a single pass.
- Three perturbation classes are mandatory:
  - **Numerical perturbation:** if the question involves numbers, generate variants with different numbers
  - **Order perturbation:** if the question has examples or list items, reorder them
  - **Surface perturbation:** reformulate the same question in 3–5 different ways
- For each question, run between 3 and 5 perturbed versions and report mean ± standard deviation, not just the headline number.
- Flag explicitly when the model passes some perturbations but fails others on the "same" question.

This converts the eval set from a measure of capability into a measure of robustness — which is what the substrate actually needs to demonstrate.

### Framework hierarchy in the catalog

The April 30 stress-test identified that not all eight frameworks in the catalog have equivalent evidence backing. Self-Consistency and Logic-LM are sustantialy more robust than the others according to 2025+ literature. This is reflected in `reasoning-frameworks-catalog.md` v1.1 with a three-tier hierarchy. Agents that invoke a framework should prefer Tier 1 frameworks when their domain applies.

### Connection to PROJECT_SCOPE.md

The substrate validation tests (Tests 1–5) retain their conceptual definitions. Their thresholds have been recalibrated in PROJECT_SCOPE.md v1.2 to be defensively reachable + ambitionally aspirational, rather than single ambitious numbers. This is a documentation change, not a substrate redesign.

---

## Substrate-level findings — mandatory section in every substrate-instrumented report (added v1.3)

Every substrate-instrumented report (any output that contributes Test evidence) MUST end with a "Substrate-level findings" subsection before the bibliography / references / footer. This is what makes the substrate accumulate transferable insight across sessions.

**What goes in this section.**

Substrate-level findings are observations about how the substrate behaved during the work, NOT the biological conclusions. Examples from real sessions:

- *"Pre-resolves can catch experimental design flaws before wet-lab"* — a transferable pattern, not a biology fact.
- *"Tier systems must incorporate specificity, not just presence"* — a methodology correction.
- *"External ID verification is non-negotiable"* — a hard-rule candidate (now codified as CLAUDE.md §7 9th rule).
- *"Honest pivots on infrastructure failures preserve productivity"* — a resilience pattern.
- *"Squidiff Mode 0 confidence cap prevents overclaiming"* — a substrate-integrity pattern.

**Template:**

```markdown
## Substrate-level findings

What we learned about the substrate (not the biology) during this work. Each finding is a transferable observation — applies beyond this session.

### Finding N: <one-line summary>
<2-3 sentence elaboration. Evidence: <what was observed>. Transferability: <where else this applies>.>

(Repeat per finding. Typical range: 3-8 findings per substantive report.)
```

**Why this is mandatory.**

Without a dedicated section, substrate-level lessons get lost when the document is closed. The 2026-05-09 meta-analysis captured 8 such findings retroactively — every one of those should have been generated by the report at the time, not retrospectively. Mandatory inclusion solves this.

**Skills bound to this requirement:** all substrate-instrumented skills, including `organogenesis-agent-architect`, `causal-ablation-cascade-sim`, `squidiff-in-silico-gate` (which adds its findings about transcriptomic prediction confidence vs ground truth, transfer-distance impact, spurious-convergence detections, etc.), and any future custom skills.

**Substrate evidence:** Test 3 (iteration loop) primary — these findings are the cases the loop trains on.

---

— End of substrate-evidence-guide.md v1.4 —

**v1.4 changes vs v1.3 (2026-05-14, ADR-0007):**
- Test 1 §Design requirements: added item 4 — HTML report mandatory at conclusion with visible §5 contract UI; 4 TYPES defined in companion `html-report-contract.md` v1.0.
- Aligns with CLAUDE.md §5/§7/§11 v2.5 (HTML emission rule + simulation-backed-viz hard rule + visual-offer reflex).
- Test 1 evidence now requires HTML, not just structured output records — the HTML body IS the audit trail. Pure MD/JSON outputs are insufficient for substrate-instrumented work that reaches a conclusion.
