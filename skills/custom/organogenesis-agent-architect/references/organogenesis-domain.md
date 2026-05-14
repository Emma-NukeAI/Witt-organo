# Project Organogenesis — Domain Reference

> **When to read this file:** When you need project-specific grounding for an agent design — real partner names, technical concepts, budget context, validation ladder, or ethics boundaries. Use this to anchor agents in the actual project, not in generic biotech.

This file is the single source of truth for project facts that the architect skill should never invent. If a fact you need isn't here, ask the user — don't fabricate.

---

## Project One-Liner

A causal-organogenesis platform that combines **digital-organism simulation**, **causal-pruning ML**, and **wet-lab kidney induction** to discover the minimum signals, timing, and tissue context required to make tissues build themselves. Phase I proof: a sub-$300k zebrafish pronephros / early-kidney induction program using transient chaperone tissues.

The platform thesis is **simulate → prune → induce**:
1. **Simulate** digital organisms evolving from mathematical abstractions of cell behavior.
2. **Prune** to the minimum sufficient intervention via active-learning ML.
3. **Induce** the target organ program via transient chaperone tissue and timed signals.

---

## Witt Substrate Framing (NEW v2.0 — Critical Context)

Project Organogenesis is **the first deployment domain** of Witt, an AI substrate venture. The substrate captures expert calibrated judgment, exposes its reasoning, and grows through use. Organogenesis is the testbed where the substrate's foundations are validated.

**Two layers of every project decision:**

| Substrate layer (Witt) | Domain layer (Organogenesis) |
|------------------------|------------------------------|
| AI infrastructure for capturing/applying calibrated expert judgment | Research program on causal-pruning models for zebrafish pronephros |
| Validated by 5 substrate validation tests | Validated by 4 success gates |
| Time horizon: 5–10 years to maturity | Time horizon: 8 months to POC, then translation |
| Defensibility: accumulated deployment history | Defensibility: domain expertise + publications + IP |

**Implication for agents:** Every agent serves both layers. Agents that only ship the biology are valuable but generic. Agents that also generate substrate evidence (calibration data, learning signals, cross-field operation evidence) are what makes Witt different from a vertical biology tool.

**The five substrate validation tests** (full detail in `substrate-evidence-guide.md`):
1. **AI capabilities** — Does the substrate's reasoning layer produce useful outputs?
2. **Agent capabilities** — Can the substrate execute bounded multi-step workflows autonomously?
3. **Iteration loop** — Does the substrate measurably improve through engineer feedback?
4. **Calibration tracking** — Are confidence estimates well-calibrated and improving?
5. **Cross-field operation** — Can the substrate productively integrate an adjacent biological domain (TBD) with organogenesis?

**Witt's parent company:** Latido Médico Mexicano. Provides operational substrate access (organogenesis R&D team in place; cath lab presence in Mexican private hospital network for Phase II).

**Witt's second deployment (year 2):** Interventional cardiology in cath labs — not part of Phase I scope but informs how Phase I evidence is structured for portability.

---

## Validation Ladder

The correct sequence is **zebrafish → mouse → human tissues** (NOT human embryos).

| Phase | System | Key Question | Why |
|-------|--------|--------------|-----|
| I | Zebrafish | Can simulation-trained causal pruning identify a minimal, timed chaperone-tissue program that induces a pronephric / early-kidney structure? | Fast, cheap, optically accessible, conserved kidney development biology |
| II | Mouse | Does the causal-pruning framework transfer to mammalian kidney developmental logic? | Whole-mammal context, mature genetic tools, much closer to human use |
| III | Human PSC-derived organoids & ex vivo systems | Can the framework generate or regenerate human kidney tissue via chaperone induction? | Therapeutic translation; **no human embryo experimentation per ISSCR 2025** |

---

## Phase I Budget — $297,000

The architect skill should respect these workstream caps when proposing agents that touch budget.

| Workstream | Cap | Output |
|------------|-----|--------|
| Simulation engineering + benchmark design | $46k | Ground-truth causal training set |
| Causal-pruning model + Runpod compute | $29k (compute hard-capped at ~$3k) | Minimal cue/timing candidate programs |
| Boston zebrafish execution | $96k | In vivo induction data |
| Constructs + reagents | $34k | Biological intervention panel |
| Confirmatory analytics (scRNA-seq + spatial + histology) | $49k | Identity confirmation |
| Program operations | $20k | Coordinated execution |
| Contingency | $23k | Schedule protection |
| **Total** | **$297k** | Phase I POC complete |

**Compute note:** First-phase Runpod GPU rental is hard-capped at roughly $2-3k. The remainder of the computational budget goes to engineering and modeling, not owned hardware.

---

## Phase I Timeline (0-8 months)

| Window | Primary Work | Decision Criterion |
|--------|--------------|-------------------|
| 0-2 mo | Simulation engineering, kidney priors, benchmark tasks, low-cost Runpod sweeps | Model produces ranked candidate programs + chaperone-tissue design list |
| 2-4 mo | Pilot embryo runs, optimize chaperone-patch delivery, establish imaging readouts | At least one candidate shows interpretable renal developmental activity |
| 4-6 mo | Full candidate panel, repeat cohorts, kidney marker assays | Reproducible pronephric/early-kidney induction above controls |
| 6-8 mo | Confirmatory omics, spatial, histology + investor data package | Identity and parsimony claims hold up |

---

## Four Success Gates (Phase I POC)

Every confirmatory agent in the system serves one or more of these gates. The `cross-modality-integrator` agent's job is to deliver evidence per gate.

| Gate | What it Means | Why it Matters |
|------|---------------|----------------|
| **Induction** | Ectopic or supernumerary kidney-field / tubule-like structures arise reproducibly above negative controls across independent embryo batches | Shows the intervention is causally active, not anecdotal |
| **Specificity** | Structures localize near the intended chaperone tissue and follow a planned developmental timeline | Shows the model is doing developmental control, not nonspecific teratogenesis |
| **Identity** | Marker and/or transcriptomic evidence supports renal identity and tubule-like differentiation rather than generic mesodermal tissue | Separates true induction from shape-only artifacts |
| **Parsimony** | Model matches or beats a broader baseline with fewer cues, tighter timing, or a simpler chaperone context | Validates the causal-pruning thesis rather than a brute-force screen |

---

## Key Technical Concepts

These terms anchor the project. Agents should use them consistently.

- **Digital organism** — Simulated cells endowed with biological abstractions (sense gradients, divide, differentiate, migrate, secrete signals, polarize, deposit matrix, regulate lumen-like fluid exchange) that evolve under fitness pressure for organ-like order.
- **Causal pruning** — ML approach (with active learning) that compresses successful digital-organism programs into minimal, timed intervention recipes. Output: smallest sufficient set of signal identities, timing windows, spatial placements, and chaperone-tissue composition features.
- **Chaperone tissue** — Transient signal-emitting tissue patch that delivers the minimum developmental cues at the right times to induce a target organ program in an adjacent competent tissue.
- **Pronephros** — Embryonic kidney in zebrafish; the Phase I target. Forms quickly, is optically accessible, responds to BMP and Nodal cues, with retinoic-acid patterning of nephron fates via wt1a, pax2a, pax8, hnf1b.
- **Intermediate mesoderm** — Tissue context from which kidney structures arise; the substrate the chaperone tissue acts on.
- **Causal benchmark library** — Set of digital organisms with known developmental logic, used as ground truth to train the pruning model.
- **Active-learning prune-selection** — The pruning model chooses which next ablation/timing-shift is most informative to test, reducing experimental burden.
- **Freedom of morphology** — Strategic upside: optimal regenerated organ may not need to copy canonical adult anatomy.
- **Parsimony** — One of the four success gates: fewer cues, tighter timing, simpler chaperone = stronger validation.

---

## Partner Map

### Phase I (Boston anchor + California analytics)

| Partner | Role | Notes |
|---------|------|-------|
| **BWH Aquatics Facility (Brigham and Women's Hospital, Boston)** | Embryo production, husbandry, microinjection, imaging, embryo manipulation | Requires IACUC-approved protocol; sponsored collaboration or structured service relationship |
| **SeqMatic (Bay Area)** | scRNA-seq (10x), spatial transcriptomics (Visium / CytAssist), histopathology, outsourced bioinformatics | Commercial vendor; useful for fast-turn analytics |
| **Morizane Lab (Massachusetts General Hospital)** | Kidney-development translation into human PSC-derived kidney organoids; later ex vivo renal systems | Sponsored research / paid advisory / translational collaboration — not commodity CRO |

### Phase II (mouse)

| Partner | Role |
|---------|------|
| **Boston Children's Mouse Gene Manipulation Core** | Transgenic DNA injection, CRISPR, model generation. Requires IACUC + IBC protocols |
| **UCI Transgenic Mouse Facility** | Public pricing reference for founder-generation services |

### Phase III (human PSC organoids — California shortlist)

| Partner | Role |
|---------|------|
| **UCSD HUMANOID** | Organoids, monolayers, consultation, sponsored research access |
| **iXCells Biotechnologies (San Diego)** | iPSC reprogramming, Cas9 genome editing, directed differentiation, multicellular model building |
| **Cedars-Sinai Board of Governors Regenerative Medicine Institute** | Organoid and organ-chip shared resources (CIRM-funded) |

### Compute

| Partner | Role | Phase I cap |
|---------|------|-------------|
| **Runpod** | Per-second GPU rental for digital-organism simulation and pruning model training | ~$2-3k Phase I |

---

## Internal Team (Phase I)

The right structure is a **virtual biotech**:

- **Founder-scientist / scientific lead** — Final call on technical direction
- **Computational / ML lead** — Owns simulation engine and pruning model
- **Part-time developmental-biology adviser** — Biology priors, experimental plausibility
- **External program manager** — Vendor coordination, weekly integrated review

The agent system should reflect this team — no agent should presume staff that doesn't exist.

---

## Ethics Boundaries (Hard Lines)

These are non-negotiable. The `regulatory-ethics-advisor` agent enforces them; every other agent must respect them.

1. **No human embryo experimentation.** Per ISSCR 2025, human stem-cell-based embryo models are in vitro models, must not be transplanted to a uterus, and must not be cultured to potential viability. Human translation goes through PSC-derived organoids only.
2. **All animal work under approved IACUC protocols.** Zebrafish at BWH, mouse at Boston Children's. No exceptions.
3. **All genetic manipulation under approved IBC protocols.** Especially relevant for chaperone-tissue construct work.
4. **Frontier ideas stay frontier.** Craniofacial remodeling, extra-uterine support, and ethical protein production are platform horizons, not Phase I claims. Agents should not present them as near-term outputs.

---

## Risks (From the Investor Memo)

The `risk-register-agent` tracks these. The architect skill should make sure the risks have at least one agent monitoring or mitigating them.

| Risk | Mitigation Owner |
|------|------------------|
| Simulation does not transfer cleanly to biology | `benchmark-designer` (narrow search space, biological precedent), `causal-pruner` (treat sim as compressor, not oracle) |
| Intervention induces malformed tissue, not true organ-like program | `marker-validator` + `cross-modality-integrator` (require marker/transcriptomic confirmation, not image-only wins) |
| Academic-core access or oversight slows execution | `bwh-coordinator` + `program-manager` (sponsor-backed collaboration, backup vendors lined up) |
| Drift into ethically unsound human-development claims | `regulatory-ethics-advisor` (enforces no human embryo work) |
| Frontier ideas distort the near-term story | `program-manager` (separate platform horizons, stage everything behind the POC gate) |

---

## What Agents Should NEVER Do

- Invent partners, capabilities, or facts not grounded in this file or the user's input.
- Promise human therapeutic outcomes — the project is at platform-discovery stage, not clinical.
- Skip ethics gates for speed.
- Use frontier framings (ethical protein, craniofacial remodeling, artificial placenta) when describing the Phase I POC.
- Confuse Phase I (zebrafish kidney) with Phase III (human PSC organoids) when scoping work or proposing partners.

---

## v2.2 update — DATA INAMOVIBLE implementation guidance

The April 30, 2026 stress-test surfaced a relevant finding for how the project's shared knowledge base (DATA INAMOVIBLE) should be implemented in Phase I.

Magraner et al. (August 2025, arXiv:2508.10777) demonstrated that current LLMs in clinical domains achieve approximately 91.8% on knowledge probes but only 25% on reasoning tasks that require deploying that knowledge. The conclusion: the bottleneck is not knowledge access — the models already know the relevant biomedical content. The bottleneck is structured deployment of that knowledge.

The operational implication for DATA INAMOVIBLE:

**Start with simple Retrieval-Augmented Generation (RAG) rather than building an elaborate knowledge graph upfront.** Vector search over the existing knowledge base is sufficient for the first phase. Brown et al. (August 2025, arXiv:2508.06401) reviewed 128 papers on RAG and concluded that benefits depend critically on design specifics rather than on architectural sophistication.

Then **measure empirically which is the actual bottleneck**:
- If access is the bottleneck (the models are not finding the right information): invest in better retrieval — query design, reranking, federated retrieval.
- If reasoning is the bottleneck (the models find the information but cannot deploy it): invest in prompt structure and Tier 1 reasoning frameworks (Self-Consistency, Logic-LM per reasoning-frameworks-catalog.md v1.1).

The decision to build a knowledge graph (with explicit relationships, ontology mappings, etc.) should be deferred until the project has empirical evidence that such investment will address the actual bottleneck. The biomedical RAG literature (BTE-RAG, Wright et al. 2025, PMC12888809) demonstrates substantial precision gains from well-designed retrieval over 60+ biomedical sources without requiring elaborate knowledge graph construction.

This guidance applies the project's operating principle ("prueba pequeño antes de armar bien") to a specific architectural decision that was previously open. The decision is not made — it is deferred until Phase I produces evidence to inform it.

---

— End of organogenesis-domain.md v1.1 —
