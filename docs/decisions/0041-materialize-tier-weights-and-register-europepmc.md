# ADR-0041 — Re-ingest to materialize tier weights + register EuropePMC as a source (human-gated)

- **Status:** Accepted — **human gate AUTHORIZED by Emmanuel, 2026-07-20** ("Sí — ambos (#1 + #3)"), after the exact write-spec (node/edge deltas) was stated before any write (founder directive 2026-06-13; CLAUDE.md §7).
- **Relates:** ADR-0020 (hosted Neo4j GraphRAG), ADR-0024 (RAW/DERIVED Bayes-purity `tier_weight`), ADR-0039 (ingest stamps `verified_tier_weight` on Entity + MENTIONS), ADR-0022/0026 (answer-pipeline Path B via Europe PMC — the source of CORPUS-2026-0003), ADR-0029 (analogous human-gated DI add). Motivated by the 2026-07-20 GraphRAG composition review.
- **Affects:** the hosted Neo4j graph (embedding + index layers) + `rag_index/databases.json` + `rag_index/niche_database_crosswalk.json`. This is a **MUTATION (ADD/UPDATE-only, MERGE — never deletes)**, not read-and-report.

## Context

The 2026-07-20 composition review (measured live: 95 nodes / 141 edges) surfaced two real defects:

1. **Drift graph↔code.** The graph's last re-ingest was **2026-06-13** (`Meta.refreshed_at`), predating ADR-0024/0039. All **44 Entities and 88 MENTIONS carried `verified_tier_weight = None`** — the Bayes-purity tier weight existed in `ingest.py` but was not materialized in the live data, so no downstream calibration could weight a mention by its verification tier.
2. **Scaffold leak.** `CORPUS-2026-0003` (Gerlach & Wingert 2014, via Path B) declares `source_db: "EuropePMC"`, but EuropePMC was **not** in `databases.json`. `ingest.py` only creates `FROM_DB` when `source_db` matches a registered `Database`, so the paper had **no `FROM_DB` edge** — its provenance was queryable only from manifest metadata, not from the graph. As Path B (Europe PMC) recurs, every new paper would inherit the same hole.

## Decision

**(a) Register EuropePMC** as an authoritative literature source in `databases.json` — `feeds_niches: ["RN11"]` (curated literature claims), provenance `curated`; mirrored in the crosswalk (declared RN11; proposed RN1/RN3/RN10). **(b) Run the canonical single writer** `rag_index/graphrag/ingest.py` (gated re-ingest, `uv run --locked`, `EMBED_MODEL=openai` — same model, **no embedding-model change → no halt**). One idempotent run materializes the tier weights (fix #1) and creates the EuropePMC node + edges (fix #3).

**Not #2 (corpus under-population):** explicitly out of scope — it populates naturally with use (founder direction 2026-07-20).

## Consequences

- **Graph: 95 → 97 nodes, 141 → 144 edges.** `Database` 10 → **11** (`DB::EuropePMC`); `Document` 27 → **28** (`db:EuropePMC` catalog doc); `FROM_DB` 12 → **14** (`db:EuropePMC`→DB + `CORPUS-2026-0003`→DB); `FEEDS` 25 → **26** (EuropePMC→RN11). `IN_NICHE` 16, `MENTIONS` 88, `Entity` 44, `Niche` 13 unchanged.
- **Tier weights materialized:** 44 Entities (21×1.0 RAW / 23×0.7 DERIVED) and **88/88 MENTIONS** (43×1.0 / 45×0.7) now carry `verified_tier_weight`. `Meta.refreshed_at` 2026-06-13 → 2026-07-20; `doc_count` 28.
- **ADD/UPDATE-only:** no node/edge deleted; all embeddings re-computed with the SAME model (openai/1536) so the `doc_embeddings` index (ONLINE) is unchanged in shape. Sparse `documents.jsonl` rebuilt in sync (28 docs).
- **Doc ripple:** references to "10 databases / 9 authoritative sources" become **11 / 10** (databases.json, crosswalk purpose updated; README + CLAUDE.md §12 to sync on next docs pass). Composition viz regenerated to **v2** (v1 preserved as the pre-fix snapshot).
- **Reversible** only via a *gated prune proposal* (removing EuropePMC), never automatic (ADR-0022 discipline).

## Verification (read-only, post-ingest, live)

- `node_counts` {Document 28, Niche 13, Database 11, Entity 44, Meta 1}; `rel_counts` {IN_NICHE 16, FROM_DB 14, FEEDS 26, MENTIONS 88}.
- `entities_by_weight` {1.0: 21, 0.7: 23}; MENTIONS with weight **88/88** {1.0: 43, 0.7: 45}.
- `DB::EuropePMC` present, `FEEDS → RN11`; `CORPUS-2026-0003 -[:FROM_DB]-> EuropePMC`.
- Vector index `doc_embeddings` **ONLINE, 1536-dim**; `Meta.refreshed_at = 2026-07-20`.

## Substrate instrumentation (§5)

- **framework_applied:** Chain-of-Verification (CoVe) — per `reasoning-frameworks-catalog.md §8`: *"Generate a draft answer, then generate verification questions about that answer, answer those questions independently, and revise the draft based on the verification results."* The predicted write-deltas were verified against the live graph after the write. Self-report per §5.
- **agents_invoked:** `composite-auditor` — skipped-ad-hoc (a human-gated, deterministically-verified infrastructure mutation, not a substrate-evidence biology claim requiring an audit gate); `causal-pruner` — not-applicable (no ranked candidates / sufficiency hypotheses).
