# PR-11 — SKILL.md meta-loop section: 4 pre-approved governance-proposal templates

- **Status:** APPLIED (GWT v1.1 Cycle 5): meta-loop section added to the architect SKILL.md.
- **Target:** `skills/custom/organogenesis-agent-architect/SKILL.md` (new "Meta-loop" section).
- **Depends on:** ADR-0013 (meta-loop human-gated), ADR-0009 (RIL), the governance queue.

## Decision

Add a Meta-loop section to SKILL.md documenting the four pre-approved governance-proposal templates and
the human-gate invariant (`self_applied: false`). Templates:

1. **domain-recall-drop** — sub-domain X hypotheses rated ≥4 on Completeness fall below the global
   median for 2 consecutive K=6 windows → fix-cascade: hybrid BM25+dense retrieval → adjusted MeSH
   filters → tuned reranker → (last resort) embedding fine-tune.
2. **contradiction-section-empty** — `alternatives_considered.contradictory_evidence_cited` empty in
   >40% of outputs → add a mandatory contradiction-search step (negated query) before pipeline entry.
3. **citation-coverage-drift** — Proxy-0 citation verification drops with no local change → suspect a
   provider model-id deprecation / wrapper change → re-pin model-id, re-run the noise-probe.
4. **sub-domain-calibration-divergence** — Proxy-2 ECE diverges by biological sub-domain → tune the
   per-sub-domain isotonic bins (the regressors already exist from day 1, ADR-0014).

## Cycle status

- Applied: the SKILL.md meta-loop section + templates. One real proposal already in the queue from
  Cycle 1 (`gp-2026-06-10-contradiction-section-empty`).
- Live firing of templates accrues with use (telemetry thresholds need accumulated data).
