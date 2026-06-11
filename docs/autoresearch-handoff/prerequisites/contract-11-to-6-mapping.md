# PRE-1 — Contract mapping: hypothesis guide (11 fields) → §5 contract (6 fields)

- **Status:** prerequisite — **GATES PR-02** (reasoning-exposer sub-schema).
- **Closes:** gap C.1 (the "7-field" miscount) and gap C.20 (EPS naming collision).
- **Date:** 2026-06-10

## Why this exists

`INTEGRATION_PROPOSAL.md` repeatedly says the hypothesis guide has a "7-field contract" and §3.3
makes a "final decision" mapping 7→6 to avoid a "fork." **That is a miscount.** The guide
(`research-hypothesis-generation-guide.md` §1) lists **eleven** fields. The spurious "7" fabricates
a non-existent dilemma. The real task is an **11→6** mapping, and three of the eleven fields
(Gaps in literature, Required controls, Possible confounders) are non-trivial to fold — the
proposal silently dropped them. This doc maps all eleven explicitly, with no field dropped.

## The 11 source fields → the 6-field §5 contract

| # | Guide §1 field (11) | → §5 contract destination |
|---|---|---|
| 1 | Summary of existing evidence | `evidence_cited` |
| 2 | Gaps in the literature | `gap_flags.gaps_in_literature` |
| 3 | Candidate hypothesis | `direct_answer.hypothesis` |
| 4 | Supporting evidence | `evidence_cited` |
| 5 | Contradicting evidence | `alternatives_considered.contradictory_evidence_cited` **(obligatory non-empty)** |
| 6 | Testable predictions | `direct_answer.testable_predictions` |
| 7 | Proposed experiment | `direct_answer.proposed_experiment` (sub-field of direct_answer, **not** a 7th universal field) |
| 8 | Required controls | `gap_flags.required_controls` |
| 9 | Possible confounders | `gap_flags.possible_confounders` |
| 10 | Confidence level | `confidence` / `confidence_by_subclaim` |
| 11 | Citations | `evidence_cited` |

The contract stays **exactly 6 universal fields** (`direct_answer`, `confidence`,
`evidence_cited`, `alternatives_considered`, `gap_flags`, `framework_applied`). Hypothesis-specific
structure lives in **sub-fields** of `direct_answer` and named **sub-keys** of `gap_flags` — no
fork, no 7th field.

### The three fields the proposal dropped (now explicit `gap_flags` sub-keys)

- `gap_flags.gaps_in_literature` — what the corpus does not yet cover (drives the
  domain-recall-drop governance trigger + the §3.3 rule that agents complement via MCP/ToolUniverse).
- `gap_flags.required_controls` — controls a downstream wet-lab design must include.
- `gap_flags.possible_confounders` — confounders that would invalidate the testable prediction.

## EPS naming (closes C.20)

`EPS` is used for two different things in INTEGRATION_PROPOSAL (§5.1 says 2σ; §5.3 says p25).
Disambiguate everywhere going forward:

- **`EPS_delta = 2σ`** — one-sided signal-detection threshold ("is this delta a real improvement,
  or noise?"). Used by the effective-frontier keep/discard rule.
- **`EPS_pass = p25`** — percentile pass/fail threshold on bounded [0,1] metrics. Replaces the
  "70% arbitrary" composite-auditor agreement threshold.

These are distinct quantities; never write bare "EPS."

## Downstream

PR-02 (reasoning-exposer sub-schema) MUST implement: `alternatives_considered` with an obligatory
non-empty `contradictory_evidence_cited`, and the three `gap_flags` sub-keys above. PR-01
(`hypothesis-generator`) emits `direct_answer` in the guide's example shape
(Hypothesis / Rationale / Contradictory Evidence / Testable Prediction / Experiment / Confidence)
folded into these 6 fields.
