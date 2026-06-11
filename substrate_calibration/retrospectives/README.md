# `retrospectives/` — Reasoning-Improvement Loop (RIL) ledger

**Status (GWT v1.1 Cycle 1): infrastructure populated, NOT a running subsystem.** This directory
holds the RIL ledger seeds. The full `retrospector` agent, the `RIL_PROGRAM.md` charter, the
post-run scorer (`tools/retrospect.py`), and reactive auto-cap are **Cycle 3** (see the plan §5 +
ADR-0009 / ADR-0016, which are Proposed, not yet built). What exists now is the *shape* of the
loop, seeded with real Cycle-1 data so the schema is exercised — "prueba pequeño".

## Files

- `failure_log.jsonl` — append-only structured failure events (one JSON object per line).
- `sessions/retro_<sid>_<ISO>.json` — one self-critique record per completed session.
  Reflection only — **NOT an audit gate** (CLAUDE.md §7: audit gates use `composite-auditor`).
- `governance_queue.jsonl` — governance-proposals. The agent MAY write; it MUST NOT self-apply
  (`self_applied: false` is an invariant). A human approves (program-manager clears the queue).
- `rolling_calibration.json` — reactive K=6 hit-rate tally + auto-cap state (dormant until the
  K=6 window fills; currently 2 resolved predictions).

## Git convention (per the plan §5.1)

`sessions/*.json` + `governance_queue.jsonl` are committed (substrate evidence). `failure_log.jsonl`
is committed (it IS the Test-3 trace) and rotated quarterly. In Cycle 3, `rolling_calibration.json`
and a future `next_session_prepend.md` move to `.gitignore` as derived state.
