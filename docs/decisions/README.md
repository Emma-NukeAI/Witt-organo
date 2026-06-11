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
| [0008](0008-ceded-slot-hypothesis-generator.md) | 2026-06-10 | Ceded Phase-I slot: +hypothesis-generator, −investor-relations-drafter; keep ip-patent-watcher | Accepted |
| [0009](0009-retrospector-and-ril-subsystem.md) | 2026-06-10 | retrospector agent + Reasoning-Improvement Loop as a subsystem (cedes risk-register-agent) | Accepted |
| [0010](0010-rename-bundle-to-gwt-v1.1.md) | 2026-06-10 | Rename the umbrella bundle v2.5 → GWT v1.1 (label reset; v2.x history preserved) | Accepted |
| [0011](0011-eps-must-be-measured.md) | 2026-06-11 | EPS must be measured (noise-probe before any improvement claim) | Accepted |
| [0012](0012-reactive-calibration-rolling-k6.md) | 2026-06-11 | Reactive calibration (rolling K=6 + auto-cap) supersedes quarterly-only | Accepted |
| [0013](0013-governance-proposal-meta-loop.md) | 2026-06-11 | Governance-proposal meta-loop: the agent proposes, the human applies (Sakana safety lesson) | Accepted |
| [0014](0014-outcome-vocab-and-per-stream-auto-cap.md) | 2026-06-11 | Outcome vocabulary (positive/negative/unfalsifiable) + per-stream auto-cap regime | Accepted |
| [0015](0015-rag-index-structure-backend-open.md) | 2026-06-11 | RAG index structure-first (13 niches + 9 DBs); backend OPEN (FAISS/Neo4j/graphify/hybrid via spike) | Accepted (structure) |
| [0016](0016-ril-program-charter.md) | 2026-06-11 | RIL_PROGRAM.md as the canonical Reasoning-Improvement-Loop charter | Accepted |
| [0017](0017-corpus-classifier-agent.md) | 2026-06-11 | Corpus-classifier as an operational mode of domain-knowledge-curator (categorize + audit, human-gated) | Accepted |
| [0018](0018-niche-taxonomy-keep-as-is-recommend-always.md) | 2026-06-11 | DATA INAMOVIBLE niche taxonomy keep-as-is + always-recommend-changes + metabolic discriminator | Accepted |
| [0019](0019-rag-backend-v1-sparse-flat-versioned.md) | 2026-06-11 | RAG backend v1: flat versioned human-gated sparse retriever (dense/hybrid gated) | Accepted |

---

*Format adapted from Michael Nygard's "Documenting Architecture Decisions" (2011), tailored to the substrate-validation discipline of the Witt × Organogenesis project.*
