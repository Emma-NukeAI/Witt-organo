# autoresearch handoff — imported discipline (read-only reference)

This directory imports the **autoresearch** discipline (Caparzi / Karpathy-`nanochat`-derived
single-GPU research-org experiment, run v1→v2→v3 with a human gate between runs) so the
Witt × Organogenesis repo can port its *disciplines* — noise-probe/EPS, effective frontier,
reactive calibration, PIVOT_AFTER, human-gated governance-proposals, and the honesty clause
(pre-registered confidence) — into the substrate agents.

These four files are **imported copies for reference** (the authoritative originals live in
`c:\Users\Emmanuel\dev\autoresearch\`). Treat them as read-only source material; do not edit
them here — edit the proposals/prerequisites that adapt them.

## Files

- `STRATEGY_FINAL.md` — the discipline (6 prescriptions §5.1–§5.6).
- `INTEGRATION_PROPOSAL.md` — the architecture proposal (Anexo C = 20 gaps C.1–C.20; §7 = 11 PRs/ADRs).
- `research-hypothesis-generation-guide.md` — the reference guide (§1 = the **11-field** output
  contract; §2–§6 = technical setup, data prep, evaluation rubric, stack, phased path). This is
  the canonical reference for the `hypothesis-generator` agent (PR-01) and the corpus classifier.
- `program.v3.md` — the autoresearch `program.md` v3 (the "research-org code"). §15 = the
  human-gated meta-loop. It is the basis for the future `RIL_PROGRAM.md` charter (Cycle 3).

## How this repo adapts them (GWT v1.1)

- `prerequisites/contract-11-to-6-mapping.md` (PRE-1) — maps the guide's 11 fields → the §5
  6-field contract. **Gates PR-02.** Fixes gap C.1 (the "7-field" miscount).
- `prerequisites/gap-triage-C1-C20.md` — disposition (RESOLVE / DEFER / CLOSED) for all 20 gaps,
  with the formal closure of C.11 (the "§15 missing" false positive: §15 exists in `program.v3.md`).
- `proposals/PR-01-hypothesis-generator.md` — the new agent (the only live agent-design change in
  Cycle 1, applied as a block in `agent-catalog.md`).
- `proposals/PR-02-…`, `PR-12-…` — specs only (deferred cycles).

The 11 PRs are generated as **separate proposal artifacts for review**, never one massive commit.
