# ADR-0031 — Multi-family composite-auditor panels (reviewer independence)

- **Status:** Accepted — from the external review (Fable 5, 2026-07-05, rec 2), `docs/EXTERNAL_AUDIT_FABLE5_REVIEW.md`.
- **Relates:** ADR-0006 (composite-auditor replaces single-LLM audit), CLAUDE.md §7 (audit gate), the full-functionality audit (which used a same-family panel — the very weakness this fixes).
- **Affects:** how `composite-auditor` panels are convened (process/policy). No code mutation of the DI.

## Context

The external auditor's sharpest governance critique: our composite-auditor's "three independent reviewers"
were **three instances of the same base model** (3× `claude-opus-4-8` in the 2026-07-04 audit). Same-model
reviewers have **correlated errors** — three correlated votes ≈ one vote with extra cost. Adversarial
prompting reduces but does not remove shared blind spots. Independence was *asserted, not demonstrated*.

Empirically the same-family panel still produced useful disagreement (2× APPROVE_MINOR + 1× REVISE), and a
genuinely independent reviewer (Fable 5) surfaced critiques the Opus panel missed (reviewer-independence
itself, retrieval-measurement gap) — direct evidence that cross-family diversity catches more.

## Decision

1. **Composite-auditor panels SHOULD mix model families**, not stack instances of one model. Available
   families: **Claude** (`claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5`) and **Fable**
   (`claude-fable-5`). Default panel for a substantive audit: **≥1 Claude (Opus) + ≥1 Fable + 1 more**
   (a different Claude size, or a second Fable), so at least two families are represented and reviewer
   size/training varies. Full cross-vendor independence (a third provider) is **not yet available** — this
   is recorded as a standing limitation, not a solved problem.
2. **Measure and log inter-reviewer disagreement** each panel (verdict spread + whether any reviewer
   dissented). A panel with near-zero disagreement over time is evidence the panel is redundant — then
   collapse it and say so. Disagreement is a *feature to be measured*, not hidden.
3. **Do not describe a panel as an N-vote independent gate unless the families are actually mixed.** A
   same-family panel is reported honestly as "N correlated reviewers."

## Demonstration (2026-07-05) — the first multi-family panel + measured disagreement

A 3-model panel (Opus + Fable + Sonnet) reviewed "the 5 recs are adequately addressed + the self-assessment
is honest." Logged to `substrate_calibration/records/panel_multifamily_20260705.json`:

| Reviewer | Family | Verdict | Confidence |
|---|---|---|---|
| A | Claude (Opus) | APPROVE_MINOR | 0.78 |
| B | **Fable** | APPROVE_MINOR | 0.72 |
| C | Claude (Sonnet) | APPROVE_MINOR | 0.68 |

**Measured disagreement:** verdict unanimous (3/3 APPROVE_MINOR); confidence spread 0.10 (mean 0.73). But
**concern diversity was real** — all three flagged the thin measurement (n=3 probes, n=10 calibration); two
flagged the "inamovible" guarantee as conditional-until-hardened; and **Sonnet uniquely** caught a meta-point
the others missed: *rec #2 itself is soft-overclaimed — only 2 families exist, so this panel's composition is
the evidence for the limitation, not its resolution.* That a cross-model reviewer surfaced a concern the
others didn't — even at unanimous verdict — is the empirical case for family diversity (a same-model panel
would more likely have shared the blind spot). Sonnet's catch is exactly the standing limitation this ADR
already records; the panel confirmed it rather than dissolving it.

## Consequences

- Higher per-audit cost (mixed families, more tokens) — acceptable per the operational-spend directive
  (quality of the answer over the bill); still bounded (a panel ≈ a few model runs).
- The 2026-07-04 same-family audit is retroactively labeled "3 correlated Opus reviewers"; its findings
  stand (they were verified), but its *independence* claim is corrected here.
- **Standing limitation (panel-confirmed):** only two genuine model families are available (Claude + Fable);
  full vendor-diversity (a 3rd provider) is a future item. Report multi-family panels as "2-family," not "3."
