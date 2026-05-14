# ADR 0002 — Version preservation: never modify prior session outputs when adding new content

- **Date:** 2026-05-12 (decision); 2026-05-14 (ADR written)
- **Status:** Accepted retroactively
- **Decided by:** user-driven during cascade session, codified in agent practice
- **Affects:** all session artifact production (HTML reports, viz files, simulation outputs)

## Context

During the cascade session, the user explicitly directed that prior HTML reports (etapa1, etapa2, comparison viz v1) should remain untouched when stage 3 was added. Adding Etapa 3 led to *new* files (`-v2.html`), not modification of existing files. The user's directive was clear: *"quiero que las visualizaciones sean nuevos archivos para no tocar los pasados y ver las diferencias."*

## Decision

When adding a new stage, scenario, candidate, or evolution to existing project artifacts, the agent produces a **new versioned file**. Prior versions are preserved untouched. Cross-references between versions are maintained.

Format: `<filename-stem>-v<N>.<ext>` for the new version. Original lives at `<filename-stem>.<ext>` and is treated as v1 implicitly.

## Alternatives considered

- **In-place edits with git history:** rejected — git history is forensic but not browse-friendly. Stakeholders looking at v1 see v2 unless they `git checkout`.
- **Append-only sections within the same file:** rejected — does not work for HTML reports where the structure is the artifact (a 3-panel viz vs 4-panel viz are different files, not different sections).
- **Single rolling "latest" file + numbered archives:** rejected — `latest` ambiguity confuses cross-references and breaks the comparison-by-version reading pattern.

## Consequences

- Disk usage grows with versions; acceptable cost.
- The user can always view "what the cascade looked like with only 2 stages" by opening v1.
- `squidiff-in-silico-gate` outputs to `SIMULATION_OUTPUTS_DB/<hypothesis_id>/` follow this rule: never overwrite, always version.
- The skill registers this rule in its hard rules (`SKILL.md` §10): "Adding to an existing cascade: never modify prior reports/* or viz files. Create new etapaN-conclusion.html, regenerate cierre-*.html, create *-v2.html for viz. Preserves comparability."
- ADRs about removing or merging versions become a future decision when version count exceeds reasonable browsing limits.

## Evidence

- `reports/visualizacion-cascada-pronefro.html` (v1, 9 scenarios) vs `reports/visualizacion-cascada-pronefro-v2.html` (v2, 13 scenarios) — direct evidence
- `reports/visualizacion-comparacion-pronefro.html` (v1) vs `reports/visualizacion-comparacion-pronefro-v2.html` (v2) — same pattern
- `skills/custom/causal-ablation-cascade-sim/SKILL.md` §10 hard rules — rule codified
- `reports/retrospective-sesion-cascada.html` §4.2 — flagged as worth preserving
