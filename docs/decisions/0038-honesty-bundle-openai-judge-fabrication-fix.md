# 0038 — Honesty bundle: cross-provider (OpenAI) judge, judge-fabrication fix, deterministic-first scoring

- **Date:** 2026-07-11
- **Status:** accepted
- **Decided by:** Emmanuel (chose the "honesty bundle" scope); implemented + validated on a 6-question subset
- **Affects:** `evaluation/run_held_out.py` judge panel + scoring; the reviewer-independence + LLM-judge-validity concerns the closing audit (ADR-0037) raised

## Context

ADR-0037's closing composite-audit REVISE'd all 7 session claims and surfaced three method flaws that gate any
future strengthening: (C2) within-Anthropic "divergence" is mostly capability-tier grading noise, not
independence; (C4) the LLM judges FABRICATED verification narratives ("3/3 live-Ensembl spot-checks resolved
correctly") they were structurally incapable of performing, plausibly rewarding the mere APPEARANCE of
grounding; and the transversal point that LLM-judge quality is not ground truth. The founder chose the cheap
"honesty bundle" (make the existing controls trustworthy) over scaling to 30 or building more apparatus, and
noted an OpenAI key is available (already in `.secrets` for embeddings).

## Decision

Three changes to `run_held_out.py`, all cheap, none growing the substrate's footprint:

1. **Cross-PROVIDER judge (OpenAI).** The judge panel becomes `JUDGE_PANEL` = Opus/Sonnet/Haiku + **gpt-4o**
   (provider-tagged; `openai_verdict()` uses the OpenAI SDK function-calling with the SAME verdict schema). This
   makes cross-provider disagreement measurable — the only split that meaningfully tests independence.
2. **Judge-fabrication fix.** `judge_answer` now runs the deterministic identifier check (`verify_output`) and
   HANDS it to every judge, with a system prompt that says the judge has NO tools, must NOT claim verification
   it did not perform, and must reward correctness — not the appearance of grounding. Judges now cite the
   *provided* check ("confirmed against the deterministic check / verified_in_store") instead of inventing one.
3. **Deterministic-first labeling.** Every record's `scoring.primary_signal` is explicit:
   `store-grounded-deterministic` (real ground truth) vs `llm-judge-advisory (NOT ground truth)`. The
   store-grounded outcome, when it exists, remains the primary; the judge panel is advisory.

## Validation (6-question Level-2 subset, re-judged with the honest 4-provider panel)

- **Cross-provider (Claude vs GPT) disagreement = 1/6; within-Anthropic = 3/6.** The surprising, honest signal:
  GPT AGREES with the Anthropic majority *more* often than the Anthropic tiers agree among themselves — i.e.
  the within-Anthropic "divergence" the earlier claim leaned on was largely Opus↔Haiku adjacent-label noise
  that a cross-provider judge does not share. We now have a REAL cross-provider number, replacing the
  meaningless within-Anthropic 34%.
- **Fabrication fix works (by manual read, not phrase-count).** The phrase count was ~flat (18→19) because
  judges legitimately cite the *provided* deterministic check; reading the justifications confirms they now
  ground in that check ("verified_in_store", "confirmed against the deterministic check") rather than
  fabricating Ensembl spot-checks. Honest caveat: a phrase-count cannot distinguish legit citation from
  fabrication — the manual read is the evidence.

## Alternatives considered

- **Scale Level-2 to 30 now** — deferred (expensive; only meaningful once the judge is trustworthy, which this
  bundle establishes).
- **Swap models to fix fabrication** — REJECTED: fabrication is a prompt/design issue (any text-only judge can
  fabrication-claim); the fix is feeding the real check + forbidding invented verification.
- **Treat cross-provider agreement as validation of correctness** — REJECTED: high cross-provider agreement can
  also reflect correlated LLM bias; it is a stronger-than-within-family signal, not ground truth. Ground truth
  still needs deterministic checks (identifier subset) or human-expert rating (open subset).

## Consequences

- Reviewer-independence claims can now cite a real cross-provider measurement; the honest finding is that
  cross-provider agreement is HIGH on clear cases (not that adding a provider adds noise).
- The judge quality metric is better grounded (judges see the deterministic check) but remains ADVISORY and
  not ground truth — labeled as such in every record (`primary_signal`).
- Still open (unchanged): independent ground truth for open-reasoning questions (needs a human-expert gold set —
  the one thing more compute cannot buy); scaling Level-2 to 30; per-binding provenance authentication (ADR-0036 limit).

## Evidence

- Code: `evaluation/run_held_out.py` (`openai_verdict`, `JUDGE_PANEL`, `judge_answer` det-fed + provider split,
  `make_record.primary_signal`).
- Validation: `evaluation/runs/month_0_l2/_panel_honest_Q*.json` (6 re-judged panels, 4 providers each).
- Prior: ADR-0037 (the audit that mandated this), ADR-0031 (multi-family panels), ADR-0036 (deterministic gate).
