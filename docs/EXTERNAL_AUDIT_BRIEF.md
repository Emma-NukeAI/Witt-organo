# Project brief for external review

**Purpose of this document.** A neutral, self-contained description of the project — its goals, architecture, workflow, agent roster, and governance — written so an external reviewer can assess it and give a supervisory opinion. It is a summary for review, not the internal working documentation.

---

## 1. What the project is

A research program in **computational and experimental developmental biology**, run by a medical-research organization. It has two coordinated parts:

- **The science (domain layer).** A proof-of-concept (POC) studying early kidney (pronephros) development in the **zebrafish**, a standard model organism. The work combines computational modeling of developmental signaling with laboratory validation (imaging, single-cell transcriptomics, tissue histology). It is basic research, conducted under standard institutional ethics oversight (animal-care and stem-cell-research guidelines); it involves **no human-embryo experimentation** and is not a clinical or therapeutic program.

- **The decision-support system (substrate layer).** A software system that helps the research team organize evidence, retrieve prior results, and reason over them with **calibrated confidence and explicit citations**. Its guiding idea is *accountability*: every machine-generated answer exposes its evidence, its confidence, the alternatives it considered, and its known gaps. The system is a research-support tool; it does not make consequential decisions on its own.

A core operating principle governs both parts: **"test small before building well"** — prefer a rough, working validation over an elegant, untested design.

---

## 2. Design principles (the logic)

1. **Human-in-the-loop by default.** The default mode of operation is human-driven: a person leads the reasoning and the software instruments it. A more automated "orchestrated" mode exists but is reserved for low-risk, repeatable, reversible tasks (e.g. literature scans, batch formatting). Any output that could affect compliance, budget, laboratory plans, or partnerships goes through an explicit human approval gate — never automatic filtering.

2. **A single, protected source of truth.** Shared project knowledge lives in one curated, versioned store. It is **read-only by default**; every change (add/edit/remove) requires an explicit human approval and a written specification of exactly what will change. This is what keeps the knowledge base stable and auditable over time.

3. **No invented facts.** External identifiers (gene IDs, database accessions, publication IDs) are never taken from model memory. They must resolve against the verified store or an authoritative external database, with the raw source response cached as proof — otherwise they are explicitly flagged as unverified. A deterministic (non-AI) check enforces this before any output is accepted.

4. **Audit discipline in language.** The project distinguishes carefully between "measured/validated," "preliminary evidence captured," and "not yet established," and never overstates the first. Claims are tempered to what the evidence supports.

5. **Reasoning is exposed, not hidden.** Every substantive machine output is a structured object: a direct answer, a confidence estimate (broken down when a claim mixes strong and weak parts), the evidence cited, alternatives considered, known gaps, and which reasoning method was used. Confidence self-reports are treated as useful metadata, not as ground truth about the system's internal reasoning.

---

## 3. Architecture and workflow

### The shared knowledge base
A curated store of domain knowledge (developmental-biology literature, datasets, prior analyses, verified identifiers), implemented as a knowledge graph with semantic search plus a backing store for raw data. It is versioned and human-gated for changes; reads are free.

### Two operating methods
- **Human-driven (default).** A person queries specialist components; an "assembler" component composes their outputs into a coherent draft; a human reviews before anything proceeds.
- **Orchestrated (restricted).** A coordinator dispatches a set of specialist components automatically, followed by an automated review and a human gate. Used only for the low-risk, repeatable task types noted above.

### The answer-and-learning loop
1. Answer from the shared knowledge base if it already contains enough.
2. If not, consult external sources (public biomedical literature and tool APIs).
3. Route any externally sourced evidence through an **independent multi-reviewer audit** (see §5).
4. Present to a **human approval gate**.
5. Only after approval is new knowledge added back to the store.

"Not currently in the knowledge base" is treated as a prompt to learn, not a stopping point — but nothing enters the source of truth without the human gate.

### Deterministic safety checks
Separate from any AI component, deterministic checks enforce the invariants above: identifier verification, structural completeness of outputs, consistency between the documentation and the actual state of the system, and "no accidental mutation of the source of truth."

---

## 4. The agent roster (roles)

Agents are role-scoped software components. Grouped by function:

- **Modeling & simulation** — run computational sweeps; generate ranked candidate hypotheses (always treated as hypotheses requiring human review, never decisions); maintain benchmarks and scoring criteria.
- **Laboratory support** — translate computational recipes into experiment protocols (with a human gate); track reagents and scheduling; enforce ethics/compliance as a hard gate.
- **Data & analysis** — single-cell and spatial transcriptomics pipelines, imaging analysis, histology scoring, and a cross-modality integrator that assembles the evidence for the biological success criteria.
- **Knowledge & strategy** — literature monitoring, knowledge-base curation.
- **Governance & measurement (substrate-specific)** — a calibration tracker (are confidence estimates well-calibrated?), an evaluation runner (does the system improve over time on a held-out question set?), a case-capture component (turn expert feedback into structured training signal), and a **multi-reviewer auditor** used as the audit gate.

A written rule set governs *when* each agent must be invoked, and requires an explicit, justified note whenever a role is performed without invoking its designated agent.

---

## 5. Governance and accountability

- **Multi-reviewer audit gate.** Any output used as validation evidence is reviewed by **three independent reviewers with adversarial prompts** (each asked to try to refute the claim), and their votes are combined. A single automated yes/no pass is explicitly disallowed as an audit gate; self-review by the component that produced the work does not count as an audit.
- **Calibration tracking.** Confidence estimates are scored against observed outcomes over time, with standard post-hoc calibration methods and honest, tiered thresholds (a conservative commitment level reported separately from aspirational targets).
- **Reasoning-method discipline.** Each output names the reasoning method it used and cites the specific criterion that justified the choice, from a maintained catalog.
- **Decision records.** Every substantive architectural decision is written up as a dated record with context, decision, and consequences.
- **Documentation-consistency gate.** A deterministic check keeps the human-readable documentation in sync with the actual state (counts, versions, records); drift fails the check.

The architecture is deliberately split into an **accountability half** (this system — the machinery that turns generated content into checkable, human-approved knowledge) and a **separate, isolated generation half** (a distinct research module for hypothesis generation that reads the knowledge base **read-only**, never modifies it, and by default only produces *proposals* for human review; the generation engine itself is not yet built). The separation exists so exploratory work can never destabilize the accountable core.

---

## 6. Current state

- The shared knowledge base is deployed and queryable (semantic search + deterministic identifier resolution + a way to drill from a summary to the underlying raw data).
- The answer-and-learning loop, the deterministic safety checks, the multi-reviewer audit gate, and the calibration/evaluation scaffolding are implemented and have been exercised end-to-end.
- A recent internal exercise ran a broad functionality check (offline and against the live system) and put it through the multi-reviewer audit; findings were addressed. The biological objective itself (demonstrating sufficiency of the proposed developmental program) remains open and is explicitly gated to future laboratory work.
- Known open items are tracked honestly (e.g., security hardening of hosted services; longer-horizon measurements; one cross-domain integration test that is exploratory in this phase).

---

## 7. What we would like the external reviewer to assess

1. **Architecture soundness** — is the separation of a protected source of truth, a human-gated change process, and a retrieval-plus-audit loop a sensible and robust design?
2. **Governance adequacy** — are the human gates, the multi-reviewer audit, the anti-fabrication checks, and the calibration discipline sufficient to make the system's outputs trustworthy? Where are the weak points?
3. **Gaps and risks** — what is under-specified, under-tested, or over-claimed? What failure modes are not yet covered?
4. **Honesty of self-assessment** — does the project's characterization of "what works vs. what is unproven" hold up, or is it optimistic anywhere?
5. **Proportionality** — is the engineering effort well-matched to the goals, consistent with the "test small before building well" principle, or is anything over-engineered?

A candid, critical opinion is what is wanted — including disagreement with the design choices.
