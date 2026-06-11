# 0016 — `RIL_PROGRAM.md` as the canonical Reasoning-Improvement-Loop charter

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** the RIL subsystem, `retrospector`, all substrate-instrumented agents

## Context

The autoresearch discipline lives in a single canonical `program.md` that every run reads and that
carries the §15 human-gated meta-loop. GWT v1.1's reasoning loop needed the same: one in-repo,
accessible, evolving charter — not rules diffused across CLAUDE.md + several reference files. The user
asked specifically whether the loop has "a program.md like Karpathy's methodology" and required it be
accessible and continuously adapting within the project.

## Decision

Create `substrate_calibration/RIL_PROGRAM.md` as the canonical charter (ported from
`docs/autoresearch-handoff/program.v3.md`). It defines: the two cadences (online auto-cap / offline
retrospective), the sacred metrics per stream, the EPS noise discipline (EPS_delta=2σ / EPS_pass=p25),
the per-stream reactive auto-cap (ADR-0014), the rubric (guide §4), the honesty clause, PIVOT_AFTER,
and the human-gated governance meta-loop. **The charter evolves only via a governance-proposal + human
gate** — its own §15-analog applied to itself.

## Alternatives considered

- Keep the rules diffused across CLAUDE.md + substrate-evidence-guide. Rejected: the user explicitly
  wanted one accessible, evolving document (the "program.md" analog); diffusion repeats the
  "rules don't bind without a reflex" failure mode.
- Make it immutable. Rejected: the point is continuous adaptation (autoresearch v2→v3 made continuous).

## Consequences

- Easier: one place defines "what improvement means," "what noise is," and the loop's rules; the
  `retrospector` and all agents read it.
- Committed: charter changes require ADR + governance-proposal (versioned with the bundle).

## Evidence

`docs/autoresearch-handoff/program.v3.md` §15; `substrate_calibration/RIL_PROGRAM.md`; GWT v1.1 plan §5.0.
