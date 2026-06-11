# 0009 — `retrospector` agent + Reasoning-Improvement Loop (RIL) as a subsystem

- **Date:** 2026-06-10
- **Status:** accepted (2026-06-11 — Cycle 3 built: retrospector catalog block + RIL_PROGRAM.md + tooling)
- **Decided by:** Emmanuel
- **Affects:** Phase I catalog (cap ≤16), substrate-instrumentation category, Test 1/3/4 instrumentation

## Context

The core of GWT v1.1 is a reasoning-improvement loop that (a) auto-corrects confidence during a run
and (b) is analyzable post-run so each iteration improves — and that institutionalizes self-critique
so future sessions learn from their own mistakes. The autoresearch discipline (noise-probe/EPS,
effective frontier, reactive calibration, PIVOT_AFTER, human-gated governance-proposals, honesty
clause) is the proven precedent. A dedicated owner is wanted so the loop is not diffuse.

## Decision

Introduce a new **`retrospector`** agent that owns the RIL: the post-run retrospective (reads the
case ledger + calibration stream + EPS, scores the reasoning trace against the
`research-hypothesis-generation-guide` §4 rubric, writes a self-critique record, regenerates a
`next_session_prepend`) and the governance-proposal queue. The `retrospector`'s self-critique is
**reflection, NOT an audit gate** (CLAUDE.md §7: audit gates use `composite-auditor`). The loop also
extends `calibration-tracker` (reactive K=6 + auto-cap), `evaluation-runner` (noise-probe + effective
frontier), and is governed by a canonical `RIL_PROGRAM.md` charter (analogous to autoresearch
`program.md` §15; ADR-0016). **Full design + the charter land in Cycle 3.** This ADR reserves the
catalog slot now: when `retrospector` is built, **`risk-register-agent` is ceded** in Phase I (its
register folds into `program-manager`); net Phase-I active count stays 16.

## Alternatives considered

- **No new agent — extend existing agents only.** Rejected (Emmanuel): the loop is the heart of the
  upgrade and merits a clear owner; diffusing it across three agents repeats the "rules don't bind
  without a reflex" failure mode.
- **Cede `ip-patent-watcher` for the slot** (INTEGRATION_PROPOSAL Option A). Rejected: preserves the
  IP moat (already decided in ADR-0008); cede the Limited-substrate-evidence `risk-register-agent`
  instead.
- **A persistent 24/7 retrospector service.** Rejected: the `retrospector` is checkpoint-triggered
  batch (session close / on-demand), not a daemon. No server required.

## Consequences

- Easier (Cycle 3+): one owner for the RIL; the autoresearch disciplines have a home; self-critique
  is mechanical (auto-cap + prepend + governance queue).
- Harder: `risk-register-agent`'s register becomes a `program-manager` artifact in Phase I.
- Committed (Cycle 1 already): the RIL ledger schema is seeded under
  `substrate_calibration/retrospectives/` (infrastructure populated, not yet a running subsystem).

## Evidence

`docs/autoresearch-handoff/STRATEGY_FINAL.md` §5; `program.v3.md` §13 (reactive calibration) + §15
(governance meta-loop); GWT v1.1 plan §5, §8; the Cycle-1 RIL seeds
(`substrate_calibration/retrospectives/`); CLAUDE.md §7 (self-audit prohibition).
