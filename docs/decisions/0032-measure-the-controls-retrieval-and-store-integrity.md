# ADR-0032 — Measure the controls: retrieval eval + store-integrity scan as standing gates

- **Status:** Accepted — from the external review (Fable 5, 2026-07-05, recs 1 & 5).
- **Relates:** ADR-0020/0022 (retrieval + loop), ADR-0008/0010 (store is human-gated), CLAUDE.md §10 (preflight).
- **Affects:** adds two read-and-report tools + a language rule. No DI mutation.

## Context

The external auditor's highest-value / lowest-cost recommendation: **"measure the controls, don't just run
them."** Two controls were unmeasured:
- **Retrieval quality** — a knowledge-graph + vector + sparse store "lives or dies on recall/precision,"
  yet there was no recall metric. A silent retrieval miss makes the system re-learn what it already knows,
  or answer from partial context with high confidence. Load-bearing, unmeasured.
- **Error persistence in the store** — the human gate protects *entry*, not *persistence*. There was no way
  to find an approved-but-wrong fact after the fact (the 2026-06 wt1a ENSDARG-collision class).

## Decision

1. **`substrate_calibration/tools/retrieval_eval.py`** — known-item recall@k + MRR over the DATA INAMOVIBLE
   (probes derive from the corpus manifest; offline sparse + live neo4j). First run (2026-07-05): recall@1 =
   recall@5 = MRR = 1.0 on 3 probes — reported honestly as a **SCAFFOLD** (small corpus, indicative not
   robust). It becomes statistically meaningful as the corpus grows.
2. **`substrate_calibration/tools/store_integrity_scan.py`** — error-in-store detection: duplicate symbols,
   ENSDARG collisions (wt1a-class), malformed IDs, incomplete provenance, staleness; optional live
   re-resolve vs Ensembl. Read-and-report; emits `pending_review` proposals, **never auto-fixes** (§7).
   First run (2026-07-05): 51 records CLEAN. Intended as a **periodic** scan.
3. **Language rule:** until a control has a measured effectiveness number, it is described as **scaffolding**,
   not as validation. "Calibration" with n=10 labeled outcomes is "scaffolding populated," not "satisfied"
   (already enforced in `compute_ece`, ADR-0030). Same discipline now applies to retrieval and the audit gate.

## Consequences

- Two new standing controls; both exit non-zero on failure so they are usable as periodic gates.
- Honest status: retrieval recall is a 3-probe scaffold; do not cite it as robust until the corpus grows.
- Next: add these to the periodic run set (alongside the smoke suite); grow the retrieval probe set and
  the calibration outcome count before upgrading either from "scaffolding" to "measured control."
