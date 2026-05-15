# Architecture Decision Records (ADRs)

This directory holds Architecture Decision Records for the `witt-organogenesis` project — short, dated, immutable notes capturing **why** a non-obvious architectural choice was made.

ADRs are not project documentation in the usual sense. They are forensic records: when a future collaborator (or future-you) asks "why did we do X this way?", an ADR is where the answer lives. The current state of the repo lives in code and live docs; the *why* of past choices lives here.

## When to write an ADR

Write one when **all** of the following are true:

1. The decision is non-obvious — there were defensible alternatives.
2. The decision is hard to reverse — it shapes downstream work.
3. Future collaborators will need the reasoning to evaluate or revise it.

Examples that warrant an ADR:
- Choosing one orchestration pattern over another for a substrate-instrumented agent.
- Recalibrating a substrate validation threshold because of new evidence.
- Selecting a Tier 2 reasoning framework as the default for a niche.
- Choosing one Tool Universe layer (skill / MCP tool / SDK) over another for a specific workflow.

Examples that do NOT warrant an ADR:
- Renaming a file (use git history).
- Adding a new collaborator (use access logs / contact docs).
- Updating a dependency to a newer compatible version.

## How to add one

1. Copy the template below into a new file: `NNNN-short-slug.md` where `NNNN` is the next zero-padded sequence number (`0001`, `0002`, …).
2. Fill the sections.
3. Set `Status: proposed` initially. Update to `accepted`, `rejected`, `superseded by NNNN`, or `deprecated` as the decision evolves. Never delete an ADR — supersede it.
4. Commit. ADRs are part of the repo's history.

## Template

```markdown
# NNNN — <short title>

- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | rejected | superseded by NNNN | deprecated
- **Decided by:** <name(s)>
- **Affects:** <scope: which niches, which agents, which phase>

## Context

What is the situation that requires a decision? What constraints, evidence,
or prior decisions frame it?

## Decision

What did we decide? State it as a single declarative paragraph.

## Alternatives considered

What other options were on the table? Why were they not chosen?

## Consequences

What downstream effects does this decision have? What does it make easier?
Harder? What is now committed that wasn't before?

## Evidence

Links to the stress-test brief, PROJECT_SCOPE sections, substrate test results,
or external references that informed the decision.
```

## Existing ADRs

| ADR | Date | Title | Status |
|-----|------|-------|--------|
| [0001](0001-cascade-protocol-4-scenarios.md) | 2026-05-12 (retroactive) | Cascade protocol uses 4 scenarios per stage (Mode A×B × hipo×KO) | Accepted |
| [0002](0002-version-preservation-rule.md) | 2026-05-12 (retroactive) | Version preservation: never modify prior session outputs | Accepted |
| [0003](0003-decouple-paradigm-as-purity-test.md) | 2026-05-12 (retroactive) | Decouple paradigm: PASA / PARCIAL / FALLA tripartite | Accepted |
| [0004](0004-squidiff-as-transcriptomic-gate.md) | 2026-05-13 (patched 2026-05-14) | Adopt Squidiff as transcriptomic hypothesis gate | Accepted |
| [0005](0005-test-claim-language-discipline.md) | 2026-05-14 | Test claim language: "satisfied" vs "case capture" vs "infrastructure populated" | Proposed |
| [0006](0006-catalog-agent-invocation-discipline.md) | 2026-05-14 | Catalog agent invocation discipline + decision matrix + §11 preflight | Proposed |
| [0007](0007-html-report-mandatory-at-conclusion.md) | 2026-05-14 | HTML report mandatory at conclusion + 4 TYPES + simulation-backed-viz hard rule + visual-offer reflex | Accepted |

---

*Format adapted from Michael Nygard's "Documenting Architecture Decisions" (2011), tailored to the substrate-validation discipline of the Witt × Organogenesis project.*
