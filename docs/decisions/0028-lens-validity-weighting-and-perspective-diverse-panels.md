# ADR-0028 — Lens-validity weighting + perspective-diverse Self-Consistency panels

- **Status:** Accepted (Emmanuel, 2026-06-23) — adjustment #1 from the 2026-06-22 end-to-end pipeline test; the user requested all revealed adjustments be applied in order.
- **Relates:** ADR-0024 (R2 identifier `tier_weight` / Bayes-purity — this extends the tier idea to evidence LENSES), ADR-0025/0027 (accountability gates; this is another "turn an auditor catch into a deterministic guard"). CLAUDE.md §4 (Self-Consistency), §5/§11. `reasoning-frameworks-catalog.md §4`.
- **Affects:** any Self-Consistency / panel ranking that produces substrate evidence (Tests 1/4). Read-and-report; no DATA INAMOVIBLE mutation.

## Context

The end-to-end test (`reports/2026-06-22_pronephros-upstream-signal_e2e.html`) asked which upstream signal regulates the pronephros TF set. A 5-ranker Self-Consistency panel converged **5/5 on "Wnt (inducer)"** — but the closing composite-auditor returned **2 REVISE / 1 APPROVE_MINOR**, all three flagging `induction_vs_patterning_correct = False`. The defect:

- The "inducer" verdict rested **entirely on human-ortholog PPI** (OmniPath `WNT1→PAX2/PAX8`), the LOWEST-validity lens for a zebrafish induction claim.
- The strongest evidence in the set — zebrafish-**native** loss-of-function (RA via `aldh1a2`/`cyp26a1`) — was for a **different role** (proximodistal patterning), and was scored 0 votes partly because RA is **structurally invisible** to a PPI database (an absence-of-evidence artifact misread as evidence-against).
- **Majority-vote amplified a SHARED lens-validity bias**: all five rankers privileged the lens with explicit "stimulation" edges. Self-Consistency cannot fix a bias every member shares.

The auditor caught it. The lesson: make that catch **deterministic and pre-vote**, and make panels **not share the bias** in the first place.

## Decision

1. **`substrate_calibration/tools/evidence_weighting.py`** (read-and-report, NO-SPEND):
   - **`EVIDENCE_TIER`** — a validity hierarchy over evidence LENSES: `native_perturbation` 1.0 > `native_expression` 0.7 > `ortholog_regulatory` 0.5 > `pathway_membership` 0.2 > `absence` 0.0. Extends the IDENTIFIER `tier_weight` of `verify_output` (ADR-0024) to EVIDENCE lenses.
   - **`rank_with_lens_validity(candidates)`** — re-scores raw ranker probabilities by the BEST tier supporting each candidate (`adjusted = raw_prob × best_tier_weight`) and raises **`overclaim_flag`** when the raw-top candidate is supported only by sub-native tiers while a DIFFERENT candidate carries native evidence. The note instructs: *report the role-split, gate on native confirmation* — exactly the auditor's correction, now a deterministic guard.
   - `absence` is explicitly non-informative when the signal is structurally invisible to the lens (RA↔PPI) — callers must not treat such absence as evidence-against.

2. **Perspective-diverse panel practice (companion).** Self-Consistency panels for evidence-ranking SHOULD give each ranker a DISTINCT lens/perspective (one evidence stream each, or an assigned adversarial prior) rather than N identical prompts — so a shared bias cannot reach a false consensus. Documented in `reasoning-frameworks-catalog.md §4`. (Identical-prompt Self-Consistency remains fine for tasks without a cross-lens validity asymmetry.)

## Alternatives considered

- **Trust the majority vote + rely on the downstream auditor.** Rejected as the sole mechanism — the auditor caught it this time, but a deterministic pre-vote guard + diverse panels reduce reliance on a single catch (defense in depth; same philosophy as R3 turning §4/§11 reflexes into gates).
- **Hard-override the panel (force the weighted_top as the answer).** Rejected — the guard FLAGS and re-scores; it does not auto-decide. The role-split + human gate (causal-pruner §7.1) remain. A weighting is advisory evidence for the synthesizer/auditor, not a new oracle.
- **A learned lens-weighting policy.** Deferred — that is MITAD_B (generation). This is a deterministic, auditable check.

## Consequences

- The exact 2026-06-22 over-claim is now caught deterministically (selftest reproduces it: raw-top `Wnt` flagged + demoted below native `RA`).
- Any future panel can call `rank_with_lens_validity` before declaring a winner; an `overclaim_flag` routes to role-split + human gate instead of a single-winner claim.
- **Honest limits:** the tiers are a fixed v1 hierarchy (not calibrated from outcomes — a gap_flag, like the DERIVED=0.7 placeholder in ADR-0024); the caller must tag each candidate's `support_tiers` honestly (the guard is only as good as the tagging); perspective-diversity is a documented practice, not yet a hard-enforced panel constructor.

## Verification

`python substrate_calibration/tools/evidence_weighting.py --selftest` → PASS: the ortholog-only raw-top (`Wnt`, adj 0.21) is flagged as an over-claim and demoted below the native-evidence candidate (`RA`, adj 0.40); a native-supported raw-top raises no flag. NO-SPEND, deterministic.

## Substrate instrumentation (§5)

- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (the guard is a deterministic predicate over tagged candidates). Self-report per §5.
- **agents_invoked:** `composite-auditor` — the 2026-06-22 closing audit IS the source of this fix (its REVISE is now executable); `causal-pruner` — not-applicable (tooling, no biological candidate generation).
