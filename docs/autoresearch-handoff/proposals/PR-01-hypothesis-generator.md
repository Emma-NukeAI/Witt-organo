# PR-01 — Add `hypothesis-generator` to the agent catalog

- **Status:** APPLIED this cycle (the one live agent-design change in Cycle 1).
- **Target:** a block in `skills/custom/organogenesis-agent-architect/references/agent-catalog.md`,
  Category 4 (Knowledge & Strategy). (The proposal's `agents/<name>/SKILL.md` path does not exist;
  all agents are catalog blocks.)
- **Depends on:** PRE-1 (11→6 contract mapping), ADR-0008 (ceded slot).
- **Closes:** C.18 (frontmatter/template). **Cross-links:** PRE-1, PR-02, source-of-truth (Track A).

## Role (6 responsibilities)

1. Take a seed research question (Method 2: from a human; the default).
2. **Consult the source-of-truth interface** (`resolve_id` / `lookup_prior`, DATA INAMOVIBLE v1)
   for verified identifiers + prior artifacts BEFORE generating (CLAUDE.md §10 preflight).
3. Complement via MCP / Tool Universe — verify, complete, and check coverage; a hole → `gap_flag`
   (CLAUDE.md §6; GWT v1.1 §3.3: not exempt from MCP even when the internal DB has data).
4. Produce N candidate hypotheses, each in the §5 contract via PRE-1 (11→6), with the guide's
   example shape (Hypothesis / Rationale / Contradicting evidence / Testable prediction / Experiment
   / Confidence) folded into `direct_answer` + sub-keys.
5. Raise governance-proposal triggers when the contradiction section is empty or domain recall drops.
6. Set `requires_ethics_review` so `regulatory-ethics-advisor` Capa-2 fires BEFORE any wet-lab draft.

## Contract (via PRE-1)

Exactly the 6 §5 fields. `alternatives_considered.contradictory_evidence_cited` is **obligatory and
non-empty** (a candidate with no contradicting evidence is rejected, not emitted). `gap_flags`
carries `gaps_in_literature`, `required_controls`, `possible_confounders`. `framework_applied`
trimmed to day-1 fields only (closes C.13): no pre-committed pipeline_config sub-graph.

## Method & gate

Method 2 default (human drives; the agent instruments). **Method 1 only on wet-lab escalation, with
a 100% human gate** (a hypothesis that proposes a wet-lab experiment is ranked-candidate work →
routes through `causal-pruner` discipline + `regulatory-ethics-advisor` + HUMAN GATE; never
auto-dispatched). `framework_applied` default: Self-Consistency (Tier 1) for ranking candidates;
Logic-LM (Tier 1) when criteria are formalizable. Self-report, not introspection (CLAUDE.md §5).

## Substrate evidence

Test 3 + Test 4 **direct** (each hypothesis is a pre-registered, calibratable prediction feeding the
RIL). Test 1 + Test 2 **deferred** — `gap_flag`: not operationalized yet (C.2/C.3 → PR-04/PR-08).

## Cap accounting (stays 16)

| | Phase I active count |
|---|---|
| before | 16 |
| − `investor-relations-drafter` (suspended Phase I, ADR-0008) | 15 |
| + `hypothesis-generator` | 16 |

`ip-patent-watcher` retained (IP moat → neutralizes C.8). `retrospector` slot reserved separately
(ADR-0009, built Cycle 3; cedes `risk-register-agent` then).

## ≤1024-char bilingual frontmatter draft (closes C.18)

> "Genera hipótesis de investigación calibradas y fundamentadas para Project Organogenesis. Consulta
> la fuente-de-la-verdad (identificadores verificados + artefactos previos) ANTES de generar, y
> complementa con Tool Universe / MCP para verificar y completar. Cada hipótesis trae evidencia a
> favor Y en contra (obligatoria), predicción testable, experimento propuesto, controles, confounders
> y confianza calibrada. Use when someone says: generate a hypothesis, propose a mechanism, what could
> explain X, design a testable prediction, genera una hipótesis, propón un mecanismo, qué explicaría X.
> Method 2 by default; wet-lab escalation requires a 100% human gate. Outputs follow the §5 contract;
> external identifiers are never used from memory (verified + raw-cached first). Bilingüe."

(Character count of the description above is < 1024.)

## Applied catalog block

See `agent-catalog.md` → Category 4 → `### hypothesis-generator` (added this cycle), and the
`investor-relations-drafter` suspension note + the updated "Stage caps to respect" line.
