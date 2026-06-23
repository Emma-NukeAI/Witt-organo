# Reasoning Frameworks Catalog

> **When to read this file:** When designing an agent that needs to reason explicitly (not just respond), when populating the `framework_applied` field in a structured output, or when planning what reasoning capabilities the substrate covers. Also read this when a new framework appears in the literature and you need to decide whether to add it.
>
> **Maintenance note:** This is the **most actively iterating reference in the skill**. The starter catalog has 8 frameworks; expect to grow to 20–40 over the POC year. Bump version when adding/removing frameworks. Last updated: 2026-05-13 — **v1.2** adds specificity-aware **candidate-ranking Tier system** (distinct dimension from framework-tier taxonomy; do not conflate). v1.1 (2026-04-30) introduced tier hierarchy from stress-test findings.
>
> **v1.2 changelog (2026-05-13, generated during recalibration):**
> - Added "Candidate-ranking Tier system (specificity-aware)" as a separate dimension from the framework-tier taxonomy. The mafba case study from 2026-05-09 documented as worked example.
> - Naming clarification: existing Tier 1/2/3 refers to reasoning frameworks (Self-Consistency, Logic-LM, CoT, etc.). The new section refers to candidate ranking. These are distinct uses of "Tier" and must not be conflated.
> - Added skill-specific binding for `squidiff-in-silico-gate`: Logic-LM is the preferred framework when decouple criteria are formalizable (boolean predicates over transcriptomic readouts). Self-Consistency is appropriate when the verdict requires probabilistic majority voting across uncertain operations (e.g., novel-drug Mode 5 with high transfer-learning distance).

---

## Why this file exists

Witt's substrate captures expert calibrated judgment. Part of expert judgment is *how* an expert reasons — not just what they conclude. Operationalizing reasoning frameworks (Chain-of-Thought, Tree-of-Thought, Self-Discover, Inversion, etc.) makes this captureable, calibratable, and transferable across domains.

The frameworks live inside the substrate's reasoning layer (per Witt's technical foundations, Section 5 of the thesis). They are not a separate hierarchy. They are the operational building blocks of the reasoning the substrate exposes.

**The Latticework analogy.** Munger's latticework is a curated set of mental models that an expert can invoke depending on the problem. This catalog is the computational equivalent: a curated set of reasoning frameworks that an agent can invoke depending on the question. Same idea, different substrate.

**Operating principle (from Martín, April 29):** *"hay que probar."* Each framework here is operationalized to the level needed for first invocation. Sophisticated calibration of when each framework works best is something the system learns through use, not something this catalog pretends to know up front.

---

## How frameworks are operationalized

Each framework in the catalog has the same structure:

- **What it is** — One-paragraph description, plain language.
- **When to invoke** — Question types or signal patterns where this framework helps.
- **When NOT to invoke** — Anti-patterns; cases where this framework misleads more than it helps.
- **How an agent applies it** — Operational shape (prompt structure, multi-step pattern, tool invocation).
- **Substrate evidence generated** — Which validation tests this framework's invocation contributes to.
- **Organogenesis worked example** — Concrete example of the framework applied to a real POC question.
- **Origin / reference** — Where the framework comes from in the literature (Awesome-LLM-Reasoning catalog or classical mental-model literature).

Every agent output in the system that involves reasoning must populate the `framework_applied` field of the structured-output contract with the name of the framework used (e.g., `"framework_applied": "tree-of-thought"`). The `reasoning-exposer` agent enforces this.

---

## The starter catalog (v1.2)

**Important interpretation update (v1.1, derived from April 30, 2026 stress-test):** the eight frameworks below are organized into three tiers based on the strength of 2025+ literature backing them. When agents need to select a framework for a task, they should prefer Tier 1 frameworks within their domain of applicability. Tier 2 frameworks are useful with awareness of documented limitations. Tier 3 frameworks are heuristics without rigorous LLM-specific literature — defendable as prompting practice but not as evidence-backed methods.

### Tier 1 — Default when applicable (strongest 2025+ evidence)

These two frameworks have the most robust empirical backing in 2025 literature for their respective domains. They should be the first choice when their domain of applicability is matched.

- **Self-Consistency** — for any task where multiple runs can be majority-voted; agreement rate doubles as confidence signal. Used by Vega et al. (Feb 2025) as one of three successful confidence-scoring strategies in biomedical calibration.
- **Logic-LM (Symbolic Verification)** — for any task whose criteria are formalizable; produces results perfectly calibrated by construction. The only framework in the catalog that bypasses the brittleness/faithfulness/calibration problems documented in 2025+ literature, because the verification step is symbolic, not neural.

### Tier 2 — Use with awareness of limitations (mixed 2025+ evidence)

These frameworks remain useful but have documented limitations that must be considered when interpreting their outputs.

- **Chain-of-Thought (CoT)** — useful as prompting structure, but per Anthropic April 2025, the chain produced is not a reliable window into the model's actual reasoning. Use for output structure, not for auditability.
- **Chain-of-Verification (CoVe)** — favored by 2025 literature for high-stakes outputs, but Su et al. (May 2025) shows that excessive verification degrades performance on simple problems. Context-dependent.
- **Tree-of-Thought (ToT)** — promising for exploratory problems, but Khalid et al. (March 2025) on disjunctive reasoning failures suggests caution: the multi-branch structure exposes the model to exactly the type of reasoning where 2025 literature documents systematic failure.
- **Self-Discover** — limited 2025+ literature on top of the original 2024 paper. Maintain for novel problem types but monitor.

### Tier 3 — Prompting heuristics (no rigorous LLM-specific literature)

These are mental-model heuristics borrowed from non-LLM contexts. They are defensible as prompting practice but lack rigorous LLM-specific empirical validation. Mark them as such when used.

- **Inversion (Munger / Jacobi)** — risk-assessment heuristic. No 2025+ LLM-specific studies.
- **First-Principles Reasoning** — assumption-stripping heuristic. No 2025+ LLM-specific studies.

### The frameworks themselves

The detailed operational definitions for each of the eight frameworks follow. The tier classification above governs which to prefer in agent design; the definitions below remain unchanged from v1.0.

---

### 1. Chain-of-Thought (CoT) — Tier 2

**What it is:** The agent produces an explicit sequence of intermediate reasoning steps before reaching a conclusion. Instead of jumping from question to answer, it externalizes the work.

**When to invoke:**
- Multi-step problems where intermediate state matters
- Mathematical or quantitative reasoning
- Cases where the engineer needs to audit the reasoning, not just the conclusion

**When NOT to invoke:**
- Simple lookup questions ("what is the BWH IACUC contact?")
- Cases where the answer is already known from a single source
- High-volume routine outputs where verbosity is overhead

**How an agent applies it:** Wrap the reasoning prompt with "Let's think step by step" or equivalent structured prompting. Output includes the intermediate steps, not just the answer.

**Substrate evidence generated:**
- Test 1 (response surfaces reasoning the engineer wouldn't have produced)
- Test 4 (each intermediate step can be confidence-tagged)

**Organogenesis worked example:** Agent `causal-pruner` ranks intervention recipes. With CoT: "First, the candidate prunes BMP at t+18h. BMP suppression at this stage typically delays mesodermal commitment. Given the target is pronephric induction at t+30h, this timing leaves room for the RA pulse to act on uncommitted intermediate mesoderm. Therefore the candidate scores high on biological plausibility despite a lower in-silico score." Without CoT: "Candidate ranked 4/10."

**Origin:** Wei et al., *Chain of Thought Prompting Elicits Reasoning in Large Language Models* (NeurIPS 2022).

---

### 2. Tree-of-Thought (ToT) — Tier 2

**What it is:** The agent explores multiple reasoning paths in parallel, evaluates partial paths, and prunes unpromising branches before committing to a final answer. Like CoT but branching.

**When to invoke:**
- Problems with multiple plausible approaches
- Exploratory questions where the right framing isn't obvious
- Cases where committing to the first reasoning path is risky

**When NOT to invoke:**
- Time-critical responses where exploration overhead isn't justified
- Problems with a single clearly correct approach
- Cases where the engineer already specified the framing

**How an agent applies it:** Generate 3–5 reasoning candidates for the first step, evaluate each, pick the most promising, repeat for next step. Track the rejected branches in the gap-flags field of the output.

**Substrate evidence generated:**
- Test 1 (alternatives considered field is naturally populated)
- Test 4 (per-branch confidence is rich calibration data)
- Test 3 (the explored-but-rejected branches are particularly rich case captures for compound-through-use)

**Organogenesis worked example:** `experiment-designer` is asked to design a wet-lab protocol from a pruned recipe. ToT explores three approaches in parallel: (a) standard injection at single-cell stage, (b) localized chaperone-tissue transplant at gastrulation, (c) inducible construct activated at intermediate mesoderm formation. Each is scored for technical feasibility, lab-time cost, and signal-to-noise. (b) wins; (a) and (c) are logged as alternatives.

**Origin:** Yao et al., *Tree of Thoughts: Deliberate Problem Solving with Large Language Models* (NeurIPS 2023).

---

### 3. Self-Discover — Tier 2

**What it is:** Before solving a problem, the agent first selects which reasoning operations to apply (e.g., decomposition, abstraction, comparison) and composes them into a tailored reasoning structure. Meta-reasoning before reasoning.

**When to invoke:**
- Novel problem types the agent hasn't seen before
- Problems where the right reasoning shape isn't pre-known
- Cases where you want the agent to *justify* why it reasoned the way it did

**When NOT to invoke:**
- Routine problems where reasoning overhead isn't worth it
- Time-critical responses
- Cases where a fixed reasoning template is known to work

**How an agent applies it:** Two-pass process. Pass 1: agent picks 3–5 reasoning operations from a menu (decompose, abstract, analogize, invert, etc.). Pass 2: agent applies the chosen operations in sequence.

**Substrate evidence generated:**
- Test 1 (response includes meta-reasoning about reasoning, often surfaces things the engineer didn't have)
- Test R1 (this framework is itself an instance of substrate-level framework selection)

**Organogenesis worked example:** A novel question arrives: "If we observe morphology pattern X in the simulation but the corresponding wet-lab embryos look like Y, what alternative interpretations exist?" Self-Discover picks: (a) decompose (separate sim-side and bio-side mismatches), (b) analogize (find similar discrepancies in the literature), (c) invert (what would have to be true for the simulation to be right and the wet-lab to be wrong?). Then applies them.

**Origin:** Zhou et al., *Self-Discover: Large Language Models Self-Compose Reasoning Structures* (Preprint 2024).

---

### 4. Self-Consistency — Tier 1 (preferred)

**What it is:** Sample multiple reasoning paths to the same question with temperature > 0, then take the majority answer. Reduces single-shot reasoning errors.

**When to invoke:**
- High-stakes outputs where one reasoning attempt might fail randomly
- Numerical or factual questions where consistency is checkable
- Calibration measurement (the agreement rate across samples is itself a confidence signal)

**When NOT to invoke:**
- Routine outputs where 5x compute cost isn't justified
- Open-ended creative tasks where divergence is the point
- Problems where the answer space is continuous and "majority" is meaningless
- **Cross-lens validity asymmetry without diversification** — when the candidates differ in the VALIDITY of the evidence behind them (e.g., one supported by native-species loss-of-function, another only by cross-species ortholog PPI), an identical-prompt panel will amplify a SHARED bias and reach a confident-but-wrong consensus. Documented failure: the 2026-06-22 E2E test, where 5/5 rankers voted "Wnt (inducer)" on ortholog-PPI evidence while the strongest native evidence (RA) was for a different role (composite-auditor REVISE; ADR-0028).

**How an agent applies it:** Generate N (typically 5–10) reasoning paths at temperature ~0.7. Take majority for discrete answers; take median or weighted average for numerical. Report the agreement rate as the confidence estimate. **(ADR-0028) When candidates rest on evidence of differing validity, (a) make the panel PERSPECTIVE-DIVERSE — assign each ranker a distinct lens/prior rather than an identical prompt — and (b) pass the result through `substrate_calibration/tools/evidence_weighting.py` (`rank_with_lens_validity`), which re-scores by lens-validity tier and raises `overclaim_flag` when the raw-top candidate is ortholog/membership-only while another carries native evidence. A flag routes to a role-split + human gate, never a single-winner claim.**

**Substrate evidence generated:**
- Test 4 directly (agreement rate is a natural confidence proxy and can be calibrated against actual accuracy)

**Organogenesis worked example:** `marker-validator` scores a finalist embryo against the kidney marker panel. Run 7 independent scoring passes; 6 agree on "renal identity confirmed." Report confidence 0.86 (= 6/7). If 4/7 agree, report confidence 0.57 — and route to human review.

**Origin:** Wang et al., *Self-consistency improves chain of thought reasoning in language models* (ICLR 2023).

---

### 5. Logic-LM (Symbolic Verification) — Tier 1 (preferred)

**What it is:** Translate the natural-language problem into formal symbolic logic, run a solver, translate back. Combines LLM language understanding with deterministic logical guarantees.

**When to invoke:**
- Constraint-satisfaction problems
- Compliance checks (IACUC, IBC, ISSCR rules)
- Problems where the answer must be provably correct, not just plausible

**When NOT to invoke:**
- Open-ended reasoning where formalization is forced
- Problems where the symbolic translation overhead exceeds the benefit
- Cases where ambiguity is the actual content

**How an agent applies it:** (1) Translate the question into first-order logic or SAT/SMT form. (2) Hand to solver (Z3, Prolog, or equivalent). (3) Translate solver output back to natural language with the deterministic guarantee preserved.

**Substrate evidence generated:**
- Test 1 (high-confidence outputs are *provably* high-confidence, distinct from foundation-model overconfidence)
- Test 4 (Logic-LM outputs are perfectly calibrated by construction — useful baseline)

**Organogenesis worked example:** `regulatory-ethics-advisor` checks a proposed protocol. Translates the protocol elements and the ISSCR/IACUC rules into formal predicates. Solver returns: "All constraints satisfied" or "Constraint X violated by element Y." No ambiguity.

**Origin:** Pan et al., *Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning* (EMNLP 2023 Findings).

---

### 6. Inversion (Munger / Jacobi) — Tier 3 (heuristic)

**What it is:** Instead of asking "how do we make X succeed?", ask "what would guarantee X fails?" Then avoid those things. Classical mental model from Carl Jacobi via Charlie Munger.

**When to invoke:**
- Risk assessment and pre-mortems
- Problems where success criteria are vague but failure modes are clear
- Cases where direct optimization keeps producing the same wrong answer

**When NOT to invoke:**
- Constructive design tasks where forward-thinking is needed
- Cases where you have no information about either success or failure modes
- Problems where the failure space is unbounded

**How an agent applies it:** Reframe the original question as its inverse. Generate failure modes. Rank by probability and impact. Invert again to extract the "do this to avoid that" recommendations.

**Substrate evidence generated:**
- Test 1 (inversion frequently surfaces considerations the engineer didn't have)
- Test 3 (inversion-derived failure modes are particularly rich case captures)

**Organogenesis worked example:** `risk-register-agent` is asked "what could derail Phase I?" Inversion: "what would guarantee Phase I fails?" — Generates: BWH access slips, calibration approach proves wrong, founder-scientist gets pulled into Latido fire-fighting, sim-to-bio gap exceeds budget, ethics drift toward human embryo work, wrong cross-field partner field chosen. Ranks. Inverts back to mitigation tasks for each.

**Origin:** Carl Jacobi (mathematics, 19th century), popularized by Charlie Munger. In the Latticework: see "Inversion" under Mathematics.

---

### 7. First-Principles Reasoning — Tier 3 (heuristic)

**What it is:** Decompose a problem to its fundamental, uncombinable truths and rebuild reasoning from there, ignoring conventional framings. Aristotelian; popularized in tech contexts by Musk.

**When to invoke:**
- Cases where conventional wisdom is producing stuck thinking
- Novel problems where existing analogies might mislead
- Cost or feasibility questions where assumptions need stripping

**When NOT to invoke:**
- Problems where established analogies clearly apply (don't reinvent biology)
- Routine work where convention is fine
- Cases where the "first principles" are themselves contested

**How an agent applies it:** (1) State the problem and the conventional approach. (2) List the assumptions embedded in the conventional approach. (3) For each assumption, ask: is this physically/biologically necessary, or is it convention? (4) Discard the convention-only assumptions. (5) Reason from what remains.

**Substrate evidence generated:**
- Test 1 (frequently surfaces considerations the engineer didn't have, especially around hidden assumptions)
- Test R1 (the framework selection itself is meta-reasoning — invoking first-principles signals "I think the conventional framing is wrong here")

**Organogenesis worked example:** `experiment-designer` is asked: "We always inject at single-cell stage; can we go cheaper?" First-principles: assumption is single-cell stage is necessary for distribution to all daughter cells. Strip: actually, what's needed is signal exposure at the right developmental window. Single-cell distribution is one way to achieve that, not the only way. Alternative: localized signal source at gastrulation might achieve the same exposure profile at lower cost.

**Origin:** Aristotle, modernized in design and engineering contexts. Latticework: "First Principles Thinking" under Worldly Wisdom.

---

### 8. Chain-of-Verification (CoVe) — Tier 2

**What it is:** Generate a draft answer, then generate verification questions about that answer, answer those questions independently, and revise the draft based on the verification results. Anti-hallucination by construction.

**When to invoke:**
- High-stakes outputs that will be acted on (lab dispatch, vendor commitment, investor communication)
- Cases where confident hallucination is the worst failure mode
- Outputs that cite specific facts or numbers

**When NOT to invoke:**
- Brainstorming or exploratory outputs where over-correction kills creativity
- Outputs where the verification overhead exceeds the cost of being wrong
- Cases where the verification questions can't be answered better than the original

**How an agent applies it:** (1) Generate draft answer. (2) Generate 3–5 questions a skeptic would ask about the draft. (3) Answer each independently, ideally with retrieval. (4) Compare answers to draft. (5) Revise draft to resolve discrepancies. (6) Output revised version with the verification trail in the evidence field.

**Substrate evidence generated:**
- Test 1 (revised outputs are higher quality)
- Test 4 (post-CoVe confidence is meaningfully different from pre-CoVe; calibration improves)
- Test 2 (the verification step is itself a multi-step workflow)

**Organogenesis worked example:** `investor-relations-drafter` produces a milestone update. CoVe questions: "Did we actually hit the parsimony gate this month?" "Is the calibration improvement number sourced from the held-out evaluation set or from training data?" "Are we claiming Test 5 success when we only have Test 5 partial?" Each verified independently. Draft revised; one claim about Test 5 was overstated and gets walked back.

**Origin:** Dhuliawala et al., *Chain-of-Verification Reduces Hallucination in Large Language Models* (ACL 2024 Findings).

---

## Candidate-ranking Tier system — specificity-aware (added v1.2)

**Scope.** This Tier system is for ranking biological candidates (transcription factors, signaling molecules, perturbation targets) by suitability for downstream commitment to wet-lab. It is distinct from the framework-tier system above; do not conflate the two.

**Tier definitions (mandatory dimensions).**

- **Tier 1 — primary candidates.** All three required: (a) presence in ≥2 independent cohorts/datasets, (b) specificity ratio ≥ 5.0 (target tissue mean expression / max non-target tissue expression, using whole-embryo or cross-tissue reference data), (c) consistent with literature direction (no conflicting validated paper). "Present in 2 cohorts" alone never satisfies Tier 1.

- **Tier 2 — secondary candidates.** Either (b) or (c) marginal: specificity ratio between 2.0 and 5.0, or literature support is suggestive but not validated. Two cohorts of presence is necessary but not sufficient.

- **Tier 3 — exploratory candidates.** Specificity ratio < 2.0 (broadly expressed), or single cohort only, or contradicted by literature. Not suitable for global perturbation without additional rationale; possible after restriction to conditional perturbation or tissue-specific approach.

**Mandatory pre-Tier check.** Before assigning any Tier label, the agent must execute the specificity check against the broadest available reference dataset (e.g., whole-embryo single-cell atlas) for every candidate. Skipping this check is a methodological error documented in the May 8-9 2026 session.

**Required output structure.**

For each candidate, the ranking must report:

```
{
  candidate_symbol: <gene>,
  tier_assignment: <1|2|3>,
  presence_evidence: [<dataset_1>, <dataset_2>, ...],
  specificity_ratio: <float>,
  specificity_reference_dataset: <accession>,
  literature_support: <validated|suggestive|conflicting|absent>,
  pleiotropy_risk: <low|medium|high>,
  flags: [<flag_1>, ...]
}
```

**Worked example — the mafba case (May 8-9 2026 session).**

In the original survey (2026-05-08), `mafba` was classified Tier 1 because it appeared in Schoels podocyte cluster (microdissected pronephros) and Wagner duct cluster subset (14% expressing). Both sources only examined pronephros — Schoels by microdissection, Wagner by subsetting on duct cluster only. Neither inspected the broader expression context.

When the pre-resolve specificity check was added (2026-05-09), Wagner's whole-embryo data revealed mafba expression at 87% in endothelial, 80% in lens, 77% in macrophage cells, versus 7-20% in pronephros. Specificity ratio: 0.145.

The correct Tier under the v1.2 system: **Tier 3 (pleiotropic; unsuitable for global KO)**. A global perturbation would have produced systemic phenotypes confounded with the pronephros effect, possibly embryonic lethality. The corrective pre-resolve catched this before $30-45K of wet-lab commitment. The retrospective recommendation that elevated `hoxb8a` over `mafba` — `hoxb8a` having a specificity ratio approximately 5.4× better — is the correct ranking under v1.2.

**Operational rule.** Any candidate ranking output that does not include the specificity dimension fails this catalog's audit. The `04_option_L_TF_enumeration.py` script and equivalent enumeration tools must integrate specificity by default, not as a post-hoc check.

**Squidiff integration note.** When `squidiff-in-silico-gate` is invoked to predict the transcriptomic response of a candidate perturbation, the specificity tier of the candidate must be declared in the figure header. A Tier 3 candidate (pleiotropic) producing a clean Mode 1 PASS verdict is a substrate-integrity warning — the prediction is asking "what happens transcriptomically" while the morphology will likely be systemic-phenotype, which Squidiff cannot predict. Cross-check with Mode 3 (Morpheus pairing) is mandatory for Tier 3 candidates if a verdict will inform wet-lab budget commitment.

**Substrate evidence:** Test 1 (reasoning quality on candidate ranking), Test 4 (calibration on Tier confidence — high-Tier candidates should have higher posterior support after wet-lab outcomes).

---

## How to use this catalog

**For agent design (in `organogenesis-agent-architect`):** When defining a specialist agent, declare which reasoning frameworks it natively supports. Most agents will support 2–4 frameworks well; few support all 8 well. Match framework to agent type. **In v1.2, prefer Tier 1 frameworks (Self-Consistency, Logic-LM) when their domain applies — they have the strongest 2025+ literature backing.** For candidate-ranking tasks (TF candidates, perturbation targets), apply the specificity-aware Tier system added in v1.2 (see section above).

| Agent type | Tier 1 default | Tier 2 supplement | Tier 3 occasional |
|------------|----------------|-------------------|-------------------|
| Specialists doing analysis | Self-Consistency | CoT, CoVe | — |
| Specialists doing exploration | (none — exploration is intrinsically Tier 2) | ToT, Self-Discover | First-Principles |
| Auditors / critics | Logic-LM (when formalizable), Self-Consistency | CoVe | Inversion |
| Compliance agents | Logic-LM (mandatory) | CoVe | — |
| Strategists / planners | Self-Consistency | Self-Discover | Inversion, First-Principles |
| Routine operators | (Tier 1 not needed for routine work) | CoT only | — |

**For runtime invocation:** When an agent receives a question, it can either (a) use its default framework, or (b) explicitly select a framework based on question type. The Self-Discover framework is itself a meta-framework for selecting other frameworks. Use it when in doubt.

**For substrate evidence:** Every framework invocation must be logged with `framework_applied` in the structured output. This produces:
- Volume of framework usage data (which frameworks fire when)
- Calibration data per framework (Self-Consistency confidence vs. actual accuracy, etc.)
- Transferability data (does CoT used in organogenesis transfer to a question in another field?)

---

## Anti-patterns

1. **Framework theater** — Invoking a sophisticated framework on a trivial question to look smart. CoT for "what's the BWH contact email?" is theater. Match framework to problem complexity.
2. **Single-framework thinking** — Treating one framework as universally best. CoT is great but not for everything. The catalog exists because reasoning is heterogeneous.
3. **No framework declared** — An agent output without `framework_applied` populated cannot be analyzed for substrate evidence. The `reasoning-exposer` agent should reject these.
4. **Adding frameworks to look comprehensive** — Don't add a framework to this catalog because it's in the literature. Add when an agent in the system actually needs it. Empty catalog entries are worse than missing entries.
5. **Forgetting Logic-LM exists** — Compliance and constraint problems often default to LLM reasoning when they should default to symbolic verification. When the answer must be provably correct, use Logic-LM.

---

## Roadmap for catalog growth

The starter catalog has 8 frameworks. The path to growth:

| Trigger | Action |
|---------|--------|
| Agent in the system regularly faces a question type that doesn't fit any of the 8 | Add a framework |
| New paper in the Awesome-LLM-Reasoning repo introduces a framework that solves a problem we have | Evaluate, add if it fits |
| A framework in the catalog is never invoked across 3 months of operation | Consider removing or marking deprecated |
| A framework's calibration deteriorates substantially over time | Investigate; possibly remove or refine |

**Priority candidates for v2:** Buffer of Thoughts (template-augmented reasoning), Program-aided Language Models (PAL — for computational tasks where execution beats simulation), Analogical Reasoning (for cross-field operation), Skeleton-of-Thought (for parallel decoding when latency matters).

**Decision criterion for adding:** the framework must (a) appear in established literature with at least one peer-reviewed instantiation, (b) generate at least one type of substrate evidence not covered by the existing 8, and (c) have a clear organogenesis-relevant use case.

---

## Connection to Witt thesis

This catalog operationalizes one specific component of Witt's reasoning layer (Section 5 of the thesis). The reasoning layer is broader than just framework selection — it also includes tool use, retrieval augmentation, and structured output generation. This catalog is the *cognitive shape* component of that layer, not the entire layer.

When advisors or technical reviewers ask "what does Witt's reasoning layer actually do?", point them here for the cognitive-shape component, then to the broader Section 5 description for the full picture.

---

— End of reasoning-frameworks-catalog.md v1.1 —
