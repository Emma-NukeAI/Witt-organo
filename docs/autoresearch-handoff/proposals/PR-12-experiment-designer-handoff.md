# PR-12 (SPEC) — `hypothesis-generator` → `experiment-designer` wet-lab handoff

- **Status:** SPEC only (deferred; not applied this cycle).
- **Target:** `experiment-designer` + `regulatory-ethics-advisor` + `bwh-coordinator` blocks in `agent-catalog.md`.
- **Depends on:** PR-01 (`hypothesis-generator` is the upstream generator), PR-10 (2-layer ethics).
- **Closes:** C.9 (the wet-lab handoff was an orphan — mentioned ~14× in the proposal, never specified).

## Problem

INTEGRATION_PROPOSAL references "wet-lab escalation" repeatedly but never defines the handoff: which
sub-field becomes the experiment-designer input, when `regulatory-ethics-advisor` Capa-2 fires, how
`requires_ethics_review` interacts with the designer, and the IACUC lead time. PR-01 makes
`hypothesis-generator` the upstream node, so the safety gap must be closed in the design now.

## Spec — gating order (safety-first; ethics BEFORE any draft)

```
hypothesis-generator (Method 1 wet-lab escalation, requires_ethics_review=true)
   │
   ▼
1. deny-list (Capa 1, deterministic, pre-display)   ── PR-10 ── block on human-embryo / germline-human / GoF-pathogen
   │ (pass)
   ▼
2. schema-validate (the §5 contract + verify_output identifiers)
   │ (pass)
   ▼
3. regulatory-ethics-advisor Capa 2 (LLM-classifier; fires BECAUSE requires_ethics_review=true)
   │ (pass)
   ▼
4. HUMAN GATE (100% — no auto-dispatch; CLAUDE.md §7 compliance never auto-filtered)
   │ (approve)
   ▼
5. experiment-designer drafts the protocol (constructs, injection, chaperone-tissue, assays)
   │
   ▼
6. bwh-coordinator → IACUC submission (zebrafish IACUC lead time ~4–8 weeks — plan accordingly)
```

The invariant: **`requires_ethics_review` fires Capa-2 BEFORE any protocol draft exists.** There is
no window where an unsafe-but-textually-clean hypothesis reaches a draft un-reviewed (the C.10 window
that PR-10 also addresses).

## Acceptance

No `experiment-designer` draft is produced for an escalated hypothesis without (deny-list pass +
Capa-2 pass + human approval) recorded in order. IACUC lead time surfaced to `program-manager`.

## Cycle

Lands with PR-10 (2-layer ethics) in the guardrails sub-track.
