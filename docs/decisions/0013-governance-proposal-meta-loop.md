# 0013 — Governance-proposal meta-loop: the agent proposes, the human applies

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** SKILL.md (meta-loop section), `program-manager`, the RIL, every agent

## Context

The RIL's "learn from its own mistakes" mechanism must improve the *process* (prompts, retrieval,
thresholds, even the charter) — but autoresearch's hardest-won lesson (and the Sakana AI-Scientist
safety incident, where the agent modified its own execution scripts) is that **self-modification must
be human-gated**. autoresearch encodes this in `program.md` §15: the agent MAY write a
governance-proposal; it MUST NOT apply it.

## Decision

Adopt the human-gated governance meta-loop. Any agent MAY write a `governance-proposal` to
`substrate_calibration/retrospectives/governance_queue.jsonl` when it detects a systematic
inefficiency. It MUST NOT self-apply it: `self_applied: false` is an invariant; a `true` entry is
rejected and logged as a violation. A human (via `program-manager`) approves; a design-changing
approval requires an ADR. Four templates are pre-approved (SKILL.md meta-loop section, PR-11):
`domain-recall-drop`, `contradiction-section-empty`, `citation-coverage-drift`,
`sub-domain-calibration-divergence`. The `RIL_PROGRAM.md` charter itself evolves only this way.

## Alternatives considered

- Let the loop auto-apply improvements. Rejected: the Sakana safety lesson (self-editing execution
  scripts) + CLAUDE.md §7 (compliance/process changes never auto-filtered).
- No meta-loop (manual only). Rejected: the point is to institutionalize self-critique so future
  sessions learn; the queue + templates make it structural without removing the human gate.

## Consequences

- Easier: process improvement is captured continuously (autoresearch v2→v3 made continuous) yet safe.
- Care: the queue must be cleared by a human; stale `queued` items do not alter behavior.

## Evidence

`docs/autoresearch-handoff/program.v3.md` §15; the Sakana AI-Scientist self-modification incident
(plan §7 Sakana table); `substrate_calibration/RIL_PROGRAM.md` §7; the Cycle-1 governance_queue seed.
