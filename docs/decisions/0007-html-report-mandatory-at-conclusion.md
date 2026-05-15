# ADR 0007 — HTML report mandatory at conclusion / checkpoint

- **Date:** 2026-05-14
- **Status:** Accepted
- **Decided by:** Emmanuel (Nuke AI) — surfaced post-composite-audit SESS-2026-05-14, plan approved 2026-05-14
- **Affects:** `CLAUDE.md` (§5, §7, §8, §11, footer → v2.5), `substrate-evidence-guide.md` v1.3 → v1.4, `agent-invocation-matrix.md` v1.0 → v1.1, `html-report-contract.md` (NEW)

## Context

The composite audit of SESS-2026-05-14 documented in `docs/findings/2026-05-14-composite-audit-meta-conclusion.md` showed that the project has produced HTML reports as substrate evidence consistently — but the rule for *when* an HTML report must be emitted has been **implicit**, not contractual. The session retrospective surfaced this gap when the user asked: *"todavía no tenemos definido exactamente en qué momento se emite un reporte de HTML."*

Through May 2026 the project produced ~8 HTML reports in `reports/` and `docs/reports/` following 4 implicit TYPES (comprehensive analytical, interactive viz grid, simulation-backed Three.js, formal retrospective). These exemplars are coherent and high-quality but their emission was discretionary at the agent's judgment.

Three operational gaps motivate this ADR:

1. **Missing trigger condition.** When does a session "reach a conclusion" that requires HTML? Without a rule, an agent may close a session with prose-only or claim-record-only output, which fails to materialize the structured §5 contract as visible UI.
2. **Missing simulation-backed mandate.** If a conclusion is supported by a simulation (Morpheus, Squidiff, BioDynaMo, causal-ablation-cascade-sim), the visual proof is currently optional. Conclusions presented WITHOUT the simulation's TYPE C visualization weaken the substrate evidence and can be cited downstream as if no simulation backed them.
3. **Missing checkpoint reflex.** Users frequently ask for additional visuals (3D viz, side-by-side, animated timeline) AFTER the base output is delivered. Making this proactively offered at every checkpoint reduces friction and ensures the substrate captures the full range of expert-amplified outputs.

The user's intent is captured in three sub-requests:
1. HTML report MANDATORY at conclusion / checkpoint — *"no podemos responder una pregunta y llegar a una conclusión sin emitir un reporte en HTML."*
2. Visual-offer reflex — *"siempre le preguntamos al usuario si quiere algo visual."*
3. Simulation-backed mandatory viz — *"si el reporte lo avala (es decir, si se hizo alguna simulación), me gustaría que siempre pase por un ejemplo visual."*

## Decision

Adopt **HTML report emission as a project-level Hard Rule** with three coordinated mechanisms:

### 1. HTML emission rule (CLAUDE.md §5 + §7)

At conclusion or checkpoint of any analytical work that produces substrate evidence (any output matching §5 contract), the agent MUST emit a self-contained HTML report in `reports/`. The structured contract fields (direct_answer, confidence, evidence_cited, alternatives_considered, gap_flags, framework_applied, agents_invoked) MUST appear as **visible UI elements** in the HTML body — NOT only as metadata or hidden script. Pure markdown / JSON reports do NOT satisfy this requirement for substrate-evidence outputs.

The new `references/html-report-contract.md` defines:
- The 4 TYPES (A comprehensive analytical, B interactive viz grid, C simulation-backed Three.js, D formal retrospective)
- 8 mandatory sections per HTML regardless of TYPE
- Required visible UI elements per §5 contract field
- CSS conventions (dark for analysis, light for retrospective; do NOT mix)
- Data embedding pattern (inline `<script>const X = [...]</script>`; NO external files)
- Naming convention per ADR-0002 (version preservation)

### 2. Simulation-backed visual mandatory (CLAUDE.md §7 hard rule)

If a conclusion is backed by simulation output (`morpheus-4d-viz`, `causal-ablation-cascade-sim`, `squidiff-in-silico-gate`, BioDynaMo, `sim-orchestrator`, or any future simulator), the HTML report MUST include or cross-link a TYPE C interactive visualization. Static screenshot is NOT sufficient. The visual must be self-contained and interactively explorable (scrub, click, orbit controls).

### 3. Visual-offer reflex (CLAUDE.md §11 sub-step)

After emitting the mandatory base HTML, the agent MUST ask the user one single-line question offering additional visual artifacts (3D Three.js scrubable scene, side-by-side comparison, animated timeline, heatmaps, etc.). The offer is **opt-in additive** — user's "seguimos como está" closes the checkpoint. Skip is permitted but tracked in `agents_invoked` with `status: skipped-ad-hoc` and reason.

### Trigger conditions (per html-report-contract.md §10)

**Required:**
- Any §5 contract output (substrate-instrumented)
- User signals end-of-inquiry
- Phase or named checkpoint completes
- Substantive analytical question with confidence ≥ 0.5
- Composite audit / retrospective / meta-analysis
- Claim record written

**Exempt:**
- Conversational responses without analytical claim
- Status updates
- Trivial file operations
- Pure search / tool-use producing no substrate evidence
- Sub-tasks within a larger session (only the final conclusion triggers)
- Plan mode planning (plan file is the artifact)

## Alternatives considered

1. **Keep emission discretionary** (status quo). Rejected: the composite audit 2026-05-14 surfaced this exact gap as systemic. Discretion led to inconsistent substrate evidence — some conclusions in prose only, some in HTML, no rule for which.

2. **HTML emission at every output regardless of substance.** Rejected: would produce HTML for trivial / conversational responses, worsening the artifact-proliferation anti-pattern (AP-N9 from composite audit). Better: clear TRIGGER vs EXEMPT list.

3. **Mandatory HTML but no TYPE specification.** Rejected: would produce inconsistent aesthetics and section structures, defeating the audit-trail purpose. The 4 TYPES already exist organically; codifying them is the lower-cost decision.

4. **Build a `report-html-emitter` skill that intercepts substrate outputs.** Considered, deferred. The rule + matrix entry + visible §5 fields are sufficient as a forcing function for now. A dedicated skill could be added if v2.5 enforcement proves insufficient (parallel to how a skill could enforce §11 agent-invocation matrix).

5. **Allow markdown reports to satisfy the rule.** Rejected: markdown renders inconsistently across surfaces (GitHub, VS Code, CLI, web). HTML guarantees the audit trail looks the same wherever it's opened — and provides interactivity (modals, click-to-expand, embedded data) that markdown cannot.

6. **Simulation-backed viz as recommendation, not hard rule.** Rejected: too easy to skip when a simulation IS the central evidence. The viz is the proof; making it optional weakens substrate evidence quality.

## Consequences

**Positive:**

- Every conclusion produces a citable, self-contained artifact. Future sessions / external reviewers can open one HTML and see the entire reasoning chain visibly.
- Simulation outputs are no longer "buried" in JSON or summary text — the visualization is the audit trail.
- The visual-offer reflex captures user-amplified extras systematically, generating richer substrate evidence for Test 1 (orchestration).
- Codifying existing practice doesn't require new infrastructure — the 8 exemplar reports already work and become canonical templates.
- The composite-auditor can now mechanically verify rule compliance: every claim record's `session_id` should reference an HTML file in `reports/`.
- Aligns with Witt's central commitment: *"exposes its reasoning at every step"* (CLAUDE.md §1).

**Negative / costs:**

- Adds HTML-generation overhead at every conclusion. Acceptable for substrate-instrumented work; trivial responses are exempt.
- Self-containment constraint (no external CDN) may bloat TYPE C HTMLs (Three.js bundled). Accepted — the canonical exemplars already do this and remain functional.
- Existing pre-2026-05-14 prose-only reports (e.g., proteomic-evidence v1.0-v1.4 MD files) do NOT comply with new rule. They are **grandfathered** (ADR-0002 preservation) but new equivalents should be HTML from v2.5 forward.
- Mandating CSS conventions (dark vs light) limits stylistic experimentation. Trade-off: visual coherence across the project > novel aesthetics per report.

**Implementation order (executed 2026-05-14 after plan approval):**

1. Write `html-report-contract.md` (NEW reference)
2. Write this ADR-0007
3. Update `CLAUDE.md`: §5 add HTML emission rule, §7 add 2 hard rules, §8 add row, §11 add visual-offer sub-step, footer → v2.5
4. Update `substrate-evidence-guide.md` v1.3 → v1.4 (HTML as Test 1 evidence)
5. Update `agent-invocation-matrix.md` v1.0 → v1.1 (add html-report-emitter Hard Rule row)
6. Update `docs/decisions/README.md` index with ADR-0007 (Accepted)
7. Update `MEMORY.md` with 2 feedback memories
8. Future: `scripts/validate_html_reports.py` schema checker (deferred, not part of this v2.5 bump)

## Evidence

- `docs/findings/2026-05-14-composite-audit-meta-conclusion.md` §4 anti-pattern AP-N9 (artifact proliferation context)
- `docs/findings/2026-05-14-pronephros-proteomics-session-retrospective.md` §3.3 E10 (artifact proliferation as `prueba pequeño` violation — informs the "do not generate 4 parallel views" guidance in html-report-contract.md)
- The 8 canonical exemplar reports listed in `html-report-contract.md` §2 (these are the standard the contract requires)
- Skill-level HTML mandates in `causal-ablation-cascade-sim/SKILL.md` §7-8, `squidiff-in-silico-gate/SKILL.md` Output Format, `morpheus-4d-viz/SKILL.md`
- CLAUDE.md §1: *"exposes its reasoning at every step"* — the substrate's central commitment that this ADR operationalizes for the HTML emission layer
- ADR-0002 (version preservation rule) — naming convention in html-report-contract.md §8 inherits from ADR-0002
- ADR-0006 (catalog agent invocation discipline) — `agents_invoked` field that the new visible-UI mandate makes explicit
