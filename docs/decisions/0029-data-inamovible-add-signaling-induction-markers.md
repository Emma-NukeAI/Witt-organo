# ADR-0029 — DATA INAMOVIBLE: add 5 pronephros upstream-signaling / induction markers (human-gated ADD)

- **Status:** Accepted — **human gate AUTHORIZED by Emmanuel, 2026-06-23** ("Autorizo los 5 tal cual"), after the exact spec was stated before any write (founder directive 2026-06-13; CLAUDE.md §7).
- **Relates:** ADR-0008/0010 (store is read-only + human-gated mutable, single writer), ADR-0002 (versioning: snapshot before re-build), ADR-0024 (RAW/DERIVED tiers), ADR-0028 (the E2E test that revealed the gap). Adjustment #2 of the post-E2E plan.
- **Affects:** `analysis/outputs/verified_identifiers.json` (DATA INAMOVIBLE v1). This is a MUTATION (ADD-only), not read-and-report.

## Context

The 2026-06-22 end-to-end test ("which signal regulates the pronephros TF set?") found that the genes most central to the INDUCTION half of the question were **not in the store**: `osr1` (the earliest intermediate-mesoderm marker — the composite-auditor explicitly flagged it `NOT_FOUND`), the candidate inducers `wnt8a`/`fgf8a`, and the retinoic-acid-axis enzymes `aldh1a2`/`cyp26a1`. Anchoring them lets future induction/patterning questions resolve through the source-of-truth instead of from memory.

## Decision

**ADD 5 records** to the DATA INAMOVIBLE, all **RAW** tier (raw Ensembl REST response retained per §7.9). IDs resolved **LIVE from Ensembl REST** (`xrefs/symbol` + `lookup/id`, `danio_rerio`, GRCz11) on 2026-06-23 — never from memory:

| symbol | ENSDARG | role |
|---|---|---|
| `osr1` | `ENSDARG00000014091` | earliest intermediate-mesoderm induction marker |
| `wnt8a` | `ENSDARG00000052910` | Wnt inducer candidate (posteriorizing Wnt) |
| `fgf8a` | `ENSDARG00000003399` | FGF inducer candidate |
| `aldh1a2` | `ENSDARG00000053493` | retinoic-acid synthesis (proximodistal patterning) |
| `cyp26a1` | `ENSDARG00000033999` | retinoic-acid degradation |

**Mechanism (single-writer + gate discipline):**
1. NEW curated source `analysis/outputs/signaling_markers_curated.json` (mirrors `ocular_markers_curated.json`; carries ensdarg + raw_cache_ref + verified_on).
2. `build_verified_store.py` — added a merge block for the signaling curated set (RAW tier) + bumped `STORE_VERSION` `2026-06-11.1` → `2026-06-23.1` + recorded the new source artifacts.
3. SNAPSHOT the prior store → `analysis/outputs/verified_identifiers.v2026-06-11.1.json` (ADR-0002).
4. RAN the builder (NO-SPEND; re-expresses already-verified/cached data).

## Consequences

- **Store: 46 → 51 records** (26 RAW / 23 DERIVED / 2 NOT_FOUND). `store_version` 2026-06-23.1.
- **SHA256 changed intentionally:** `f070b40c…707` → `5f4d0bf9…d580`. This is the authorized mutation — the read-and-report invariant of prior sessions does NOT apply to this change (it applies to everything else).
- ADD-only: **no existing record edited or deleted** (wt1a, pax2a, … unchanged; all still resolve).
- **Reversible** via the v2026-06-11.1 snapshot.
- The ADR-0027 durable smoke test's store invariant was refactored from a frozen SHA literal to a **dynamic capture-and-compare** ("this run mutates nothing"), so an authorized store change no longer false-fails it (now 22/22).

## Verification

- `resolve_id`: all 5 new symbols resolve to their verified ENSDARG, **RAW** tier; `wt1a`/`pax2a` still resolve (no breakage).
- `verify_output.admissible`: a correct `osr1` binding → admissible; a fabricated ENSDARG → still rejected.
- `replay_and_regress` over records + regression_cases under the NEW store → **NO_REGRESSION** (the wt1a guards pass).
- All 5 tool selftests PASS; ADR-0027 durable smoke 22/22.
- Raw verification cached: `mcp_cache/raw_ensembl_signaling-genes_20260623.json` (§7.9).

## Substrate instrumentation (§5)

- **Claim record:** `substrate_calibration/records/claim_20260623_120000_adr0029-di-signaling-markers.json`.
- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (live ID resolution + deterministic store round-trip). Self-report per §5.
- **agents_invoked:** `domain-knowledge-curator` — invoked (store curation under the gate); `causal-pruner` — not-applicable; `composite-auditor` — not-applicable (the upstream E2E audit already motivated this; the add itself is a deterministic, verified curation, human-gated).
