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

**Catalog citation is required, not optional.** When the `framework_applied` field is populated in a structured output, the value must be accompanied by a quote of the specific catalog section that justifies the choice. The format is `framework_applied: <name> — per reasoning-frameworks-catalog.md §<section-number>: "<quoted criterion>"`. **The cited section MUST be the specific framework section (e.g., `§3 Self-Discover`, `§8 Chain-of-Verification`), NOT the tier header (e.g., `§Tier 2`).** Citing the tier alone is a §4 audit failure — it is the soft-form of the anti-pattern §4 was designed to prevent. Naming the framework without quoting the criterion is also a v2.2 audit failure. The 2026-05-09 session flagged this anti-pattern: the agent labelled outputs "Tier 2" without ever consulting the catalog. The 2026-05-14 session repeated it in softer form (cited "§Tier 2:" instead of "§3:" or "§8:"). The fix is to make consultation visible in the output itself.

**Framework_applied may be updated mid-session if the reasoning dynamic changes.** If the work shifts from open-ended decomposition (Self-Discover) to verification-against-multiple-evidence-streams (Chain-of-Verification) or majority-vote-across-runs (Self-Consistency), the framework_applied field SHOULD be re-elected and the change documented in the output. Locking to the v1.0 framework choice across an evolving session is itself an anti-pattern (flagged in composite audit of session 2026-05-14).

---

## 5. Output contract for substrate-instrumented agents

Every agent output that contributes to substrate evidence MUST be a structured object containing:

```
{
  direct_answer:           <the answer to the question>,
  confidence:              <real number in [0, 1]>   OR
  confidence_by_subclaim:  { <subclaim>: <num>, ... },
  evidence_cited:          [<citation 1>, <citation 2>, …],
  alternatives_considered: [<rejected hypothesis 1>, …],
  gap_flags:               [<known unknown 1>, …],
  framework_applied:       <name of the reasoning framework used>,
  agents_invoked:          [{agent, status, invocation_id|reason, evidence_generated}, …]
}
```

**`confidence_by_subclaim` is required when `direct_answer` composes multiple sub-claims of asymmetric evidence-strength.** Aggregating to a single `confidence` value when sub-claims differ materially (e.g., one well-evidenced landscape description, one hypothesis-only minimal-set claim) is a §5 audit failure — it obscures audit signal. The 2026-05-14 session reported `confidence: 0.68` for an answer that aggregated (a) landscape description (real ≈0.85) and (b) minimal-set hypothesis (real ≈0.32); future outputs use `confidence_by_subclaim`.

**`alternatives_considered` is required in BOTH structured JSON outputs AND prose reports.** Asymmetry between presentation formats (e.g., alternatives in MD but absent in companion JSON claim record) is a contract violation flagged in composite audit of session 2026-05-14.

**`agents_invoked` is required when the output's work-type matches any row in `references/agent-invocation-matrix.md`.** See §11 below for the agent-invocation preflight that populates this field.

**HTML report emission at conclusion / checkpoint is mandatory (v2.5) — scope narrowed by ADR-0046 (2026-08-09): webapp-era runs do NOT emit HTML (their audit trail is the frozen record + UI URL + server-generated PDF; historic `reports/` stay valid and get indexed by the webapp). Repo agent-session outputs keep this rule until the webapp is the client.** Any analytical output that reaches a conclusion or checkpoint state (substrate-instrumented output per §5; user-signaled end of inquiry; phase completion; substantive analytical answer with confidence ≥ 0.5) MUST emit a self-contained HTML report in `reports/`. The structured contract fields above MUST appear as **visible UI elements** in the HTML body (callouts, badges, dedicated sections) — NOT only as metadata or hidden script blocks. Pure markdown or JSON outputs do NOT satisfy this requirement for substrate-evidence outputs. The HTML IS the audit trail.

Four canonical TYPES (defined in `references/html-report-contract.md`):
- **TYPE A** — comprehensive analytical (default for substantive research answers)
- **TYPE B** — interactive viz grid (structured data: candidates × dimensions, scenarios × verdict)
- **TYPE C** — simulation-backed Three.js (MANDATORY when conclusion is simulation-backed — see §7 hard rule)
- **TYPE D** — formal retrospective (session retrospectives, meta-analyses, composite-audits)

Multiple TYPES may coexist for a single conclusion (e.g., TYPE A + cross-linked TYPE C). Do NOT generate 4 parallel views of the same evidence — composite audit 2026-05-14 flagged that as `prueba pequeño antes de armar bien` violation.

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

**No-hang rule (overrides everything else in this section, 2026-07-04 founder directive).** An MCP call must **never** block progress. The offline / deterministic path is always the default; MCP is an *enhancement, never a blocker*. Concretely:
- **The offline equivalent always exists and is preferred as the fallback.** DATA INAMOVIBLE semantic query → local sparse `rag_backend.py`; identifier resolve → local `resolve_id.py` over the verified store; Tool Universe Path B → cached `mcp_cache/` responses or the offline analysis. Never wait on the live path when a deterministic one answers the same question.
- **Every MCP call is best-effort with a bounded wait.** If a call is rejected, returns `Not connected`, or does not return promptly, do **not** re-issue it in a loop and do **not** wait indefinitely. Fall back to the offline equivalent immediately, mark the live-only portion `PENDING`, tell the user one line, and continue the rest of the work.
- **Health is re-checked at most once, cheaply, not in a loop.** Before a workflow with ≥2 MCP calls, do a single cheap liveness probe (e.g. `list_tools` / `resolve_identifier` on a known key). If it fails, run the whole workflow on the offline path and report which live paths were skipped — do not probe repeatedly hoping it recovers. A mid-session reconnect is opportunistic: use it if it happens, never stall for it.
- **Permission prompts are not a contract concern — they are a settings concern.** Read-only MCP front-door tools (`data-inamovible`: `resolve_identifier`/`query_data_inamovible`/`fetch_raw`; `tooluniverse`: `list_tools`/`find_tools`/`get_tool_info`/`grep_tools`/`execute_tool`) are pre-approved in `.claude/settings.json` so multi-call workflows don't stall on per-call approval. If a new MCP tool prompts repeatedly, propose adding it to that allowlist rather than absorbing the pause.

Operational rules when MCP is invoked from a multi-phase workflow:

- **On disconnect (`Not connected` / "tools no longer available" reminder):** mark affected phases as `pending`; synthesize the report using data already retrieved; tell the user one line ("MCP disconnected — phases X/Y PENDING"); resume only PENDING phases when reconnected.
- **On retriable error (`{"status": "error", "retriable": true}`):** retry once. If it fails again, mark PENDING and move on. Never loop.
- **On validation error (`retriable: false`):** read the error, fix the parameter (common: `identifiers` string vs. `protein_ids` array), retry once.
- **For workflows with ≥3 MCP calls:** save each successful response to `mcp_cache/<tool>_<descriptor>_<YYYYMMDD>.json` before processing; check cache before re-fetching same-day. The `mcp_cache/` and `checkpoints/` directories are gitignored.
- **When WebFetch is used to verify an external identifier per Hard Rule §7.9, the raw fetched content MUST be cached separately from any AI-processed summary.** A processed summary saved as cache is NOT verification — the AI processing layer can hallucinate the very fields being verified. The verification is satisfied only when the raw JSON / TSV / HTML response is preserved at `mcp_cache/raw_<tool>_<descriptor>_<YYYYMMDD>.<ext>`. The 2026-05-14 session violated this softly: 14 UniProt accessions were "verified via WebFetch" but only the AI-restructured candidate JSON was cached; raw UniProt responses were lost. Composite audit flagged this as cache discipline violation requiring this rule.
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
- **External identifiers are never used from internal memory without verification.** Gene IDs (ENSDARG, ENSEMBL, NCBI symbols), PMIDs, GEO/SRA accessions, DOIs, and biological sequences MUST be verified against an authoritative external source (Ensembl REST, PubMed, GEO, NCBI) before being used in analysis, citations, `evidence_cited` fields, or output of any kind. Hardcoded identifiers in scripts must carry an inline `# verified: YYYY-MM-DD source: <db>` comment. The May 8-9 2026 session documented 5 of 11 ENSDARG IDs and 1 PMID generated from internal memory were wrong; this rule prevents recurrence. **Verification is satisfied only when the raw external response is cached per §6 cache discipline** — an AI-processed summary is NOT verification.
- **Anti-fabrication verification gate (GWT v1.1).** Every external identifier in an output (ENSDARG/ENSDARP, UniProt, PMID, GEO/SRA/PXD, DOI) MUST resolve through the **source-of-truth** — `analysis/scripts/lib/resolve_id.py` reading `analysis/outputs/verified_identifiers.json` (DATA INAMOVIBLE v1) — or be explicitly flagged in `gap_flags`. The deterministic gate `analysis/scripts/lib/verify_output.py` (Logic-LM-class, NOT an LLM) enforces this: an unresolved ENSDARG is a **gate FAILURE**; PMIDs/GEO are flagged (no literature store yet). In scripts, marker/gene IDs come from `resolve_id.require()` (which raises on NOT_FOUND), never hardcoded from memory. This is the structural fix for the 2026-06 corruption (15 of 16 marker IDs in `01_schoels_analysis.py` were wrong; the `wt1a` false-positive). The store is **read-only by default** and **human-gated mutable** (writes go through the single builder + a human gate); see ADR-0008/0010 and `docs/findings/2026-06-10-schoels-phase1-id-corruption.md`.
- **DATA INAMOVIBLE mutations are human-gated, ALWAYS, with explicit specification (2026-06-13 founder directive).** Every change to the shared store — **ADD, EDIT, or DELETE** — across the **embedding**, the **index** (Neo4j graph + vector + sparse), AND the **raw** layer, passes through a human gate and MUST state exactly what is being changed before proceeding. No agent mutates the DATA INAMOVIBLE unilaterally. Consequences: `ingest.py` is **add/update-only** (MERGE, **never deletes**); pruning dead/orphan nodes is a *proposal* (detect → `pending_review` specifying exactly what would be removed → human approve → execute), **never automatic**; changing the embedding model **halts** pending explicit human confirmation (re-embeds all + invalidates the vector space). **Reads/refreshes are free** (e.g. a reader auto-reloading the sparse index after a gated ingest); **mutations are not.** This is what makes it *inamovible* — *"siempre tiene que pasar por un gate humano y especificar qué se está haciendo"* (ADR-0022).
- **Self-audit by the same agent that produced the work is prohibited as a substrate-evidence audit gate.** Use `composite-auditor` (Mode 1 split-and-vote minimum) for any retrospective claimed as audit evidence. Self-reflection by the producing agent is permitted but is NOT an audit gate. The May 14 2026 session generated a single-LLM retrospective that was treated as audit evidence; the composite-audit that followed (ADR-0006) is the operationally correct pattern and this rule makes the distinction explicit. See `skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md` for invocation routing.
- **Catalog-agent invocation discipline.** If the work being produced matches the role description of a catalog agent (per `references/agent-invocation-matrix.md`), that agent MUST be invoked OR the output's `agents_invoked` field MUST record `status: skipped-ad-hoc` with explicit justification. Implicitly performing the role without invocation OR explicit skip is a §7 violation. Particularly: generating ranked candidates / minimal sets / sufficiency hypotheses is `causal-pruner` work and MUST be flagged as such (also covered by the first rule above). Auditing substrate-evidence outputs is `composite-auditor` work and MUST NOT be done by a single-LLM self-audit pass.
- **HTML report mandatory at conclusion** (scope narrowed by **ADR-0046**: repo agent-session outputs only; webapp-era runs use the frozen record + UI URL + server PDF instead). Any analytical output that reaches a conclusion or checkpoint state MUST emit a self-contained HTML report in `reports/` per the canonical structure in `references/html-report-contract.md`. The structured §5 contract fields MUST appear as visible UI in the HTML body. Conversational responses, status updates, and trivial tool use are exempt. Skipping at conclusion is a §7 violation flag-able by composite-auditor.
- **Simulation-backed visual mandatory** (medium re-scoped by **ADR-0046** for webapp-era runs: the interactive viz renders in the UI from the frozen record — the *principle* stands, static images remain insufficient). If a conclusion is backed by simulation output (`morpheus-4d-viz`, `causal-ablation-cascade-sim`, `squidiff-in-silico-gate`, BioDynaMo, `sim-orchestrator`, or any other simulator), the HTML report MUST include or cross-link a TYPE C interactive visualization (Three.js scene, scrubable timeline, or equivalent). Static screenshot is NOT sufficient — the visual must be self-contained and interactively explorable. Conclusions presented WITHOUT the simulation's TYPE C viz fail to materialize substrate evidence.

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
| Which catalog agent should be invoked given this work-type? | `skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md` |
| What HTML structure should my conclusion report follow? Which TYPE? | `skills/custom/organogenesis-agent-architect/references/html-report-contract.md` |
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
| How do I resolve / verify an external identifier (gene ID, accession)? | `analysis/scripts/lib/resolve_id.py` + `analysis/outputs/verified_identifiers.json` (DATA INAMOVIBLE v1); gate: `lib/verify_output.py` |
| How do I query the shared DATA INAMOVIBLE corpus (semantic GraphRAG)? | via the **`data-inamovible` MCP server** (`rag_index/mcp_server/`): tools `query_data_inamovible` (semantic) + `resolve_identifier` (deterministic) + **`fetch_raw`** (drill from a chunk to the raw data, ADR-0021). Hosted Neo4j GraphRAG on Dokploy (ADR-0020); dev = local sparse `rag_backend.py`. Deploy: `rag_index/deploy/DOKPLOY_DEPLOYMENT.md`. **Robust primary front door = the `witt-di` CLI** (`rag_index/mcp_server/cli.py`: `query\|resolve\|fetch\|health`) — same backend, surfaces the `degraded` marker, no per-session MCP registration (hybrid, **CLI-primary**; the MCP is an optional read-only enhancement, ADR-0040). |
| How does a non-technical Latido teammate get set up (query/resolve/fetch/ingest, same as the founder)? | **`GUIA_MEDICOS.md`** (4 steps + a paste-into-Claude-Code prompt). Access model: local `.secrets/deploy.env` (shared credential) distributed via the team Drive; ADR-0040. Technical/dev onboarding stays in `ONBOARDING.md`. |
| Where does the RAW data live (when a chunk/embedding isn't enough)? | **Raw store, hybrid (ADR-0021):** public sources = source-pointer (URL+sha256, re-downloaded); private/derived = mirrored to self-hosted **MinIO** on Dokploy. `analysis/scripts/lib/raw_store.py`; resolve via the `fetch_raw` MCP tool. The graph is the guide; the raw store is the backing. |
| How does a teammate add data to the DATA INAMOVIBLE (human-gated)? | **`CONTRIBUTING.md`**. Repo-side: `add_dataset.py` (propose) → human review → `approve_dataset.py` (gate + ingest). Hosted (no repo/creds): the **ingest service** (`rag_index/ingest_service/`, submit token → admin `/approve` gate → ingest + git push-back). IDs never minted (resolve_id gate). |
| Where is the autoresearch discipline + the 11 PRs / 20-gap triage? | `docs/autoresearch-handoff/` (STRATEGY_FINAL, INTEGRATION_PROPOSAL, program.v3, PRE-1, gap-triage, proposals/) |
| Where is the reasoning-improvement-loop ledger (calibration, governance queue)? | `substrate_calibration/retrospectives/` (seeds; full RIL is Cycle 3, ADR-0009) |
| Did I consult the repo before generating my output? | This file §10 |
| Did I invoke the right agents for this work-type? | This file §11 + `agent-invocation-matrix.md` |
| How do I run/replay the MITAD_A accountability gates (R1–R4)? | `substrate_calibration/tools/{replay_and_regress,governance_prefilter,build_regression_cases,accountability_checks,world_state}.py` (read-and-report, zero DI mutation; ADR-0023–0026) + `verify_output.admissible()`/`tier_weight` (R2). The §4/§7/§11 reflexes now have **executable enforcers**; per-R detail in `docs/HANDOFF.md`. |
| Where is the generation half (MITAD_B)? | A **separate sibling repo** `conciencia-universal` (`Emma-NukeAI/conciencia-universal`, NOT this repo). Reads the DATA INAMOVIBLE read-only via the MCP, never mutates A; default A1 proposal-only. See its `docs/A_B_CONTRACT.md`. |

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
7. **Identifier preflight is now a function call (GWT v1.1).** For any external identifier (gene symbol, ENSDARG, accession), call `resolve(symbol|accession)` from `analysis/scripts/lib/resolve_id.py` against the verified store (DATA INAMOVIBLE v1) BEFORE using it. `NOT_FOUND` means "looked, absent" → verify against the authoritative source and cache the raw response (§7.9) before use. Never recall an ID from memory.
8. **Read `substrate_calibration/retrospectives/next_session_prepend.md`** (the RIL digest the `retrospector` regenerates each run — top recurring mistakes + standing lessons + current auto-cap state) AND the open `governance_queue.jsonl` (human-gated proposals). This is the loop-closing reflex: future sessions learn from prior sessions' mistakes. Regenerate it with `python substrate_calibration/tools/retrospect.py` if stale. (RIL_PROGRAM.md governs; ADR-0009/0013/0016.)

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

## 11. Agent-invocation preflight (mandatory before any substrate-instrumented output)

Parallel to §10 (which forces *project-state* consultation), this reflex forces *catalog-agent* consultation. Before generating any structured output that contributes to substrate evidence (any output contract per §5 with `confidence` and `framework_applied`), the agent MUST inspect:

1. **What is the dominant work-type** of the output being produced? (e.g., generating ranked candidates, auditing substrate evidence, integrating multi-modal evidence)
2. **Which catalog agents own this work-type?** Consult `skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md`.
3. **Will the agent be invoked, or operate ad-hoc?** Either invoke via `Agent` tool / skill / sub-process, OR explicitly skip with justification.
4. **Populate the output contract's `agents_invoked` field** accordingly.

**Schema of the `agents_invoked` field:**

```json
"agents_invoked": [
  {
    "agent": "causal-pruner",
    "status": "invoked",
    "invocation_id": "<agent task ID or invocation reference>",
    "evidence_generated": ["test_1", "test_4"]
  },
  {
    "agent": "reasoning-exposer",
    "status": "skipped-ad-hoc",
    "reason": "Work was a single-file edit not producing substrate evidence; reasoning-exposer overhead disproportionate to scope."
  },
  {
    "agent": "evaluation-runner",
    "status": "not-applicable",
    "reason": "No perturbation evaluation against held-out set in this output."
  }
]
```

**Why this is a hard reflex.**

CLAUDE.md §7 already enforces several agent-invocation rules (causal-pruner human gate, composite-auditor for substrate audit). But the May 8-9 and May 14 2026 sessions both demonstrated that **rules in §7 don't bind without a reflex**. The §10 preflight succeeded at fixing the "verify-before-claim" gap because it specifies explicit commands at decision time. §11 applies the same pattern to agent invocation: the matrix is the lookup; the `agents_invoked` field is the audit trail; the explicit skip-with-justification is the safety valve when the matrix overshoots.

**Skip-with-justification is allowed but tracked.** A short, work-specific justification (not boilerplate) is required. Periodic `composite-auditor` audits over skip justifications detect gaming (e.g., always skipping the same agent without genuine reason).

**Scope.**

Applies to: any output that populates the §5 contract (structured outputs with confidence/evidence/framework), claim records under `substrate_calibration/records/`, retrospectives, audit gates, ranked candidate lists, sufficiency hypotheses, cross-modal syntheses.
Does NOT apply to: conversational responses, trivial file operations, search queries that don't produce substrate evidence, status updates.

**Substrate evidence:** this reflex generates Test 1 (orchestration evidence) and Test 2 (agentic-workflow evidence) directly. Skip-with-justification entries become Test 4 calibration signal (over time, which agents are systematically skipped reveals coverage gaps).

**Closing sub-step — visual-offer reflex (v2.5):** at conclusion / checkpoint, after emitting the mandatory HTML report (per §5 + §7 hard rules), the agent MUST offer the user additional visual artifacts (3D Three.js scrubable viz, side-by-side comparison, animated timeline, heatmap, signature-cards closure). The offer is a single-line question with 2-4 options + "seguimos como está" as the close-checkpoint default. Templates and format per `references/html-report-contract.md` §11. The offer is opt-in additive, never opt-out. Skip is allowed but tracked in `agents_invoked` with `status: skipped-ad-hoc` and reason. Persistence within session: do NOT re-ask the same conclusion if user already declined; re-ask permitted when conclusion changes (new evidence, version bump).

---

## 12. Footer

- **Bundle:** **GWT v1.1** (umbrella label; **supersedes the prior `v2.5` bundle** — label reset per ADR-0010, prior v2.x history preserved here). "GWT" = the unified Witt × Organogenesis system; record the acronym's full expansion here when confirmed. Individual component SemVers keep their own numbering (below) and are NOT reset.
- **Last updated:** 2026-08-09 (**correcciones pre-UI del backend**, rama `fix/backend-pre-ui`, derivadas del handoff de la webapp `witt-ui-lab/05-backend/` (decisiones del fundador 2026-08-04): (1) **verificación 10/10** de las afirmaciones del handoff contra el código, con 2 matices nuevos — el sobre del CLI heredaba el hueco de 0-hits (derivaba el marcador de metadata por-hit) y la colisión de bundles era *cualquier-día-para-siempre* (DATE constante), no mismo-día. (2) **ADR-0043**: sobre `{degraded, n_hits, hits}` end-to-end (server/MCP/CLI; fuente = `HitList.degraded`, jamás re-derivado de hits) + enum `retrieval.mode` de 4 literales **nunca-nullable** en el bundle + `retrieval_summary` worst-of-n declarado + gate `smoke_degraded_envelope.py` **12/12** offline (cierra "degradado y vacío ≡ sano y vacío", el trap 07-18/19 en el borde vacío). (3) **ADR-0044**: identidad de bundle — `answer_bundle_<run_id>.json`, `stamp` = timestamp real, `bundle_identity.sha256` re-estampada en `record_audit` (cierra la colisión slug+DATE). (4) **ADR-0045**: ingest service v1.1 — `/reject` archiva con autor+razón (404/400 reales, nunca borra), `/approve` serializado in-process, `created_at`+FIFO real, `actions_log.jsonl` (semilla del registro de cambios a la DI); `smoke_ingest_gate.py` **10/10** offline con Neo4j/GitHub stubbeados. (5) sync doc↔repo → `doc_coherence_check` **7/7**. Store **113 sin cambio — cero mutación DI**. Sin reporte HTML por decisión del fundador 2026-08-04 (**ADR-0046**, alcance definido 2026-08-09: derogación SOLO para corridas de la era webapp — rastro = registro congelado + URL + PDF de servidor; los reportes históricos permanecen en master y la webapp los indexa; sesiones de repo conservan §5/§7). Las 5 decisiones de arquitectura quedaron cerradas el mismo día (**ADR-0047**): Postgres en Dokploy · el backend persiste el registro congelado y la webapp solo lee · auditoría en el 100% de las corridas (incl. DI_SUFFICIENT, sin caps) · panel Opus+Sonnet+Haiku+gpt-4o (Fable-5 excluido) · query_service en red interna Dokploy con la webapp como única superficie expuesta. **Bloque 1.4 entregado** (mismo ADR): `last_error`+`index_version`+`store_version` en el sobre, `record` binding (tier/approval_chain) por hit CORPUS-*, `_resolve` con el VerifiedRecord completo + `tier_weight` etiquetado; smoke 17/17. **Bloque 2 entregado** (**ADR-0048**): `rag_index/query_service/` — FastAPI de SOLO lectura que espeja el sobre verbatim (`/query|/resolve|/raw` + alias `/rack/*`), `/status` = StoreStatus 9-campos **NO-SPEND** con caché TTL (OFFLINE honesto, jamás cifras inventadas), identidad 5 cuentas planas (scrypt stdlib, tokens hasheados, admin SOLO local vía `seed_users.py`; Postgres Dokploy / SQLite dev vía `WITT_BACKEND_DB_URL`), índice de históricos ADR-0046 (48 reports + runs con `instrumented:false`, path-safety por membresía), 4 trampas heredadas resueltas (sklearn main-thread en lifespan, pin, secrets, `DI_QUERY_POOL_SIZE`); smoke **20/20** offline. Infra desplegada y verificada EN VIVO 2026-08-09/10 (Postgres `rag-wittbackenddb-qxzrgu` + `witt-query-service` sin puertos públicos + seed 5 cuentas + `/status` ONLINE; gotcha `NEO4J_URI` interno documentado). **Bloque 3 entregado** (**ADR-0049/ADR-0050**): `composite_auditor.py` **invocable** (panel Opus+Sonnet+Haiku+gpt-4o, lentes adversariales, worst-of-N, <3 válidos NUNCA aprueba, vocabulario `APPROVE|APPROVE_MINOR|REVISE` + `source_vocabulary`, jueces errados excluidos y registrados, `record_audit` gana su primer llamador real) · **máquina de estados reformada** (`DI_SUFFICIENT` intermedio — auditoría en el 100% de las corridas, terminal = `AUDIT_APPROVED|REJECTED`) · **modelo de corrida** (`queued→running→awaiting_closure→closed` + `failed`/`cancelled` de primera clase, latido anti-deadlock, cierre explícito) · **bitácora única** `run_events` (replay == traza viva SSE) · **registro congelado persistido en el backend** (Postgres; la webapp solo lee `GET /runs/{id}/record`); síntesis v1 opus + gate determinista entregado al panel (fix ADR-0038); smoke **19/19** offline. **Verificado EN VIVO 2026-08-10**: primera corrida real (`a361f566…`, wt1a/pronephros, panel live con spend) completó `queued→…→closed` con `frozen_at 2026-08-10T03:12:15Z` — el primer registro congelado y cerrado del sistema. **Bloque 4 entregado 2026-08-10** (**ADR-0051**, `render_contract_version` 1.1): dos pasadas (pass1 SIEMPRE DI-only; pass2 solo con fallback; ambas confianzas + **delta** persistidos) · **decisor de fallback por confianza** (`pass1 < τ=0.5` o ausente → Ruta B; `fallback.trigger ∈ {structural, confidence}` declarado — cierra en producto el hallazgo any-chunk de la corrida #1) · `confidence_by_subclaim` + `absence_kind` estructurado (no-evidence-retrieved ≠ evidence-of-no-effect, el catch de Sonnet) + disciplina 3-estados (`absent-not-calibratable`, jamás null silencioso) · **citas tipadas** serie numérica (letras reservadas a precedente) · **TokenUsage** medido by_model incl. embeddings reales (`embeddings.py` cuenta `resp.usage`) + costo etiquetado PROYECCIÓN; smoke **27/27** offline. **Bloques 5 y 6 entregados 2026-08-10**: **ADR-0052** (ingest v1.2 — lock de escritura CROSS-PROCESO con 503 honesto y stale-takeover; `GET /pending/{sid}` = la propuesta completa, el gate ya no firma a ciegas; `GET /actions` = read path del histórico 9-bis; smoke 15/15; el PAT del push-back y el `/approve` e2e hosted quedan gateados por el fundador) · **ADR-0053** (capa de precedente: `PrecedentItem` = corrida CERRADA, `GET /precedent/search` por relevancia con scorer DECLARADO tfidf|token-overlap-fallback, `admissible_as_evidence: false` ESTRUCTURAL — el gate es ciego a procedencia, la regla vive en el producto; series de citas disjuntas por construcción con `serialize_disjoint`/`validate_disjoint`, números=evidencia/letras=precedente; smoke 15/15). PAT hecho + **e2e del gate hosted EJERCIDO 2026-08-10 (ADR-0054)**: push-back estrenado (commits autónomos del servicio), DI +1 registro neto (CORPUS-2026-0009, la evidencia wt1a↔pronefros que pidió la corrida #1), **primer prune human-gated** (duplicado 0010 por carrera de swap del autodeploy), estado del gate al volumen. Watch Paths hechos. **LOTE BACKEND 01·A entregado 2026-08-15 (ADR-0055)**: 8 gaps de contrato reportados por la webapp (M1–M3) — lista /runs via _run_view (latido+umbral+usage), cancel con autor/razón, usage en TODO camino de salida, 409 index_offline server-side (override sparse-dev), GET /taxonomia con procedencia, taxonomy_axes declarado nunca-por-/resolve, /status +integrity honesto +embed_model_changed_at (config_history.json); smokes 32/32+25/25; migración aditiva de columnas. PENDIENTE Emmanuel: ¿/status sin auth para el cintillo pre-login? Quedan: LOTE B con sus módulos (plan M3, ratings M5, browse/default-deny, PDF M4, precedente poblado M6), normalización metadata §5.9, migrar `run_held_out` al run model.) Prior: 2026-07-19 (**data-inamovible team-ready + banco de calibración**: (1) **banco de calibración v1** (2026-07-18) — 30 preguntas para que 4 médicos de Latido califiquen DOS ejes (input=preguntas · output=respuestas), CSV→Google Sheets + `score_calibration.py` determinista, scoring a ciegas — el **gold-set humano** que ningún LLM/compute sustituye. (2) **data-inamovible MCP portable/reproducible** (**ADR-0039**): lanzado por `uv run --locked` desde el `.mcp.json` versionado + `pyproject.toml`/`uv.lock` pineado (cierra la causa raíz "intérprete sin neo4j" del incidente 07-18/19); gate determinista `rag_index/mcp_server/smoke_rag.py` **6/6**. (3) **auditoría de perfección** (13-agente CoVe/composite-auditor sobre embedding+ingesta+consulta y ambos MCPs) + **hardening** (**ADR-0040**): **marcador de degradación in-band** (`HitList.degraded` — cierra el sparse-disfrazado-de-semántico, el modo de fallo del incidente), **gate humano ESTRUCTURAL** (`rag_backend.is_approved` filtra `gather_documents` + el loop de entidades de `ingest.py`), `bge→openai` default en las rutas de ESCRITURA cuando hay `NEO4J_URI`, guardrail anti-contaminación del `.venv` (`uv pip install tooluniverse` fue la causa raíz), y **CLI `witt-di query|resolve|fetch|health`** como front door robusto — **híbrido, CLI-primario**; el MCP es enhancement opcional y **sigue read-only** (la mutación no se expuso como tool MCP). (4) **acceso del equipo (Opción A)** = `.secrets/deploy.env` local (credencial **compartida**) distribuido por Drive + `GUIA_MEDICOS.md` (guía de 4 pasos + prompt para pegar en Claude Code); Opción B (MCP remoto hosted, secretos server-side, bearer por médico — factible SIN OAuth server) **DIFERIDA**. Store **74** sin cambio esta sesión. Validado **read-only, cero mutación**: DI sweep 20/20 · MCP handshake real 5/5 (semantic 0.804) · smoke 6/6 · marker unit 4/4 · gate 9/9 · CLI e2e (degradación forzada → exit 3). Pusheado a `origin/master` FF (`aa4a61e`); commits `b902e1f`+`aa4a61e`. Reports `2026-07-19_{data-inamovible-mcp-perfection-audit,data-inamovible-acceso-equipo-arquitectura}_v1.html`). Prior: 2026-07-11 (**held-out baseline + Tool Universe fallback study**: A1 `month_0` baseline via `evaluation/run_held_out.py` — Test 3 scaffold→**measured** (30/30, real EPS), Test 4 degenerate→**non-degenerate** (n=13, ECE_raw 0.58, under-confidence); reviewer independence measured (34% inter-family divergence); DI+Tool-Universe fallback is **confidence-gated** (the model's own confidence < τ decides insufficiency, not a structural check, not a human gate — the human gate is at re-ingest); **Level-2 agentic Tool Universe tool-use is the lever** (conf 0.14→0.71, quality 0.60→0.84 on 6 Q); **ADR-0035** human-gated DI ADD +23 induction-cascade IDs re-verified vs Ensembl (store **51→74**); **ADR-0036** verify_output gains a `reingest_candidate` category — a live-verified out-of-store ID (§7.9 raw-cache backed) is a re-ingest candidate, NOT a fabrication fail (closes the ADR-0035 deferred; default pass/fail verdict unchanged); **ADR-0037** CLOSING composite-audit (7 claims × 3 adversarial families) → **all 7 REVISE, 0 CONFIRMED**: caught a real `run_held_out` parser bug (8/30 confidences leaked as text → corrected A1 to n=20, accuracy 0.85, ECE 0.51) + a judge-fabrication flaw + systematic over-claiming; all headlines walked back to "measured + audited-and-corrected, NOT validated"; **ADR-0038** honesty-bundle (the audit's cheap fixes): cross-PROVIDER **OpenAI/gpt-4o judge** added to the panel (real independence — cross-provider agreement 5/6 > within-Anthropic, i.e. the internal "divergence" was tier noise), judge-fabrication fix (judges are handed the deterministic check + forbidden to invent verification), deterministic-first `primary_signal` labeling; reports `2026-07-11_*.html`). Prior: 2026-07-05 (**full-functionality audit + composite-auditor + external Fable-5 review**: contract `smoke_contract.py` 30/34 PASS, selftest 17/17, live stack exercised; internal panel 2×APPROVE_MINOR + 1×REVISE + **external Fable-5 auditor** (`docs/EXTERNAL_AUDIT_{BRIEF,FABLE5_REVIEW}.md`); **ADR-0030** compute_ece verb fix; **ADR-0031** multi-family audit panels (reviewer independence), **ADR-0032** measure-the-controls (`retrieval_eval.py` + `store_integrity_scan.py`), **ADR-0033** security-hardening (**Proposed, DEFERRED — no action now** per founder direction; parked finding), **ADR-0034** freeze substrate feature growth until controls earn their weight; audit report `reports/2026-07-05_full-functionality-audit_composite.html`). Prior: 2026-07-04 (**contract-coherence pass**: synced §12 to the real store (51 records) / ADRs (0027–0029); drift gate `doc_coherence_check.py` + opt-in `.githooks/pre-commit`; **§6 no-hang MCP rule** + read-only MCP allowlist in `.claude/settings.json`). Prior: 2026-06-23 (**MITAD_A detection-hardening** ADR-0027 + **lens-validity guard** ADR-0028 + **DATA INAMOVIBLE grew 46→51** human-gated ADR-0029; full-pipeline E2E test, 3 rounds; master `66e6afc`). Prior: 2026-06-18 (**MITAD_A reinforced R1–R4**, ADR-0023–0026, commit `8ba31a4`; **MITAD_B bootstrapped** as the separate sibling repo `conciencia-universal`); 2026-06-13 (GWT v1.1 Cycles 1–5 + hosted deployment, ADR-0021).
- **Code home:** the project's canonical git remote is the **private** repo `Emma-NukeAI/Witt-organo` (`origin`); the prior `polimatartificial-bot/witt-organogenesis` is retained as `polimat-old`. Push only to the private origin (CLAUDE.md §7: nothing secret in git).
- **GWT v1.1 bundle synchronized to:** `organogenesis-agent-architect@2.3.0` · `reasoning-frameworks-catalog@1.2` · `substrate-evidence-guide@1.4` · `method-selection@1.2` · `agent-invocation-matrix@1.2` · `html-report-contract@1.0` · `PROJECT_SCOPE@1.4` · `causal-ablation-cascade-sim@1.0` · `squidiff-in-silico-gate@2.0.1` · **NEW** `source-of-truth/resolve_id@1.0` · `verified-identifier-store@2026-07-21.3` (**113 records**; 74→93 GATE-2 IDs re-verified for MITAD_B's stress bank + 93→113 S4 penetrance/multi-paper sweep CORPUS-2026-0004..0008, all human-gated — ADR-0041/ADR-0042; prior +23 induction-cascade IDs ADR-0035, +5 signaling markers ADR-0029) · `raw-store@1.0` (MinIO hybrid, ADR-0021) · `ingest-service@1.0` (hosted, human-gated) · `data-inamovible-graphrag@1.0` (Neo4j + OpenAI embeddings, deployed)
- **GWT v1.1 changes vs v2.5 (Cycle 1 applied):** §7 (NEW hard rule: anti-fabrication verification gate via `resolve_id`/`verify_output` over DATA INAMOVIBLE v1) · §8 (rows for the source-of-truth resolver, autoresearch-handoff, RIL ledger) · §10 (preflight step 7 = identifier `resolve()` function call; step 8 = read the RIL ledger) · DATA INAMOVIBLE v1 (`analysis/outputs/verified_identifiers.json`, 32 records) + resolver + gate · fixed the 15/16 wrong-ID corruption in `01_schoels_analysis.py` (ADR-0002 supersede + `docs/findings/2026-06-10-…`) · `compute_ece.py` outcome-mapping fix + ADR-0005 `tests_status` (n=2 "case capture") · 2nd resolved claim record (cites §5 Logic-LM) · RIL ledger seeded (`substrate_calibration/retrospectives/`) · `agent-catalog@2.3.0` (+`hypothesis-generator`, −`investor-relations-drafter` Phase I) · `docs/autoresearch-handoff/` imported + PRE-1 (11→6) + gap-triage (C.11 closed) + PR-01/02/12 · ADR-0008 (ceded slot, Accepted) · ADR-0009 (retrospector/RIL subsystem, Proposed) · ADR-0010 (this rename, Accepted).
- **GWT v1.1 Cycles 2–5 (applied 2026-06-11):** Cycle 2 — `evaluation/held_out_set_v1.json` (30 q, broad zebrafish biomedicine) + `noise_probe.py` (EPS_delta/EPS_pass scaffold) + ADR-0011. Cycle 3 (RIL core) — `RIL_PROGRAM.md` charter + `retrospector` agent (cedes `risk-register-agent`) + `rolling_calibration.py` (per-stream auto-cap) + `retrospect.py` + per-sub-domain ECE + ADR-0009/0012/0014/0016. Cycle 4 — `rag_index/` (13 niches + 9 DBs + manifest) + `corpus_classifier.py` (categorize + audit, human-gated) + composite-auditor p25 + program-manager PIVOT_AFTER + ADR-0015/0017 + PR-05/08/09. Cycle 5 — SKILL.md meta-loop (4 governance templates) + §10 prepend reflex + ADR-0013.
- **GWT v1.1 hosted deployment (applied 2026-06-12/13, ADR-0021):** **Neo4j GraphRAG** live on Dokploy (25 docs / 44 entities / 84 MENTIONS; OpenAI `text-embedding-3-small` 1536-dim, vector index ONLINE) · **MinIO** raw store live (hybrid: public source-pointer + private mirror; `raw_store.py` + `fetch_raw` MCP tool) · **ingest service** live (`rag_index/ingest_service/`: submit token → admin `/approve` gate → ingest + GitHub push-back) · corpus loaded: ZESTA full atlas (13 files / 5.4 GB, source-pointer) + GSE218068 (real expression) · contributor workflow `add_dataset.py`/`approve_dataset.py` + `CONTRIBUTING.md` · chunker `chunk_document.py`. The embedding backend question (ADR-0015 spike) is **resolved**: Neo4j native HNSW + OpenAI embeddings.
- **GWT v1.1 still OPEN / gated:** security hardening of the Dokploy services (close public ports 7474/7687/9100/9101/8077 behind internal network + TLS) · the **"universe" visualization** (View 0, exploration) · multi-family composite-auditor (PR-05, needs budget) · live PIVOT_AFTER / template firing (need accumulated telemetry). The biology re-run of `01_schoels_analysis.py` (full scanpy) is optional — `01b_schoels_remarker.py` already produced the corrected CSVs.
- **MITAD_A R1–R4 + MITAD_B split (applied 2026-06-18, ADR-0023–0026; commit `8ba31a4`):** the concept-bridge analysis (`reports/concept-bridge-*-v1.html`, composite-audited 3/3) mapped Witt as two halves — **accountability** (this repo) + **generation**. The accountability half was reinforced, all reuse-first / read-and-report (zero DI mutation), each closed with an ADR + §5 claim record + composite-auditor ≥3: **R1** loop replay-as-regression + advisory no-regression governance pre-filter + `failure_log`→permanent guards (ADR-0023); **R2** explicit admissibility predicate `H(c)∈{0,1}` + Bayes-purity `tier_weight` (ADR-0024); **R3** executable §4/§11 accountability checkers (ADR-0025); **R4** unified World-State-Transition contract (do-typed `causal_admissible`) + Tool Universe Path-B directive (ADR-0026; R4 audit REVISE→fixed: non-dict crash + cp1252 hardening across the 5 tools). **MITAD_B** = the generation engine (energy layer, epistemic RL, JAX-DSL evolutionary sim, program search) in a **separate sibling repo** `Emma-NukeAI/conciencia-universal` (own `.git`, default A1 proposal-only, reads the DI read-only via MCP, never mutates A; first target = the Energy Layer). Deferred MITAD_A wiring: `compute_ece` per-tier weighting, native WSTS emission by cascade-sim/squidiff, calibrated EVPI.
- **MITAD_A detection-hardening + post-E2E adjustments (applied 2026-06-22/23, ADR-0027–0029):** adversarial validation of MITAD_A found the safety spine irrefutable (read-and-report, human-gated) but the **detection layer** had real bypasses — all hardened same day. **ADR-0027** (commit `ad9e102`; durable smoke `smoke_adr0027_hardening.py` 22/22; composite-auditor 3/3 APPROVE_MINOR): N1 symbol↔ENSDARG **binding** validation (not just ID-exists), W1 strong-signal not-applicable → FAIL, W2/N3 generation detected by structure (`claim_category` no longer a suppressor), N6 `framework_applied` quote validated against the real catalog text, W5 `causal_admissible` only with an explicit WSTS block, N2 tolerant ENSDARG extractor, + latent `compute_ece.load_records` utf-8 fix. **ADR-0028** — `evidence_weighting.py` lens-validity guard (`EVIDENCE_TIER` native_perturbation 1.0 > native_expression 0.7 > ortholog_regulatory 0.5 > pathway_membership 0.2 > absence 0.0 + `overclaim_flag`); known limit: silent when nobody has native role-evidence. **ADR-0029** — DATA INAMOVIBLE grew **46→51** (`store_version 2026-06-11.1`→`2026-06-23.1`), HUMAN-GATED ADD-only: +5 signaling/induction markers (osr1, wnt8a, fgf8a, aldh1a2, cyp26a1), tier RAW, ENSDARG resolved live from Ensembl REST (raw cached §7.9), via the single writer `build_verified_store.py`. New lens tools in `.tooluniverse/tools/` (ZFIN native-perturbation, EuropePMC literature). Cross-cutting lesson (re-caught every E2E round): never read "absent from a lens" as "evidence against"; always cache the raw, not a summary (§7.9).
- **v2.5 changes vs v2.4 (history):** §5 HTML report mandatory at conclusion + 4 TYPES · §7 (HTML-at-conclusion + simulation-backed-viz) · §11 visual-offer reflex · ADR-0007.
- **v2.4 changes vs v2.3 (history):** §4 (section-not-tier citation + framework re-election) · §5 (confidence_by_subclaim + alternatives_considered + agents_invoked) · §6 (raw-response caching) · §7 (self-audit prohibition + catalog-agent invocation discipline) · §11 NEW · ADR-0005/0006.
- **Repo version:** GWT v1.1 — Cycles 1–5 + hosted deployment (ADR-0021) + **MITAD_A R1–R4 reinforcements** (ADR-0023–0026, commit `8ba31a4`) + **detection-hardening + post-E2E adjustments** (ADR-0027–0029, master `66e6afc`); **MITAD_B** bootstrapped as a separate sibling repo (`Emma-NukeAI/conciencia-universal`). Open items: security-hardening · viz · MITAD_B A1 run · zebrafish baseline-expression lens (no clean public JSON API) · pronephros-induction sufficiency (wet-lab GOF only, Phase II) · deferred MITAD_A wiring (compute_ece per-tier, native WSTS emission, calibrated EVPI).
