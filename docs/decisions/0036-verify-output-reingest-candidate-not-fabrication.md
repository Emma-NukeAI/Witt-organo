# 0036 — verify_output: a live-verified out-of-store ID is a re-ingest candidate, not a fabrication fail

- **Date:** 2026-07-11
- **Status:** accepted
- **Decided by:** Emmanuel (directed the refinement); implemented + self-tested
- **Affects:** the anti-fabrication gate `analysis/scripts/lib/verify_output.py` (safety spine, §7); the held-out runner's deterministic scorer; the ADR-0022 re-ingest loop

## Context

ADR-0035 flagged a false negative: the Level-2 Tool Universe fallback answered Q08 well (judges 3× correct,
confidence 0.82) but its deterministic `observed_outcome` was **negative**, because `verify_output.admissible`
checks every ENSDARG against OUR verified store and the agent had fetched REAL Ensembl IDs (sim1b, pax2b) not
yet in it. The gate conflated two very different things: a **fabricated** ID (exists nowhere) and a **real ID
verified live but not yet ingested**. The first must fail; the second is exactly the ADR-0022 signal ("not in
the store → a prompt to learn, gated on approval"), not a fabrication.

## Decision

Add a **third category** to the gate, `reingest_candidate`, gated on **§7.9 provenance** — not on trust. An
out-of-store ENSDARG counts as a re-ingest candidate ONLY if it literally appears in a §7.9 raw cache file on
disk (`reingest_cache` path(s) passed by the caller): `verify_identifiers(obj, reingest_cache=...)` reads those
raw responses OFFLINE and, for each out-of-store id, routes it to `report.reingest_candidates` (does NOT set
`ok=False`) iff it is present there; otherwise it stays `unresolved` and STILL fails. `admissible()` gains the
same `reingest_cache` param; re-ingest candidates are deliberately NOT a failure reason and are surfaced for
the human-gated re-ingest loop. **Default `reingest_cache=None` reproduces the prior behavior byte-for-byte**
(every out-of-store id is `unresolved` → fail), so the safety spine is unchanged unless a caller opts in with
real provenance.

This keeps the gate deterministic, offline, and non-fabricable: an id passes as a candidate only because it
demonstrably came from a cached authoritative response — a bare assertion (no backing raw, or missing file)
still fails.

## Alternatives considered

- **Make "unresolved" always pass / trust the agent's asserted IDs** — REJECTED: guts the anti-fabrication gate.
- **Let verify_output re-verify live against Ensembl** — REJECTED: breaks the gate's deterministic / NO-SPEND /
  offline contract. Verification-with-caching stays the caller's job (§7.9); the gate only checks the cache.
- **Whitelist via a pending_review proposal file** — REJECTED for now: couples the gate to a directory; the
  raw-cache-presence check is more general and closer to the §7.9 provenance itself.

## Consequences

- The Q08 false negative is fixed at the root: with the raw cache passed, sim1b/pax2b resolve to
  `reingest_candidates` and no longer fail admissibility. (Demonstrated against the 51-record snapshot store.)
  A genuinely-unverified id the agent merely mentioned (e.g. `ENSDARG00000039935`, which the agent itself
  flagged "identity unconfirmed", not in any cache) CORRECTLY still fails — the gate now separates all three
  classes: verified-in-store / live-verified-not-in-store / no-provenance.
- `run_held_out.score_deterministic` accepts `reingest_cache` and surfaces `reingest_candidates`; the API is
  ready for the Level-2-in-runner integration (which will pass the fetch's raw cache).
- Known limit (v1): candidacy checks that the ENSDARG is present in the raw cache, not that the specific
  symbol↔ENSDARG binding matches the cache entry; the human-gated re-ingest (build_verified_store re-resolves)
  is the backstop. Tightening to per-binding cache validation is a future refinement.
- Fixed a **pre-existing** break in `smoke_adr0027_hardening.py` (unrelated to this change): it assumed every
  file in `records/` has a `claim_id`, but `panel_multifamily_20260705.json` (ADR-0031) has none — the smoke
  now filters to claim records. Smoke back to 22/22.

## Evidence

- `analysis/scripts/lib/verify_output.py` (`_live_verified_ids`, `reingest_candidates`, `reingest_cache` on
  `verify_identifiers`/`admissible`) + its `__main__` self-test (fabricated-no-cache FAIL; cache-backed
  admissible; not-in-cache FAIL).
- Q08 demonstration vs `analysis/outputs/verified_identifiers.v2026-06-23.1.json` + raw cache
  `mcp_cache/raw_ensembl_l2-candidates_20260711.json`.
- Prior: ADR-0022 (re-ingest loop), ADR-0024 (admissibility predicate H(c)), ADR-0027 (N1/N2 hardening),
  ADR-0035 (the DI ADD that flagged this refinement).
