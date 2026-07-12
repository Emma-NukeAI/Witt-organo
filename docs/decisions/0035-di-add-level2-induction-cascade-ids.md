# 0035 — DATA INAMOVIBLE ADD: +23 pronephros-induction cascade IDs from the Level-2 Tool Universe fallback

- **Date:** 2026-07-11
- **Status:** accepted
- **Decided by:** Emmanuel (human gate); prepared by the held-out Level-2 fallback + independent re-verification
- **Affects:** DATA INAMOVIBLE verified-identifier store (v1); niches N3/N4 (signaling / induction); Test 3 corpus growth

## Context

The A1 held-out baseline (2026-07-11) showed the substrate is under-confident and the DATA INAMOVIBLE is thin
(95 graph nodes / ~3 corpus records) for broad zebrafish intent questions. The Tool Universe fallback study
found that **Level-2** (an agent that EXECUTES structured Tool Universe tools) — not Level-1 (literature) — is
the lever: on 6 intent questions confidence rose ~0.14→0.71 and judged quality 0.60→0.84. In doing so the
Level-2 agents surfaced **24 gene symbols absent from the 51-record store**, each with a live-fetched ENSDARG —
exactly the BMP/Nodal/RA/Wnt/FGF/Hox cascade the project's induction questions are weakest on. This closes the
ADR-0022 loop: "not in the store" is a prompt to learn, gated on approval.

## Decision

**ADD 23 of those identifiers to the verified store (v1), tier RAW, human-gated.** Before adding, every ENSDARG
was **independently re-verified** (NOT trusting the agent) against Ensembl REST `/lookup/symbol/danio_rerio`:
**23/23 MATCH, 0 mismatch, 0 not-found**; the raw responses were cached at
`mcp_cache/raw_ensembl_l2-candidates_20260711.json` (§7.9). The 24th candidate (`clcnkb`) carried no ENSDARG and
stays a positive NOT_FOUND. Applied via the single writer `build_verified_store.py` after folding the markers
into `signaling_markers_curated.json`; `store_version 2026-06-23.1 → 2026-07-11.1`; the prior store was
snapshotted to `verified_identifiers.v2026-06-23.1.json` (ADR-0002). Store **51 → 74 records**.

Genes added: BMP `bmp2b, bmp4, bmp7a, chrd, smad2, smad4a, smad5`; Nodal `ndr1, ndr2, lft1, lft2, tdgf1`; RA
`raraa, rarga, rxrba, cyp26b1`; Wnt `wnt2ba`; FGF `fgf24`; Shh `shha`; Hox `hoxb1b, hoxb8a`; paralogs `pax2b`
(pax2a co-ortholog), `sim1b` (sim1a ohnolog).

## Alternatives considered

- **Trust the Level-2 agents' asserted ENSDARG directly** — REJECTED: violates §7 anti-fabrication. Re-verified
  each against Ensembl with raw caching; the check happened to pass 23/23, but the discipline is non-negotiable.
- **Keep as `pending_review` only** (proposal, no store change) — the default until the human gate approves. The
  proposal (`analysis/outputs/pending_review/l2_cascade_candidates_20260711.json`) was written first; this ADR
  records the subsequent approval + application.
- **Add a focused subset (RA/Nodal core only)** — considered; the full 23 were approved since all are
  Ensembl-verified and all are induction-cascade relevant.

## Consequences

- The store now anchors the induction cascade the E2E tests + Level-2 questions repeatedly needed; future Path-A
  retrieval and the anti-fabrication gate cover these genes. Directly attacks the "content-thin" limiter.
- Exposes a gate refinement (deferred): `verify_output.admissible` scores an answer's live-verified-but-not-yet-
  in-store IDs as "unresolved → negative" (the Q08 false negative). Post-add, the 23 now resolve, but the general
  case — an agent fetching a *new* verified ID — should route to re-ingest, not be scored as fabrication.
- Docs that narrate the store count (`CLAUDE.md §12`, `README`, `HANDOFF`) updated 51→74 / version bump; the
  `doc_coherence_check.py` drift gate enforces this.
- New raw cache `mcp_cache/raw_ensembl_l2-candidates_20260711.json` is the §7.9 provenance (gitignored; the store
  records reference it, same as the ADR-0029 signaling cache).

## Evidence

- Level-2 comparison: `reports/2026-07-11_level2-agentic-tooluniverse_comparison.html`; records
  `evaluation/runs/month_0_l2/`.
- Re-verification: `mcp_cache/raw_ensembl_l2-candidates_20260711.json` (23/23 MATCH).
- Writer + curated input: `analysis/scripts/lib/build_verified_store.py`,
  `analysis/outputs/signaling_markers_curated.json`; proposal
  `analysis/outputs/pending_review/l2_cascade_candidates_20260711.json`.
- Prior: ADR-0022 (DI-first / fallback / human-gated re-ingest), ADR-0029 (+5 signaling markers, same pattern).
