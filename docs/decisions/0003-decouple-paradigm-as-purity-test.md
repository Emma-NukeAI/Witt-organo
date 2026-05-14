# ADR 0003 — Decouple paradigm: PASA / PARCIAL / FALLA as evidence-purity tripartite

- **Date:** 2026-05-12 (decision); 2026-05-14 (ADR written)
- **Status:** Accepted retroactively
- **Decided by:** cascade session agent, ratified by user
- **Affects:** `skills/custom/causal-ablation-cascade-sim/`, `skills/custom/squidiff-in-silico-gate/` Mode 3 verdicts

## Context

When evaluating whether a perturbation scenario's transcriptomic readout supports the causal hypothesis, a binary "consistent / inconsistent" framing lost too much information. Cases where the readout was partially consistent but missing key markers needed a separate category.

A specific recurring scenario surfaced the need: `2B-KO` in the pronephros cascade produced **preserved transcriptomic identity** with **destructed morphology** — a paradigm case where the morphology decouples from the form. Calling this PASS by transcriptomic-only criteria would over-claim; calling it FAIL would under-claim. The tripartite captures it correctly.

## Decision

Three-state decouple verdict per scenario:

- **PASA:** all predicted markers present + correct direction + within timing window — pure morphological ablation
- **PARCIAL:** predicted markers present in direction but timing off, or partial set — confounded
- **FALLA:** predicted markers absent or in wrong direction — identity contaminated

The verdict is itself a boolean predicate set on transcriptomic readouts, which makes it **formalizable**. This is operationally significant: when criteria are formalizable, **Logic-LM** (Tier 1 framework per `reasoning-frameworks-catalog.md` v1.2) is more appropriate than Self-Consistency. The cascade session used Self-Consistency monolithically across 12 scenarios; the framework rotation gap is documented in `reports/retrospective-sesion-cascada.html` §4.4 and addressed prospectively by CLAUDE.md §4 catalog citation requirement (Phase A.4).

## Alternatives considered

- **Binary PASA / FALLA:** rejected as too lossy. The 2B-KO paradigm case has no clean home.
- **Continuous probability score:** rejected because human reviewers needed a discrete signal for downstream decisions.
- **5-state granularity (e.g., STRONG-PASA / PASA / PARCIAL / FALLA / STRONG-FALLA):** rejected — added complexity without operational distinction; the user's downstream wet-lab decisions don't differentiate strong-PASA from PASA.
- **4-state with PASS-DECOUPLE as separate:** adopted in `squidiff-in-silico-gate` Mode 3 cross-verdict (PASS / PASS-DECOUPLE / MODERATE / FAIL). The PASS-DECOUPLE state is the paradigm case 2B-KO occupies — it extends the tripartite when paired with morphology evidence (Morpheus).

## Consequences

- Cascade reports use the tripartite verdict consistently.
- The decouple verdict feeds into `substrate_calibration/` records via `expected_outcome_if_h1` and `observed_outcome` fields.
- Logic-LM is now the preferred framework for scenario-level verdict assignment; Self-Consistency is appropriate only when the criteria are not formalized.
- `squidiff-in-silico-gate` cross-verdict (Mode 3) inherits this tripartite logic via the morpheus-pairing contract — see `morphology_decouple` field with values `pass | partial | fail | pass-paradigm | na`.
- ADR-0004 (Squidiff adoption) explicitly references this ADR as the precedent for PASS-DECOUPLE as a first-class verdict.

## Evidence

- `skills/custom/causal-ablation-cascade-sim/references/protocol-and-decouple.md` §2 — scoring rubric
- `reports/etapa1-mesendodermo-conclusion.html`, `etapa2-im-conclusion.html`, `cierre-cascada-completa.html` — applied tripartite
- `reports/retrospective-sesion-cascada.html` §4.4 — Logic-LM framework gap flagged
- `skills/custom/squidiff-in-silico-gate/references/gate-criteria.md` Section 5 (verdict states) — PASS-DECOUPLE inherits this paradigm
