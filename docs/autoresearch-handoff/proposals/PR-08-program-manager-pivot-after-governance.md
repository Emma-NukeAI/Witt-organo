# PR-08 — `program-manager`: PIVOT_AFTER triggers + governance-queue clearing

- **Status:** APPLIED (catalog note); the governance queue exists (`retrospectives/governance_queue.jsonl`).
- **Target:** `program-manager` block in `agent-catalog.md`.
- **Depends on:** ADR-0009 (RIL), ADR-0013 (meta-loop), the governance queue (Cycle 1 seed).
- **Closes:** part of C.3/C.14 (Test-2 workflow boundaries / Month-4 timing live with the calendar).

## Decision

`program-manager` owns two RIL governance duties:
1. **PIVOT_AFTER:** after 3 consecutive discards (outputs failing `improvement > effective_frontier −
   EPS_delta`), raise a governance-proposal to switch from fine-sweeping one knob to a structural move
   (or stop). Counts `plateau-batch` and `plateau-revision` discards (RIL_PROGRAM §7).
2. **Governance-queue clearing (human gate):** nothing in `governance_queue.jsonl` with `status: queued`
   may alter behavior until a human sets `status: approved` with a non-null `approved_by`. A
   `self_applied: true` entry is rejected + logged as a violation. Approved proposals that change agent
   design require an ADR (`resulting_adr`). `program-manager` also folds the (ceded) `risk-register-agent`
   register in Phase I (ADR-0009).

## Cycle status

- Applied: the catalog note (PIVOT_AFTER + governance-queue ownership). The queue + 1 real proposal
  already exist from Cycle 1.
- Deferred: live PIVOT_AFTER firing needs accumulated discards (sparse now); the Month-4 calendar gate.
