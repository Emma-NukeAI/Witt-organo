# 0010 — Rename the bundle to GWT v1.1

- **Date:** 2026-06-10
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** the umbrella bundle label only (CLAUDE.md footer); not individual component SemVers

## Context

The repo's umbrella "bundle" label was at **v2.5** (CLAUDE.md footer), while `PROJECT_SCOPE.md` was
v1.2 and the architect skill was 2.2.0 — three numbering axes that did not align. The GWT v1.1
upgrade is the moment to reset the umbrella label to a single product-era version the team uses.

## Decision

Rename the umbrella bundle from **v2.5** to **GWT v1.1**. This is a label reset, chosen explicitly
by Emmanuel over the alternatives. The prior v2.x history is **preserved** (not deleted): the
CLAUDE.md footer records the supersession mapping `bundle v2.5 → GWT v1.1`, and the v2.x changelog
chain + ADR-0001..0007 remain valid history. **Individual component SemVers keep their own numbering
and are NOT reset:** `organogenesis-agent-architect` (2.2.0 → 2.3.0 when its content lands),
`PROJECT_SCOPE` (1.2 → 1.3), `substrate-evidence-guide` (1.4 → 1.5), `agent-invocation-matrix`
(1.1 → 1.2). Only the umbrella label changes.

## Alternatives considered

- **"v1.1 product = bundle v2.6"** (keep monotonic v2.x, map product label on top). Rejected by
  Emmanuel in favor of a clean reset.
- **Two explicit axes forever (Witt v1.x / Bundle v2.x).** Rejected: more bookkeeping than wanted.
- **Renaming with history deletion.** Never on the table — ADRs and changelogs are immutable history
  (ADR-0002 spirit).

## Consequences

- Easier: one umbrella version the team refers to ("GWT v1.1").
- Care required: anything that parsed "v2.5" must read "GWT v1.1"; the footer carries the mapping so
  the v2.x history is not lost.
- Note: record the expansion of the "GWT" acronym in the CLAUDE.md footer when confirmed.

## Evidence

GWT v1.1 plan §12 (version bookkeeping) + the user's explicit choice "renombrar el bundle a v1.1";
CLAUDE.md footer (current v2.5 line); ADR-0002 (version preservation).
