# 0008 — Ceded Phase-I agent slot for `hypothesis-generator`

- **Date:** 2026-06-10
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** Phase I agent catalog (cap ≤16), Category 4/5 agents, the autoresearch integration (PR-01)

## Context

Phase I has a hard cap of ≤16 active agents (`agent-catalog.md` "Stage caps to respect"). The
autoresearch integration adds `hypothesis-generator` (PR-01, `INTEGRATION_PROPOSAL.md` §7.1), which
requires ceding one existing slot. CLAUDE.md §7 forbids backwards-incompatible changes to v2.1 agent
designs without an ADR — adding/suspending a catalog agent is exactly that.

## Decision

Add `hypothesis-generator` to Category 4. **Suspend `investor-relations-drafter` in Phase I**
(recover at the Phase-II financing gate). **Preserve `ip-patent-watcher`** — it guards the IP moat
(freedom-to-operate + competitive intel), which is defensibility-critical even in Phase I; this
neutralizes gap C.8. Net Phase-I active count stays **16**.

## Alternatives considered

- **Option A (INTEGRATION_PROPOSAL §3.1):** suspend `ip-patent-watcher`, extend `accumulator`.
  Rejected: cedes the IP moat (the proposal itself flags this tension in C.8).
- **Option B:** suspend both `investor-relations-drafter` AND `ip-patent-watcher`. Rejected:
  over-cedes; only one slot is needed for `hypothesis-generator`.
- **Option C:** merge `hypothesis-generator` into `accumulator`. Rejected: conflates generation
  (Test 3/4 source) with Method-2 thesis aggregation; muddies the case-capture lineage the RIL needs.

## Consequences

- Easier: hypothesis generation has a real catalog surface with the autoresearch disciplines; IP moat intact.
- Harder: monthly investor-update drafting is manual in Phase I until `investor-relations-drafter`
  is reinstated in Phase II.
- Committed: `agent-catalog.md` cap-swap note + the `investor-relations-drafter` suspension block;
  the second slot for `retrospector` is handled separately (ADR-0009).

## Evidence

`docs/autoresearch-handoff/INTEGRATION_PROPOSAL.md` §3.1/§7; `STRATEGY_FINAL.md` §5; `PROJECT_SCOPE.md`
§6 (DATA INAMOVIBLE) + the 4-pillar moat framing; `agent-catalog.md` "Stage caps"; GWT v1.1 plan
§9–§10; PR-01 (`docs/autoresearch-handoff/proposals/PR-01-hypothesis-generator.md`).
