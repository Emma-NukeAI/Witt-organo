# ADR-0024 — Explicit admissibility predicate H(c) + Bayes-purity verified_tier_weight + EVPI placeholder (R2)

- **Status:** Accepted (Emmanuel, 2026-06-18) — plan approved this session; R2 built + verified offline + composite-audited at close.
- **Relates:** ADR-0023 (R1 — the loop), ADR-0019/0020/0021 (RAG backend / hosted GraphRAG / raw store), ADR-0014 (outcome vocabulary + ECE), ADR-0005 (test-claim language). CLAUDE.md §7 (anti-fabrication; `verify_output` is the deterministic gate), §5.
- **Affects:** `analysis/scripts/lib/verify_output.py`, `rag_index/graphrag/ingest.py`; Test 4 (calibration), biological gates Induction/Specificity; Pillars 1 (DI composition) + 3 (substrate election). Phase I. Additive — no agent design changed; code-only (no DI mutation; re-ingest stays human-gated).

## Context

The concept-bridge analysis surfaced two §3.1 (low-risk, formally-closed) complements that MITAD_A had only *implicitly*:
- **#1 — the hard/soft admissibility theorem.** `verify_output.verify_identifiers()` already set `ok=False` on an unresolved ENSDARG (the deterministic gate), but there was no explicit predicate `H(c)∈{0,1}` and no statement of the theorem it embodies: *no soft score can rescue an inadmissible claim* (a graded score `g(Q(c))` cannot flip `H` from 0→1).
- **#5 — the Bayes-purity invariant.** Calibration consumes records as label-weight; ledger purity `= s·p / (s·p + f·(1−p))` contracts to 1 **only** on the deterministic subclass where the false-accept rate `f → 0`. Nothing distinguished verifier-confirmed (RAW, raw §7.9 cache on disk) from merely-DERIVED (resolved but raw response not retained) when assigning weight.

MITAD_A is in continuous improvement, so the mechanism must be **additive** (new hard rule composes in; new ingested entity gets weighted) and human-gated.

## Decision

Three reuse-first, additive additions — **read-and-report / code-only, zero DI mutation**:

1. **Explicit admissibility predicate** `admissible(text_or_obj, store, extra_predicates) -> (bool, reasons)` in `verify_output.py`, plus a `VerificationReport.admissible` property. `H` is a **conjunction of hard invariants, EXTENSIBLE by design** (the additive principle: a new hard rule = one more predicate, no rewrite). v1 base invariant: every external ENSDARG resolves (`verify_identifiers().ok`). The theorem is made explicit in code — admissibility is computed from hard predicates **only**, never from a confidence/quality value — so soft scoring is defined only on `H^{-1}(1)`.

2. **Bayes-purity `verified_tier_weight`** — `tier_weight(tier)` (RAW=1.0 / DERIVED=0.7 / NOT_FOUND|unknown=0.0) and `tier_weight_for_record(rec)`, **derived from the existing `verification_tier`** (no manifest-schema change). `ingest.py` stamps it on the `:Entity` node **and** the `:Document-[:MENTIONS]->:Entity` edge at the **human-gated** ingest. Only RAW-confirmed mentions may later carry full calibration label-weight — the deterministic verifier keeps `f → 0`.

3. **`info_priority_order()` — an honest EVPI PLACEHOLDER.** A transparent proxy for "which admissible candidate to resolve next" (NOT_FOUND-but-needed → high info, before already-verified; then by prior), tagged `placeholder: True`. A calibrated EVPI (`E_θ[max_a U] − max_a E_θ[U]`) needs a decision-utility model the substrate does not yet formalize — **deferred**, never presented as a calibrated value.

## Alternatives considered

- **Add `verified_tier_weight` to the `corpus_manifest.json` schema.** Rejected — derive it from the existing `verification_tier` at ingest; less mutation, same result.
- **Wire `compute_ece` to down-weight non-RAW records now.** **Deferred** — with only n≈5 resolved records (ADR-0005 "case capture"), down-weighting the non-RAW ones would leave the nascent calibration signal nearly empty. The infrastructure (`tier_weight` + the graph stamping + `admissible`) is ready for `compute_ece` to consume; revisit when RAW-tier resolved records accumulate. Recorded as a gap, not done.
- **Implement a real EVPI now.** Rejected (prueba pequeño) — no decision-utility model exists; a fake EVPI would over-claim. Shipped as a clearly-labeled placeholder.

## Consequences

- **The admissibility theorem is enforceable + extensible** — a soft score can never rescue an inadmissible claim, and a new hard rule is a one-line predicate addition (additive).
- **The graph layer now carries label-weight** (`verified_tier_weight` on Entity + MENTIONS), so retrieval/calibration over graph facts can down-weight unverified mentions; the `f → 0` deterministic subclass is exactly where the purity contraction to 1 holds.
- **Code-only, no DI mutation** — `ingest.py` changes take effect on the next **human-gated** ingest (not run here). Reads are free; mutations stay gated (§7). Additive, backwards-compatible.
- **Honest limits (gap_flags):** `compute_ece` per-record tier-weighting deferred; `info_priority_order` is a placeholder not a calibrated EVPI; **`DERIVED=0.7` is a provisional placeholder** — only `RAW=1.0` / `NOT_FOUND=0.0` are rigorously derived endpoints (purity → 1 as f → 0); 0.7 must be calibrated from an estimated DERIVED-tier false-accept rate before `compute_ece` down-weights real records by it. The incidental `compute_ece.py` edit in this change-set is a **datetime-deprecation cleanup only** (NOT tier-weighting wiring).

## Verification

Offline (NO-SPEND): `verify_output` smoke — the wt1a fabrication → `admissible=False` (reason: unresolved ENSDARG); the correct ID → `admissible=True`; `tier_weight` RAW/DERIVED/NOT_FOUND = 1.0/0.7/0.0; `info_priority_order` puts NOT_FOUND (`clcnkb`) before verified (`wt1a`). `ingest.py` + `verify_output.py` compile clean (`-W error::DeprecationWarning`). `ingest.py` NOT run (re-ingest is a human-gated DI mutation). **Closing composite-auditor (3 adversarial lenses, this session): 3/3 APPROVE (minor).** No-mutation confirmed (`verified_identifiers.json` + `corpus_manifest.json` zero git changes; `ingest.py` not run); "soft cannot rescue hard" confirmed at code level (admissible() has no confidence parameter). **7 minor fixes applied:** `extra_predicates` hard-invariant contract note; renamed the partial `VerificationReport.admissible` property → `identifier_admissible`; `DERIVED=0.7` documented as provisional + gap-flagged; dropped the dead `None` key and added `UNVERIFIED` to `TIER_WEIGHT`; `tier_weight_for_record` now delegates to `tier_weight` (no path divergence); `info_priority_order` clamps `prior` to [0,1]; noted the incidental `compute_ece.py` datetime cleanup.

## Substrate instrumentation (§5 / §11)

- **Claim record:** `substrate_calibration/records/claim_20260618_140000_r2-admissibility-purity.json` (carries a `replay` block).
- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (the admissibility gate is a deterministic predicate; the smoke tests are re-runnable proofs). Self-report per §5.
- **agents_invoked:** `composite-auditor` — invoked (Mode 1, ≥3 adversarial, closing audit); `causal-pruner` — not-applicable.
