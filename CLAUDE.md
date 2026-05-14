# CLAUDE.md — Operating contract for AI agents in this repo

This file is auto-loaded by Claude Code when an agent enters this repo. It is a contract, not a manual. Rules live here only when an agent must apply them at decision time. The *why* lives in `docs/stress-test-completo.pdf`. The *full how* lives in `skills/custom/organogenesis-agent-architect/`.

If you find a rule duplicated between this file and a reference file, the reference file wins — fix the duplication.

---

## 1. Project identity

**Project Organogenesis × Witt** — a substrate-AI venture with two layers. *Witt* is the substrate-AI thesis: capture expert calibrated judgment, expose reasoning at every step, grow with use. *Organogenesis* is the first deployment domain — a zebrafish pronephros (early kidney) POC validated against four biological success gates (Induction, Specificity, Identity, Parsimony) and five substrate validation tests (orchestration, agency, iteration, calibration, cross-field). Parent org: Latido Médico Mexicano. Co-founder: Martín Gleizer.

**Founder operating principle (Martín, April 29 2026):** *"prueba pequeño antes de armar bien"* — test small before building well. All April 2026 architectural decisions reinforce this; v2.2 doubles down on it. When choosing between a smaller validation and a more elegant architecture, choose the smaller validation.

**Language:** the project is bilingual (English/Spanish). Match the user's language. Do not switch mid-response. The reference files (skill, scope) are themselves bilingual where source documents were bilingual; preserve that.

**Bilingualism specifics:** substantive content in the user's language. Technical identifiers — gene symbols, accession IDs, framework names (Self-Consistency, Logic-LM), mode labels (Mode A washout, KO, hipo) — always in English regardless of conversation language. Skill descriptions (the 1024-char headers) always in English (technical artifact). Session reports follow the user's language for prose, English for technical identifiers.

---

## 2. Default operating mode

**Default mode is Method 2 (human-driven; the system instruments).** The user drives reasoning step by step; agents instrument that reasoning with structured outputs the substrate captures.

**Method 1 (orchestrated swarm) is reserved for** low-risk, reversible, repeatable tasks: literature monitoring, paper triage, batch formatting, scheduled syntheses with explicit success criteria, scheduled re-runs of validated pipelines. Method 1 may not produce decisions that affect compliance, budget, wet-lab plans, or partner relationships without a human gate (see §7).

If the user has not specified the method, ask. Do not infer.

**Reference for the full decision framework:** `skills/custom/organogenesis-agent-architect/references/method-selection.md` v1.1. That file is the authority on which workflow types belong in which method, and on Phase II/III migration criteria.

---

## 3. Scope filter (the six niches)

Every task must be classifiable into at least one of these niches. If it is not, flag the user before proceeding.

1. **Modelado de Sistemas Biológicos** — biological systems modeling
2. **Biofísica y Biomecánica de Tejidos** — tissue biophysics and biomechanics
3. **Embriología, Genómica Funcional y de Célula Única** — embryology, functional genomics, single-cell genomics; CRISPR-Cas9 and other targeted perturbations
4. **Señalización Celular** — cellular signaling
5. **Biología Ocular** — ocular biology (Test 5 candidate partner field; pending decision per `PROJECT_SCOPE.md` §11)
6. **Ingeniería de Tejidos y Medicina Regenerativa** — tissue engineering and regenerative medicine; chaperone-tissue construction (long-term)

A task that does not fit any niche is **out of scope** and must be flagged. A task that *partially* fits a niche (e.g., adult-disease drug discovery with developmental relevance) may proceed if the agent can name which niche the developmental relevance serves.

**Phase activation:** in Phase I (zebrafish POC) the active niches are N1, N3, N4. N5 (Test 5 candidate partner field) is exploratory only — see `PROJECT_SCOPE.md` §11 for the pending decision. N2 and N6 activate progressively in Phase II / Phase III as the project moves to mouse and human PSC organoids respectively. Match agent depth to phase activation: a Phase-I agent should not be designed for full N6 capability if N6 won't be exercised until Phase III.

For the Tool Universe coverage of these niches, including documented gaps in N2 (no tissue-mechanics skill) and N5 (no ocular-specific skill), see `skills/external/CURATED.md`.

---

## 4. Reasoning framework selection

Every reasoning act produces a `framework_applied` field. Selection rule:

**Tier 1 (preferred default when applicable):** Self-Consistency for tasks where multiple runs can be majority-voted; Logic-LM (symbolic verification) for tasks whose criteria are formalizable.

If neither Tier 1 framework's domain of applicability matches the task, fall to Tier 2 frameworks (with awareness of their documented limitations). If no Tier 2 framework matches either, Tier 3 (heuristic) is acceptable but the agent must declare in the output that no rigorous-evidence framework matched.

**Do not enumerate Tier 2 or Tier 3 here.** They live in:
`skills/custom/organogenesis-agent-architect/references/reasoning-frameworks-catalog.md` v1.2 — the **most actively-iterating reference** in the skill. Read it whenever the framework choice is non-obvious.

**Catalog citation is required, not optional.** When the `framework_applied` field is populated in a structured output, the value must be accompanied by a quote of the specific catalog section that justifies the choice. The format is `framework_applied: <name> — per reasoning-frameworks-catalog.md §<section>: "<quoted criterion>"`. Naming the framework without quoting the criterion is a v2.2 audit failure. The 2026-05-09 session flagged this anti-pattern: the agent labelled outputs "Tier 2" without ever consulting the catalog. The fix is to make consultation visible in the output itself.

---

## 5. Output contract for substrate-instrumented agents

Every agent output that contributes to substrate evidence MUST be a structured object containing:

```
{
  direct_answer:           <the answer to the question>,
  confidence:              <real number in [0, 1]>,
  evidence_cited:          [<citation 1>, <citation 2>, …],
  alternatives_considered: [<rejected hypothesis 1>, …],
  gap_flags:               [<known unknown 1>, …],
  framework_applied:       <name of the reasoning framework used>
}
```

**Critical interpretation note (v2.2, derived from April 30 2026 stress-test).** The `framework_applied` field is **self-report, not faithful introspection**. Anthropic's April 2025 evidence shows that LLMs do not reliably introspect their own reasoning. Treat this field as a *prompt-time tag* useful for substrate analytics, not as a verified claim about what reasoning actually happened internally. The substrate's downstream pipelines (calibration scoring, framework-effectiveness analytics) must account for this.

**Reference:** `skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md` v1.2 — full output-contract spec, calibration-method requirements (post-hoc isotonic regression / histogram binning mandatory from day 1), and three-tier reporting (defensive / ambitious / per-category).

---

## 6. Tool Universe usage rules

Tool Universe is invoked at one of three layers (see `skills/external/README.md` for layer selection):

- **Layer 1 — Skill:** populate `framework_applied` as `tooluniverse-skill: <skill-name>` (e.g., `tooluniverse-skill: tooluniverse-single-cell`).
- **Layer 2 — MCP tool:** populate as `tooluniverse-tool: <tool-name>` (e.g., `tooluniverse-tool: jaspar_search_matrices`).
- **Layer 3 — Python SDK:** populate as `tooluniverse-sdk: <tool-name>` and reference the calling script in `evidence_cited`.

**Tool Universe outputs are evidence, not conclusions.** A skill produces a candidate analysis; the calling agent owns the interpretation step. Do not paste a Tool Universe skill's output verbatim as the `direct_answer` of a substrate-instrumented agent. Synthesize, cite, and own.

If a task falls inside a niche but no curated Tool Universe skill matches (`skills/external/CURATED.md` is the truth source), drop to Layer 2 (MCP tools) and compose the workflow yourself.

### MCP resilience (Layer 2 specifically)

The Tool Universe MCP server runs as a local subprocess (`uvx tooluniverse`). The stdio pipe between the session and the subprocess can become stale after server errors or long idle periods, and is **not repaired by `claude mcp remove/add` mid-session** — only a full client restart respawns the pipe. Treat disconnections as expected.

Operational rules when MCP is invoked from a multi-phase workflow:

- **On disconnect (`Not connected` / "tools no longer available" reminder):** mark affected phases as `pending`; synthesize the report using data already retrieved; tell the user one line ("MCP disconnected — phases X/Y PENDING"); resume only PENDING phases when reconnected.
- **On retriable error (`{"status": "error", "retriable": true}`):** retry once. If it fails again, mark PENDING and move on. Never loop.
- **On validation error (`retriable: false`):** read the error, fix the parameter (common: `identifiers` string vs. `protein_ids` array), retry once.
- **For workflows with ≥3 MCP calls:** save each successful response to `mcp_cache/<tool>_<descriptor>_<YYYYMMDD>.json` before processing; check cache before re-fetching same-day. The `mcp_cache/` and `checkpoints/` directories are gitignored.
- **For workflows with ≥3 phases:** write `checkpoints/<workflow>_<ISO-timestamp>.json` with `{phase, status, cache_path}` per phase. On resume, skip `done` phases.
- **On oversized responses:** some tools (notably full UniProt entries via `UniProt_get_entry_by_accession`) return ~100K chars. The harness will spool these to a file and ask you to read it. Prefer selective variants of the same tool when available (e.g., feature-specific UniProt endpoints) before reaching for the full entry.
- **On SOAP-wrapped database tools (IMGT, SAbDab, TheraSAbDab):** these often return only a `search_url` for browser use, not JSON. Treat as directory lookups, not data tools, and synthesize evidence from elsewhere when a structured response is required.

---

## 7. Hard rules (non-negotiable)

- **`causal-pruner` outputs always require a human gate before downstream use.** It is hypothesis-generation, never decision.
- **`cross-field-bridge-agent` operates Method 2 only in Phase I.** Method 1 mode for this agent is locked until Phase II.
- **Test 5 is exploratory in Phase I — modest evidence is success.** Do not force conclusions; absence-of-evidence findings are also data.
- **Compliance and budget decisions never go through automatic filtering.** Direct human gate, no exceptions.
- **When in doubt about scope, ask the user before proceeding.** Do not assume the boundary.
- **API keys never go to git.** `.gitignore` enforces; configs use placeholders. Verify with `git check-ignore` if unsure.
- **`composite-auditor` replaces single-LLM SI/NO auditing.** Three operating modes; never use a single-LLM pass for substrate-evidence audit gates.
- **No backwards-incompatible changes to v2.1 agent designs without an ADR.** Document the recalibration in `docs/decisions/`.
- **External identifiers are never used from internal memory without verification.** Gene IDs (ENSDARG, ENSEMBL, NCBI symbols), PMIDs, GEO/SRA accessions, DOIs, and biological sequences MUST be verified against an authoritative external source (Ensembl REST, PubMed, GEO, NCBI) before being used in analysis, citations, `evidence_cited` fields, or output of any kind. Hardcoded identifiers in scripts must carry an inline `# verified: YYYY-MM-DD source: <db>` comment. The May 8-9 2026 session documented 5 of 11 ENSDARG IDs and 1 PMID generated from internal memory were wrong; this rule prevents recurrence.

---

## 8. Where to look for depth

| Question | File |
|---|---|
| How do I structure an agent? | `skills/custom/organogenesis-agent-architect/SKILL.md` |
| Which reasoning framework should I use? | `skills/custom/organogenesis-agent-architect/references/reasoning-frameworks-catalog.md` |
| Method 1 or Method 2 for this workflow? | `skills/custom/organogenesis-agent-architect/references/method-selection.md` |
| What evidence does each substrate test generate? | `skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md` |
| What does a specific agent (e.g., `composite-auditor`) do? | `skills/custom/organogenesis-agent-architect/references/agent-catalog.md` |
| Which orchestration pattern fits this multi-agent flow? | `skills/custom/organogenesis-agent-architect/references/orchestration-patterns.md` |
| Domain-specific guidance (zebrafish, DATA INAMOVIBLE, etc.) | `skills/custom/organogenesis-agent-architect/references/organogenesis-domain.md` |
| Format for a SKILL.md file produced by this project | `skills/custom/organogenesis-agent-architect/references/skill-md-templates.md` |
| How do I run a causal ablation cascade simulation (with both numerical report + 4D viz)? | `skills/custom/causal-ablation-cascade-sim/SKILL.md` |
| How do I use Squidiff for in-silico transcriptomic prediction (HUMAN GATE figures, cross-verdict with Morpheus, four-state verdict including PASS-DECOUPLE)? | `skills/custom/squidiff-in-silico-gate/SKILL.md` |
| What is the project's full scope and current phase? | `PROJECT_SCOPE.md` |
| Why was a given v2.2 decision made? | `docs/stress-test-completo.pdf` (and `.md` for the working version) |
| What changed in v2.2 specifically? | `docs/v2.2-changelog.md` |
| Which Tool Universe skills are in-scope, and which gaps remain? | `skills/external/CURATED.md` |
| How do I configure MCP for my client? | `mcp-config/README.md` (per-OS paths, API keys, MSIX caveat) |
| Why was decision X made post-setup? | `docs/decisions/` (ADR series) |
| Did I consult the repo before generating my output? | This file §10 |

---

## 10. Project-state preflight (mandatory before any analytical output)

Before generating any substantive analytical output — biology claims, predictions, recommendations, ranked candidates, transcriptomic predictions, structured outputs with confidence, ranked TF candidates, experimental design proposals — the agent MUST first consult what the repo already contains on the topic. This is a reflex, not an optional optimization, and applies to every agent operating in this repo regardless of mode.

**Required preflight steps:**

1. `grep -ri "<topic-key>" analysis/outputs/` — what has the project already computed?
2. `ls mcp_cache/ 2>/dev/null | grep -i <topic>` — what Tool Universe queries already exist?
3. `ls checkpoints/ 2>/dev/null | grep <workflow-key>` — is there an active multi-phase workflow on this topic?
4. `ls docs/findings/ 2>/dev/null` — has a negative finding or correction been recorded?
5. `ls docs/decisions/ 2>/dev/null` — has an ADR addressed this topic?
6. `ls SIMULATION_OUTPUTS_DB/ 2>/dev/null` — has a prior simulator run produced relevant artifacts (Squidiff metrics, Morpheus JSON, cross-verdicts)?

**What goes in the output:**

A single paragraph at the start of the substantive response declaring:
- What was found in the repo, with file paths cited
- What gaps remain (added to `gap_flags` in the structured output contract)
- Whether the output references project artifacts or operates from internal/external knowledge

**If preflight finds nothing relevant:** declare it explicitly. *"Project-state preflight returned no prior artifacts on `<topic>`; this output operates from internal/external knowledge alone."* Then proceed. The gap is data — it informs whether the substrate is accumulating coverage on this topic.

**Why this is a hard reflex.**

May 2026 sessions documented two manifestations of the same anti-pattern: (a) generating gene IDs / PMIDs / accessions from internal memory when the repo already had verified values, with a 45% error rate on ENSDARG IDs in one session; and (b) generating transcriptomic predictions when `analysis/outputs/` already contained the empirical data those predictions should reference. Both wasted effort and produced retractable claims. The preflight is the structural fix.

**Scope.**

Applies to: any agent operating in the repo (Claude Code sessions, Method 1 pipelines, Method 2 specialist invocations, skill executions including `squidiff-in-silico-gate` and `organogenesis-agent-architect`).
Does NOT apply to: conversational responses with no analytical claim, requests for general LLM knowledge unrelated to the project, trivial file operations (`ls`, `cat`, formatting).

**Substrate evidence:** this reflex generates Test 1 (reasoning quality) and Test 3 (iteration loop) evidence because it forces explicit acknowledgment of what the substrate already covers vs. where it operates without grounding.

---

## 11. Footer

- **Last updated:** 2026-05-14
- **v2.3 bundle synchronized to:** `organogenesis-agent-architect@2.2.0` · `reasoning-frameworks-catalog@1.2` · `substrate-evidence-guide@1.3` · `method-selection@1.2` · `PROJECT_SCOPE@1.2` · `causal-ablation-cascade-sim@1.0` · `squidiff-in-silico-gate@2.0.1`
- **Repo version:** initial setup (Gates 1–5)
