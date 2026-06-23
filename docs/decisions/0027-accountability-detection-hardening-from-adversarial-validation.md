# ADR-0027 — Detection-layer hardening of MITAD_A from the 2026-06-22 adversarial validation

- **Status:** Accepted (Emmanuel, 2026-06-22) — the adversarial validation (`reports/2026-06-22_mitad-a-adversarial-validation_*.html`) found the *safety* layer irrefutable but the *detection* layer narrower than claimed, with confirmed bypasses. The founder authorized applying **all six** remediations + an exigent smoke test.
- **Relates / supersedes:** ADR-0023 (R1 replay), ADR-0024 (R2 admissibility H(c)), **ADR-0025** (R3 §4/§11 gates — this ADR **supersedes its 2026-06-18 `claim_category=="methodological"` suppression** with structural generation detection), ADR-0026 (R4 WSTS). CLAUDE.md §4/§7/§11.
- **Affects:** `verify_output.py`, `accountability_checks.py`, `world_state.py`, `build_regression_cases.py`, `compute_ece.py` (shared loader). Read-and-report unchanged; **no DATA INAMOVIBLE mutation**. Pillars 1–5.

## Context

The adversarial validation verdict: the **safety property** (read-and-report, advisory governance, human-gated mutation) *defends itself* — 3 adversarial auditors could not break it. The **detection/enforcement layer** was the soft edge. Bypasses confirmed by re-running the code (not trusting the subagents):

- **N1** — `verify_output` checked an ENSDARG *exists* in the store, never that it is *bound* to the paired symbol. The exact "wrong ID that collided with an unrelated gene" corruption (`failure_log` line 1) was unguarded in general.
- **W1** — a required agent marked `not-applicable` on a detected work-type was scored WARN, not FAIL (softer than `absent`).
- **W2/N3** — the causal-pruner keyword path was *suppressed* for self-declared `claim_category=="methodological"` (introduced in ADR-0025's update). A generation claim mislabeled methodological — or phrased outside the keyword set — evaded the §7 causal-pruner hard rule.
- **N6** — §4 validated citation *syntax* (a §section + some quote) but never the quote's *truth*; a fabricated criterion under a valid section passed clean.
- **W5** — `world_state` granted `causal_admissible=True` by keyword inference; a causal verb in an *observational* sentence (or a methodological record merely *describing* `do(a)`) was over-certified (66% false-positive on the do-typed subset of the real corpus — including the project's own R2/R4 records).
- **W3** — `build_regression_cases` synthesized a guard only from a free-text `<symbol> resolves to <ENSDARG>` triple; the bulk "15/16 wrong IDs" failure produced zero guards.

(Honest scope note: **N2** — ENSDARG regex case/separator brittleness — was *partially* confirmed; the versioned `…054611.1` form is actually caught. N2 regex-hardening is **not** in this round and remains an open gap_flag.)

## Decision

Six deterministic, read-and-report hardenings (no learned selectors — that is MITAD_B):

1. **N1 — symbol↔ENSDARG binding (`verify_output.py`).** `verify_bindings()` walks an output object for **explicit structured pairs** ({symbol, ensdarg}); a pair whose ENSDARG ≠ the store's binding for that symbol fails `admissible()` (hard). Free-text pairing is **not inferred** (it would over-fire on any text naming a gene and, separately, an accession) — that stays an honest gap_flag.
2. **W1 — `not-applicable` on a strong signal → FAIL (`accountability_checks.py`).** A required agent declared `not-applicable` on a **strongly** detected work-type is now a contradiction-FAIL (was WARN).
3. **W2/N3 — structural generation detection (`accountability_checks.py`).** `claim_category` is no longer a **suppressor**; it is only a positive signal. **STRONG** = the category self-identifies as generation (`rank|prun|generation`) **OR** the output carries a structured candidate set (`ranked_candidates`/`minimal_set`/…) → causal-pruner *required* (FAIL if absent/`not-applicable`). **WEAK** = a sufficiency phrase in `claim_text` → advisory WARN only, and only when the agent is absent (PASS when addressed — honoring Phase-I skip-with-justification). This closes the mislabel hole *and* fixes the prior over-fire on extraction/tooling records that merely *mention* a minimal-set.
4. **N6 — quote-vs-catalog validation (`accountability_checks.py`).** The quoted criterion is checked against the **actual catalog text**: in the cited §N body → PASS (`validated`); elsewhere in the catalog → WARN (`elsewhere`, paraphrase/mis-attribution); **nowhere in the catalog → FAIL (`not_in_catalog`, fabricated)**. Bare-tier/no-section remains the hard FAIL. Degrades to presence-only if the catalog file is unavailable (never a false FAIL).
5. **W5 — explicit-block requirement for causal admissibility (`world_state.py`).** `causal_admissible=True` is granted **only** for an explicit `world_state_transition` do-block. A keyword-inferred do-type is a **candidate** (`causal_admissible_candidate`), never admissible — killing the over-certification.
6. **W3 — structured guard synthesis (`build_regression_cases.py`).** `extract_identifier_guards()` also reads a structured `id_corrections: [{symbol, correct, wrong}, …]` field, so a **bulk** failure synthesizes one self-validated guard **per symbol** (not zero). A `--failure-log` override enables NO-SPEND testing. Guards remain correct-by-construction (built only if they pass the live store).

**Latent bug fixed in passing:** `compute_ece.load_records` opened record JSON **without `encoding="utf-8"`** → cp1252 mojibake of `§`/em-dash/quotes on Windows, which silently broke the N6 quote match (and any text check over `framework_applied`). Now reads UTF-8. This is the shared loader for all four R-tools.

## Alternatives considered

- **Free-text proximity heuristic for N1** (resolve "<symbol> … <ENSDARG>" within N chars). Rejected — over-fires on any prose naming a gene and an unrelated accession. Structured-pair = hard; free-text = gap_flag is the honest line.
- **Hard-FAIL any quote not verbatim in the cited §N (N6).** Rejected — a real catalog criterion cited from the Tier-overview line (e.g. niche-taxonomy's §8 quote at catalog line 58) would false-FAIL. `elsewhere → WARN`, `not-in-catalog → FAIL` separates paraphrase from fabrication; distinguishing paraphrase from a *correct* citation is left to composite-auditor (a judge, not a deterministic gate).
- **Keep keyword-only generation detection, just add verbs.** Rejected — still gameable by category and still over-fires on mentions. Structural detection (candidate field) is non-gameable: a real generation output *names* its candidates.
- **Drop `causal_admissible` entirely (W5).** Rejected — the explicit-block path is the intended forward mechanism; demoting inference to `candidate` preserves the signal without the false certification.

## Consequences

- **Behavior changes (non-regression verified, 17/17 smoke):** two real records move **PASS→WARN** under N6 (`collaborator-zebrafish-lbpp`, `niche-taxonomy-audit`: §8 quotes that live in the catalog's Tier-overview, not the §8 body → `elsewhere`). `world_state` now certifies **0** keyword-inferred records as `causal_admissible` (was 3, of which 2 were over-fires); the genuine biological do-claim (`143000`) is now an honest `candidate` pending an explicit block. **No record moves to FAIL that was not already FAIL** (the 4 legacy §Tier-2 records). R1–R4 stay PASS.
- **The bypasses are closed at the right severity:** N1 mis-binding → admissible=False; W1/W2/N3 structured generation → §11 FAIL; N6 fabricated quote → §4 FAIL; W5 over-fire → eliminated; W3 → bulk failures now guardable.
- **Honest residual gaps (gap_flags):** N2 regex robustness (case/separator) deferred; N1 free-text pairing remains an inference gap (only structured pairs are hard-checked); N3 text-only generation is WARN not FAIL (a bare textual sufficiency claim with no structure/category is ambiguous by construction); the §11 coverage table is still a subset of the matrix (now structurally-detected, not category-trusting).

## Verification

**Exigent smoke test (`substrate_calibration/tools/smoke_adr0027_hardening.py`, durable + NO-SPEND): 23/23 PASS** (the initial 17/17 harness, extended with the N2 + closing-audit cases).
- **A · evasion→caught (8/8):** N1 mis-binding → admissible=False; correct binding → True; fabricated ENSDARG → False; W1 → §11 FAIL; W2/N3 structured → §11 FAIL; N3 text-only → no-longer-silent (WARN); N6 fabricated → §4 FAIL/`not_in_catalog`; corrupt store → replay REGRESSION Δv=−1.0 ×3.
- **B · non-regression (5/5):** R1–R4 PASS; legacy FAIL (by design); no new record-level FAIL (4 total); replay over the real corpus → NO_REGRESSION; world_state → 0 false causal_admissible.
- **C · invariants (4/4):** SHA256(`verified_identifiers.json`) = `f070b40c…707` unchanged; `git diff` empty for `records/`, `regression_cases/`, `analysis/outputs/`.
- **All 5 tool selftests PASS** under the new contract.

**Closing composite-auditor (3 adversarial lenses, this session):** see the §5 claim record + the closing report. Self-audit by the producer is prohibited (§7).

## Substrate instrumentation (§5 / §11)

- **Claim record:** `substrate_calibration/records/claim_20260622_120000_adr0027-detection-hardening.json`.
- **framework_applied:** Chain-of-Verification — per `reasoning-frameworks-catalog.md §8` (each fix carries a verification question answered independently by the smoke test before adoption). Self-report per §5.
- **agents_invoked:** `composite-auditor` — invoked (closing audit, Mode 1 ≥3 adversarial); `causal-pruner` — not-applicable (tooling, no biological candidate generation).

## Update (2026-06-22 close) — closing composite-audit found real defects; REVISE applied

The closing composite-auditor (workflow `wf_15c04cc6`, 3 independent adversarial lenses) returned **3/3 APPROVE_MINOR** — and earned it: each auditor **constructed and ran** real defects in the first-round fixes. All were fixed the same session (the loop closing on itself: the audit found holes in the fix, the fix was fixed and re-verified).

- **N1 missed the real output shape.** `01_schoels_analysis.py` emits `{marker, ens_id}` rows — neither key was in the allowlist, so a mis-binding in the very shape N1 cites evaded (`admissible=True`). Also a NOT_FOUND symbol paired with a real-but-other-gene ENSDARG slipped. **Fix:** added `marker`/`ens_id` to the key sets **and** a key-agnostic **reverse-binding** check (the paired ENSDARG resolving to a *different* stored symbol is now caught even when the paired symbol is NOT_FOUND). Verified: `{marker:pax2a, ens_id:<wt1a's id>}` and `{symbol:osr1, ensdarg:<wt1a's id>}` both → `admissible=False`.
- **N6 first-quote-only false-FAIL (a NEW over-fire I introduced).** `_QUOTE_CAP.search` read only the first quoted span, so a legitimate record with an aside quote *before* the genuine criterion was classified `not_in_catalog` → false FAIL. **Fix:** scan **all** quoted spans (`findall`); `validated` if any is in the cited §N, `elsewhere` if any is in the catalog, `not_in_catalog` only if none. Plus: ignore spans `< 20` chars (a trivial `"the answer"` no longer validates as PASS), and **attribute the intro summary-table line** to its named framework's section (the CoVe one-liner now validates under §8). Net: `collaborator-lbpp` + `niche-taxonomy` **return to PASS** — the prior PASS→WARN is gone, so this round has **zero** PASS→WARN regression.
- **W2/N3 over-fire on non-biological categories.** Bare `prun`/`generation` substrings fired on governance (`pruning-proposal` = DI orphan-node pruning) and tooling (`report-generation`); a candidate field holding *repository names* (`['PRIDE','MassIVE']`) tripped detection. **Fix:** tightened `_GEN_CATEGORY_RE` to biological-generation phrasings (still matches the legacy `pruner-generation-ad-hoc`); candidate fields now require ≥2 **gene-symbol-shaped** items.
- **Producer-claim correction (auditor-2):** `build_regression_cases.py` has **no** `--selftest` (uses `--dry-run`); the validation is "4 `--selftest` tools + `build_regression_cases --dry-run` + the `verify_output` module smoke," not "5 selftests."

**Re-verification after REVISE:** all 5 tool selftests PASS (accountability selftest now also asserts the multi-quote VALIDATE, governance/repository non-over-fire); exigent smoke test **17/17**; accountability over the 13 records = **{8 PASS, 1 WARN, 4 FAIL}** (the 4-FAIL §Tier-2 invariant holds; the 1 WARN is pre-existing `zesta` no_quote); replay **NO_REGRESSION**; SHA256(`verified_identifiers.json`) = `f070b40c…707` unchanged; `git diff` empty over `analysis/outputs/` + `regression_cases/`.

**Residual gaps (honestly scoped, per the auditors):** N1 forward-binding is allowlist-keyed (a pair under a wholly unanticipated key still needs the reverse-check backstop); N1 free-text pairing not inferred; N3 text-only paraphrase generation is WARN not FAIL; the §11 coverage table remains a structurally-detected subset of the matrix.

### Follow-up (same session): N2 closed too

After the close, the founder opted to also fix **N2** (the one remediation left out of the six). `verify_output.py` ENSDARG extraction is now **tolerant** (case-insensitive, optional `[\s_\-]` separator, optional `.version` suffix) and **canonicalizes** every match to `ENSDARG<11 digits>` before resolving. So `Ensdarg00000054611`, `ENSDARG_00000054611`, and `ENSDARG00000054611.1` no longer evade — all → `admissible=False`. Binding values are canonicalized identically (a correct `{marker, ens_id}` pair in any case still passes; a mis-binding in any case still FAILs). Re-verified: module smoke (N1+N2) all expected; exigent smoke still **17/17**; 5 selftests PASS; replay NO_REGRESSION; accountability {8 PASS, 1 WARN, 4 FAIL}/13; SHA256 `f070b40c…707` unchanged. **N2 is no longer a residual gap.**
