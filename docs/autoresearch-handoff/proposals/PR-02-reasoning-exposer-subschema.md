# PR-02 (SPEC) — `reasoning-exposer` sub-schema for hypotheses

- **Status:** SPEC only (deferred; not applied this cycle).
- **Target:** `reasoning-exposer` block in `agent-catalog.md`.
- **Depends on:** PR-01, ADR-0008, PRE-1 (11→6 mapping).
- **Closes:** C.17 (single-LLM auditor anti-pattern reintroduced), C.13 (KG anti-pattern in schema).

## Problem

INTEGRATION_PROPOSAL has `reasoning-exposer` validate that `contradictory_evidence_cited` is
non-empty AND that the cited paper *actually contradicts* — a **semantic** check. A single LLM doing
semantic contradiction-validation is exactly the single-LLM-auditor anti-pattern that
`composite-auditor` replaced (CLAUDE.md §7).

## Spec — split syntactic vs semantic

1. **`reasoning-exposer` does the SYNTACTIC check only** (deterministic, cheap, middleware):
   - the 6 §5 fields are present;
   - `alternatives_considered.contradictory_evidence_cited` is **present and non-empty**;
   - `gap_flags` carries the three PRE-1 sub-keys (`gaps_in_literature`, `required_controls`,
     `possible_confounders`);
   - `framework_applied` cites a specific `§<n>` with a quoted criterion (rejects `§Tier N`);
   - external identifiers pass `verify_output` (the §6.4 gate).
2. **The SEMANTIC check** ("does the cited paper actually contradict?") routes to `composite-auditor`
   (Self-Consistency vote) or a human rater — never a single-LLM pass.
3. **Trim the schema to day-1 fields (closes C.13):** no pre-committed `pipeline_config` sub-graph;
   add fields only when bottleneck evidence appears (Magraner Aug 2025).

## Acceptance

A hypothesis with an empty contradiction section is **rejected by the syntactic gate** before it can
reach a semantic check. A `§Tier 2` citation is rejected. No single LLM renders a contradiction
verdict.

## Cycle

Lands after PR-01 is live and PRE-1 is validated; pairs with PR-05 (composite-auditor thresholds).
