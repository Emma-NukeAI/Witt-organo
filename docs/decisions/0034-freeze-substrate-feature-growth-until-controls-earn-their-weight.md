# ADR-0034 — Freeze substrate feature growth until each control earns its weight (and biology moves)

- **Status:** Accepted — from the external review (Fable 5, 2026-07-05, rec 4) + the founder principle "prueba pequeño antes de armar bien."
- **Relates:** PROJECT_SCOPE Operating Principle, ADR-0032 (measure the controls), the 2026-05-31 self-critique (over-engineering flagged internally too).
- **Affects:** project process/policy. No code.

## Context

The external auditor's main disagreement was **proportionality**: for a single-organism POC whose core
biological claim is still unproven, the substrate is "a platform built ahead of the evidence that the
platform's methods improve outcomes." Over-building the **safety spine** (read-only store, human gates) is
defensible — integrity failures are expensive to unwind. But the **retrieval / audit / calibration
superstructure is feature-weight**, and each such control should have to *earn its keep* by catching
something a simpler control would have missed.

This converges with our own signals: the founder's "test small before building well" and the 2026-05-31
self-critique that already flagged over-engineering.

## Decision

**Freeze new substrate subsystems.** Until further notice:

1. **No new substrate subsystem** is built unless an existing, simpler control has demonstrably failed to
   catch a real error that the new one would catch. New *measurement* of existing controls is exempt and
   encouraged (ADR-0032).
2. **Each existing feature-weight control must earn its keep.** For the audit panel, retrieval, and
   calibration, record at least one concrete instance where the control caught a real defect a simpler
   control would have missed — or mark it a candidate for removal.
3. **Calibration waits on real outcomes.** No effort to make calibration "meaningful" beyond the current
   scaffold until wet-lab work supplies enough resolved outcomes (ADR-0030/0032).
4. **The safety spine is exempt** (store read-only + human gates + anti-fabrication gate + deterministic
   checks): over-investment there is the acceptable kind.
5. **Bias toward reuse and deletion.** Prefer wiring/simplifying existing pieces over adding new ones.

## Consequences

- Effort redirects from building to **measuring and validating** what exists, and to the biology.
- A control that cannot show it caught a real error becomes a deletion candidate at the next review —
  proportionality is enforced, not just aspired to.
- Revisit when the biology moves (wet-lab outcomes) or a control demonstrably fails.
