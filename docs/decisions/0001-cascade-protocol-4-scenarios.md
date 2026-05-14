# ADR 0001 — Cascade protocol uses 4 scenarios per stage (Mode A×B × hipo×KO)

- **Date:** 2026-05-12 (decision); 2026-05-14 (ADR written during unified recalibration)
- **Status:** Accepted retroactively
- **Decided by:** agent in cascade session, ratified by user
- **Affects:** `skills/custom/causal-ablation-cascade-sim/`, all cascade outputs

## Context

When designing the causal ablation cascade simulation for pronephros development, a protocol was needed for how many perturbation scenarios to evaluate per developmental stage. The session was operating under the user's explicit directive *"vayamos con la ruta que tenga más posibilidad de éxito sin pensar en los costos"* — maximize causal inference quality over minimum cost.

The choice was between:
- A small protocol (1-2 scenarios per stage) consistent with "prueba pequeño"
- A large protocol (6-8 scenarios with gradient doses + multiple rescue constructs)
- A medium balanced protocol (4 scenarios crossing two axes)

## Decision

Each stage of the cascade is evaluated with **exactly 4 scenarios**, crossing two axes:

- **Mode axis (temporal):** `A` = stage-specific with washout (perturbation ON during the stage's window, then released — analog: photo-activated blebbistatin pulse + photo-released). `B` = persistent (perturbation starts at stage's window onset and continues — analog: maternal-zygotic mutant).
- **Dose axis (intensity):** `hipo` = ~50% activity reduction (sub-lethal, modal phenotype detectable). `KO` = ~95% activity reduction (near-complete loss, strong but variable, sometimes catastrophic).

The four scenario codes per stage `{N}`:
- `{N}A-hipo` — Mode A, hipo dose. Highest causal value (cleanest stage-specific signal).
- `{N}A-KO` — Mode A, KO dose. Strong signal but more variance.
- `{N}B-hipo` — Mode B, hipo dose. Reference only — confounded with cascade.
- `{N}B-KO` — Mode B, KO dose. Control positive of extreme OR catastrophic confounder.

This is encoded in `skills/custom/causal-ablation-cascade-sim/SKILL.md` (the 4-scenario protocol section) and `references/protocol-and-decouple.md` §1.

## Alternatives considered

- **2 scenarios (A-hipo + B-control only):** rejected — no contrast between stage-specific and cascade effects.
- **Wet-lab style 4 scenarios (A-hipo / B-control / C-rescue / D-orthogonal):** retrospectively proposed by audit. Recognized as a defensible *forward-looking* protocol for wet-lab translation, but does not describe what this in-silico cascade session decided. May become ADR-0005 if adopted for Phase II.
- **6+ scenarios (gradient dose × multiple rescue × time-lapse):** rejected for Phase I per founder principle "prueba pequeño antes de armar bien." May be considered for Phase II.
- **Continuous time-lapse rather than discrete scenarios:** rejected — read-out infrastructure not yet available; harder to compare across stages.

## Consequences

- Cascade simulation skill (`causal-ablation-cascade-sim/SKILL.md`) bakes in the Mode A × B × hipo × KO contract.
- Cross-stage comparison is straightforward because every stage has the same 4-cell matrix.
- `squidiff-in-silico-gate` (ADR-0004) can be invoked per scenario, producing 4 transcriptomic verdicts per stage that aggregate into the stage's overall finding via Mode 3 cross-verdict with Morpheus.
- The Mode A vs B contrast at same dose distinguishes stage-specific causality from cascade effects — mitigates Gate 4 (parsimonia) without eliminating it.
- Phase II decision: revisit whether 4 is still right when wet-lab read-out infrastructure expands; consider the audit-proposed A/B/C/D wet-lab translation as evolution path.

## Evidence

- `skills/custom/causal-ablation-cascade-sim/SKILL.md` lines 51-61 — canonical 4-scenario codes
- `skills/custom/causal-ablation-cascade-sim/references/protocol-and-decouple.md` §1 — design rationale
- `reports/cierre-cascada-completa.html` — three-stage execution producing 12 scenarios + control
- `reports/retrospective-sesion-cascada.html` §4.2 — flagged decision as worth preserving
