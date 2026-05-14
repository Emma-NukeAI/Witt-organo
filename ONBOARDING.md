# Onboarding — Project Organogenesis × Witt

Welcome. This document is for new collaborators joining the project. It is designed for a 30–60 minute first read; deeper documents are linked at each step. By the end, you will have the project running locally and know where every piece of the work lives.

If anything here is unclear, that's a documentation bug — open an issue or ping Emmanuel directly (see [Where to ask questions](#where-to-ask-questions) at the bottom).

---

## Welcome and project context

**Project Organogenesis × Witt** is a substrate-AI venture with two intertwined components:

**Witt** is a substrate-AI thesis — the underlying claim that an AI substrate can capture expert calibrated judgment, expose its reasoning at every step, and grow with use. Witt is domain-agnostic in concept; what makes the substrate framing different from a "vertical biology tool" is that the substrate produces *transferable* evidence (calibration data, learning signals, cross-field operation evidence), not just biology answers.

**Project Organogenesis** is the first deployment domain. The proof-of-concept is **zebrafish pronephros (early kidney) development** — chosen because zebrafish are fast, cheap, and well-characterized, and the pronephros is a highly tractable organogenesis system with clear success criteria. 

The substrate and the domain validate against different metrics — five substrate validation tests for Witt; four biological success gates for Organogenesis. **Every agent the project designs serves both layers.** That dual-purpose discipline is what makes the architecture defensible. See [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) for the formal definitions and current phase.

Parent organization: **Latido Médico Mexicano**. Co-founder: **Martín Gleizer**. Founder operating principle from Martín (April 29 2026): *"prueba pequeño antes de armar bien"* — test small before building well. Every April 2026 architectural decision reinforces this; v2.2 doubles down on it. When forced to choose between a smaller validation and a more elegant architecture, choose the smaller validation.

---

## The architecture in 5 minutes

Five concepts. Each gets 2–4 sentences; deeper reading is linked.

### Method 1 vs Method 2

The architecture supports two parallel methods. The choice is a runtime decision by the human user, not by the orchestrator.

**Method 1 (orchestrated swarm)** — a 24/7 orchestrator dispatches to a swarm of specialist agents, an auditor filters, a human gate approves, then results land in a database. Fits well-defined, repeatable, throughput-bottlenecked workflows. Substrate evidence: Tests 1, 2, 4.

**Method 2 (human-driven)** — humans drive reasoning step by step; agents instrument that reasoning with structured outputs. Fits novel, exploratory, cross-field questions. Substrate evidence: Tests 1, 3, 5.

**Default mode in this repo is Method 2.** Method 1 is reserved for low-risk, reversible, repeatable tasks. See [`skills/custom/organogenesis-agent-architect/references/method-selection.md`](skills/custom/organogenesis-agent-architect/references/method-selection.md) v1.1 for the full decision framework.

### The five substrate validation tests

| # | Test | What it measures |
|---|---|---|
| 1 | **Orchestration** | The substrate's specialists answer real questions correctly with structured, confidence-tagged outputs. |
| 2 | **Agency** | Multi-step workflows execute through human-gated checkpoints without confidently-wrong outputs. |
| 3 | **Iteration loop** | The substrate compounds through use — calibration improves, error rates drop, prior cases inform new ones. |
| 4 | **Calibration** | Confidence scores match empirical accuracy (Expected Calibration Error). v1.2 thresholds recalibrated based on Vega et al. Feb 2025. |
| 5 | **Cross-field operation** | The substrate transfers knowledge between adjacent biological domains. v1.2 frames this as **exploratory in Phase I**, not a criterion of success. |

Detail and recalibrated thresholds: [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §5.

### The four biological success gates (Organogenesis POC)

| Gate | Criterion |
|---|---|
| **Induction** | Reproducible ectopic kidney structures above negative controls, across independent batches. |
| **Specificity** | Structures localize to the chaperone tissue and follow the planned timeline (not nonspecific teratogenesis). |
| **Identity** | Marker + transcriptomic evidence supports renal identity (`wt1a`, `pax2a`, `pax8`, `hnf1b`) — not generic mesoderm. |
| **Parsimony** | Pruned program matches or beats fuller-cue baseline with fewer cues, tighter timing, simpler chaperone context. |

Full text and ladder of evidence: [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §4.

### The six niches (scope filter)

Every task in this repo must fit at least one of these niches. Tasks outside are flagged.

1. Modelado de Sistemas Biológicos (Biological Systems Modeling)
2. Biofísica y Biomecánica de Tejidos (Tissue Biophysics & Biomechanics)
3. Embriología, Genómica Funcional y de Célula Única (Embryology, Functional Genomics, Single-Cell)
4. Señalización Celular (Cellular Signaling)
5. Biología Ocular (Ocular Biology) — Test 5 candidate partner field, decision pending
6. Ingeniería de Tejidos y Medicina Regenerativa (Tissue Engineering & Regenerative Medicine)

Phase activation: in Phase I, niches 1, 3, 4 are primary. N5 is exploratory; N2 and N6 activate progressively in Phase II / III.

### v2.2 stress-test recalibrations

On April 30 2026 the v2.1 architecture was stress-tested against 2025+ LLM reasoning evidence (~25 papers). v2.2 is the operational consequence. Major changes: three-tier reasoning framework hierarchy (Self-Consistency and Logic-LM as Tier 1); Test 3, 4, 5 thresholds recalibrated with three-tier reporting (defensive / ambitious / per-category); `framework_applied` reframed as self-report, not faithful introspection (Anthropic April 2025); `composite-auditor` replaces single-LLM auditing; `causal-pruner` neutered to hypothesis-generation only.

Full evidence and reasoning: [`docs/stress-test-completo.pdf`](docs/stress-test-completo.pdf) (or `.md` for the working version). What changed and where: [`docs/v2.2-changelog.md`](docs/v2.2-changelog.md).

---

## Setting up your environment

### Step 1 — Clone this repo

```bash
git clone https://github.com/<owner>/witt-organogenesis.git
cd witt-organogenesis
```

### Step 2 — Clone Tool Universe inside skills/external/

```bash
cd skills/external/
git clone https://github.com/mims-harvard/ToolUniverse.git
cd ../..
```

The `ToolUniverse/` folder is gitignored — every collaborator clones it locally so we receive upstream updates via `git pull` without our repo growing. See [`skills/external/README.md`](skills/external/README.md) for context.

### Step 3 — Install Python and uvx

`uvx` runs Tool Universe's MCP server on demand. Install once per machine:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify with `uvx --version`. Python 3.11+ should also be available; `uv` will manage its own Python automatically.

### Step 4 — Configure MCP for your client

Pick the matching template:

- Claude Desktop → `mcp-config/claude-desktop.json`
- Claude Code → `mcp-config/claude-code.json`
- Cursor → `mcp-config/cursor.json`

Copy the contents into your client's actual MCP config file. **Paths differ by client.** See [`mcp-config/README.md`](mcp-config/README.md) for the per-OS table — note especially: only Claude Desktop uses `%APPDATA%` on Windows; Claude Code and Cursor use `%USERPROFILE%`. There is also an MSIX caveat for Microsoft Store installs of Claude Desktop.

### Step 5 — Set up your API keys

Three keys, all free and all optional (Tool Universe works without them, but specific tools will be rate-limited):

| Variable | Where to obtain | Why bother |
|---|---|---|
| `NCBI_API_KEY` | https://account.ncbi.nlm.nih.gov/settings/ | PubMed search rate from 3/sec → 10/sec |
| `NVIDIA_API_KEY` | https://build.nvidia.com | Unlocks AlphaFold2, ESMFold, genomics models |
| `FDA_API_KEY` | https://open.fda.gov/apis/authentication/ | Higher FAERS rate limits |

Place them in the `env` block of whichever config file your client reads. **Never commit keys.** `.gitignore` excludes `*.env` and `.claude/settings.local.json` for this reason.

### Step 6 — Validate the setup

Outside any client, in a terminal:

```bash
PYTHONIOENCODING=utf-8 uvx tooluniverse status
```

Expected: a banner reporting ~2,200 tools across ~500 categories. First run may take 30–60 seconds while `uvx` resolves and caches the package; subsequent runs are near-instant.

Inside your client, open a new conversation and run a tiny Tool Universe call (e.g. ask: *"Use Tool Universe to search JASPAR for the PAX6 transcription factor binding motif."*) — successful response confirms the MCP path works end-to-end.

If anything fails, see the **MCP Resilience** subsection in [`CLAUDE.md`](CLAUDE.md) §6 for triage steps.

---

## Your first session with the project

Open Claude Code (or your preferred client) inside the repo. `CLAUDE.md` is auto-loaded as project context — the agent now knows the operating contract.

For your first exercise, run a **Method 2 question**: pick a workflow from one of the six niches and ask the agent to walk you through it step by step, instrumenting each step. Example:

> *"In Method 2, walk me through: given a candidate transcription factor for zebrafish pronephros segment specification, how do I assemble evidence for whether it's a true regulator vs. a co-expressed bystander? At each step, name the framework you applied, your confidence (0–1), and any gap flags."*

Watch for:

- The agent **asks before assuming method** (default is Method 2; if you didn't say, it should ask).
- Each output includes the structured contract: `direct_answer`, `confidence`, `evidence_cited`, `alternatives_considered`, `gap_flags`, `framework_applied`.
- The agent treats Tool Universe outputs as **evidence, not conclusions** — it cites and synthesizes, doesn't paste verbatim.
- Hard rules (`CLAUDE.md` §7) are visible: e.g., if the agent runs the `causal-pruner` archetype, it stops at the human gate.

If any of these fail, the agent isn't following the contract — flag it.

---

## Where to find what

Detailed map for navigating the repo. (`CLAUDE.md` §8 has a more compact version for in-session lookup.)

| You want to … | Look at |
|---|---|
| Understand the project's full scope, current phase, budget, partners | [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) |
| Read **why** v2.2 made the architectural choices it did | [`docs/stress-test-completo.pdf`](docs/stress-test-completo.pdf) (or `.md`) |
| See the condensed list of what changed v2.1 → v2.2 | [`docs/v2.2-changelog.md`](docs/v2.2-changelog.md) |
| Design a new agent system | [`skills/custom/organogenesis-agent-architect/SKILL.md`](skills/custom/organogenesis-agent-architect/SKILL.md) |
| Pick a reasoning framework for an agent's `framework_applied` | [`skills/custom/organogenesis-agent-architect/references/reasoning-frameworks-catalog.md`](skills/custom/organogenesis-agent-architect/references/reasoning-frameworks-catalog.md) |
| Decide Method 1 vs Method 2 for a new workflow | [`skills/custom/organogenesis-agent-architect/references/method-selection.md`](skills/custom/organogenesis-agent-architect/references/method-selection.md) |
| Look up what evidence a substrate test requires | [`skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md`](skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md) |
| Browse the agent catalog (e.g., `composite-auditor`, `cross-field-bridge-agent`) | [`skills/custom/organogenesis-agent-architect/references/agent-catalog.md`](skills/custom/organogenesis-agent-architect/references/agent-catalog.md) |
| Pick an orchestration pattern | [`skills/custom/organogenesis-agent-architect/references/orchestration-patterns.md`](skills/custom/organogenesis-agent-architect/references/orchestration-patterns.md) |
| Domain-specific guidance (zebrafish kidney, DATA INAMOVIBLE) | [`skills/custom/organogenesis-agent-architect/references/organogenesis-domain.md`](skills/custom/organogenesis-agent-architect/references/organogenesis-domain.md) |
| Format a SKILL.md the project way | [`skills/custom/organogenesis-agent-architect/references/skill-md-templates.md`](skills/custom/organogenesis-agent-architect/references/skill-md-templates.md) |
| Find a Tool Universe skill or check niche-fit | [`skills/external/CURATED.md`](skills/external/CURATED.md) |
| Choose a Tool Universe layer (Skill vs MCP tool vs SDK) | [`skills/external/README.md`](skills/external/README.md) |
| Configure MCP, find API keys, troubleshoot connections | [`mcp-config/README.md`](mcp-config/README.md) |
| Read the rules an AI agent in this repo must follow | [`CLAUDE.md`](CLAUDE.md) |
| See past architectural decisions | [`docs/decisions/`](docs/decisions/) (ADR series; empty at setup) |

---

## Contributing

### How to propose a change

Open an issue describing the change before you start work. Scope decisions go through Emmanuel; do not assume scope.

### Branch naming

`<type>/<short-slug>` where type is one of: `feat`, `fix`, `docs`, `refactor`, `chore`, `adr`. Examples: `docs/onboarding-clarifications`, `feat/composite-auditor-mode-c`, `adr/0001-rag-vs-knowledge-graph`.

### Adding a non-obvious architectural decision

If the change is non-obvious (alternatives existed, hard to reverse), add an ADR in [`docs/decisions/`](docs/decisions/) using the template in that folder's README. ADRs are immutable — supersede them, do not delete them.

### What scope changes look like

A scope change is anything that adds or removes a niche, changes a Phase boundary, or alters a substrate test definition. These go through Emmanuel **and** the founder operating principle: prueba pequeño antes de armar bien.

---

## What success looks like in Phase I

Phase I (8 months, $297K budget) succeeds when **both** the four biological gates AND the five substrate tests show defensible evidence. Both layers must hold for the project's defensibility argument to land.

### Biological gates (Organogenesis)

All four gates above must show evidence in confirmatory omics + spatial + histology by months 6–8. The validation ladder runs from `Q-PCR markers → bulk RNA-seq → spatial transcriptomics → confirmatory histology`. See [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §4.

### Substrate tests (Witt) — recalibrated v1.2 thresholds

| # | Test | Defensive threshold (commitment) | Ambitious threshold (aspirational) |
|---|---|---|---|
| 1 | Orchestration | Specialists answer correctly with structured confidence-tagged outputs | (illustrative — see scope) |
| 2 | Agency | Multi-step workflows complete through human gates without confidently-wrong outputs | (illustrative — see scope) |
| 3 | Iteration | ≥5 percentage points improvement on primary accuracy; calibration corr +0.05; no significant degradation | ≥15 pp improvement; +0.15 |
| 4 | Calibration | ECE < 0.20 with post-hoc calibration (isotonic regression, histogram binning); high-conf preds correct ≥85% | ECE < 0.10 |
| 5 | Cross-field | **Exploratory in Phase I.** Modest preliminary evidence is success; full demonstration deferred to Phase II/III | Original ≥60% / ≥70% / ≥30% framing — not a Phase I criterion |

Critical reframing (v1.2): Test 5 is **not** a Phase I success criterion. The substrate's ambitious cross-field claim seeds in Phase I and matures in Phase II/III. The defensive thresholds for Tests 3 and 4 are reachable based on 2025+ literature; the ambitious thresholds remain as aspiration, not commitment. See [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §5 for full text and the reasoning behind the recalibration.

### What Phase I does *not* prove

Phase I does not prove the substrate is production-ready, that the cross-field claim is fully validated, or that the biology generalizes beyond zebrafish. Honest framing of what's *not* proven is part of the project's defensibility — see [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §5 "What the tests do NOT prove (audit discipline)".

---

## Where to ask questions

**Project communication is email-only.** No Slack, no GitHub Discussions, no standing meetings — keep traffic concentrated in email so it remains searchable and self-documenting.

Direct contact:

- **Emmanuel** — emmanuel@nuke-ai.com
- **Martín Gleizer** — Md@latidomedico.com

If you find a documentation bug while reading this file, open an issue and tag it `docs`. The repo improves through use.
