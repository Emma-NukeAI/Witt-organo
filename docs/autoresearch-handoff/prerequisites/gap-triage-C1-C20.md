# Gap triage — Anexo C (20 gaps) disposition for GWT v1.1

- **Date:** 2026-06-10
- **Method:** `organogenesis-agent-architect` Mode B (audit + delta).
- **Scope:** which of the 20 gaps in `INTEGRATION_PROPOSAL.md` Anexo C are resolved in this
  PR-cycle (Cycle 1) vs deferred with a named precondition.

## Formal closure of C.11 (FALSE POSITIVE — verified)

C.11 claims "the reference to `program.md §15 v3` does not exist." **It exists.** Quoting the
imported `docs/autoresearch-handoff/program.v3.md` lines 201–204:

> ## 15. Meta-loop — proposing changes to THIS file (human gate, non-negotiable)
>
> You MAY write a `governance-proposal` when you spot a systematic inefficiency in your own
> process. You MUST NOT edit `program.md` yourself. Governance is human-applied only.

The `§15 v3` citations in INTEGRATION_PROPOSAL (§2.1, §3.2, §5.6, §7.9, §9.4) are therefore
**correct**. C.11 is **CLOSED — false positive**. (Note: the user's brief referred to this as
"C.10"; the actual §15 gap is numbered **C.11** in Anexo C. C.10 is the separate deny-list gap.)

## Triage table

| Gap | Title (abbrev) | Disposition | Reason / precondition |
|---|---|---|---|
| C.1 | contract miscount 7 vs 11 | **RESOLVE** (PRE-1) | doc-only; gates PR-02 |
| C.2 | Test 1 not operationalized | DEFER → PR-04 / html-contract | PR-01 flags as `gap_flag` |
| C.3 | Test 2 not operationalized | DEFER → PR-08 | checkpoints need program-manager |
| C.4 | Test 3 threshold missing | DEFER → PR-04 | PASS criterion lives in PR-04 |
| C.5 | Test 4 sub-domains / ECE target | DEFER → PR-06 | calibration-tracker + per-sub-domain isotonic |
| C.6 | Proxy-2 ground truth uncalibrated | DEFER → PR-06 + live raters | no rating infra yet |
| C.7 | multi-family API budget | **DEFER — NO-SPEND block** | standing no-spend directive |
| C.8 | ceded slot vs IP moat | **RESOLVE** (ADR-0008) | cede investor-relations-drafter, keep ip-patent-watcher → moat intact |
| C.9 | wet-lab handoff orphan | **RESOLVE (spec)** → PR-12 | §7 safety; spec authored this cycle |
| C.10 | deny-list underspecified | DEFER → PR-10 | regulatory-ethics-advisor 2-layer |
| C.11 | "§15 v3 missing" | **CLOSED — FALSE POSITIVE** | §15 exists (program.v3.md L201-204, quoted above) |
| C.12 | framework_applied self-report as ground truth | DEFER → PR-11 + external RIL ledger | self-report anchored to ledger (Cycle 3) |
| C.13 | KG anti-pattern in schema | **RESOLVE** (PRE-1 / PR-02) | trim to day-1 fields |
| C.14 | K=6 vs Month-4 gate timing | DEFER → PR-08 | held_out_set sized to 15 items |
| C.15 | Test-5 flag attachment owner | DEFER → PR-09 | domain-knowledge-curator side-effect |
| C.16 | Self-Consistency independence | DEFER → PR-05 (NO-SPEND) | multi-family deferred |
| C.17 | single-LLM auditor reintroduced | **RESOLVE (spec)** → PR-02 split | syntactic (reasoning-exposer) vs semantic (composite-auditor) |
| C.18 | frontmatter/template missing | **RESOLVE** (PR-01) | ≤1024-char bilingual frontmatter authored |
| C.19 | Proxy-3 vs Proxy-2 retro-correction | DEFER → PR-06 + wet-lab outcomes | retro-correction protocol later |
| C.20 | EPS collision (2σ vs p25) | **RESOLVE** (PRE-1 glossary) | EPS_delta vs EPS_pass |

## Summary

- **Resolved this cycle (8):** C.1, C.8, C.9 (spec), C.13, C.17 (spec), C.18, C.20 + C.11 (closed).
- **Deferred with a named precondition (12):** C.2–C.7, C.10, C.12, C.14–C.16, C.19.

Each deferral names the PR that will close it (PR-03…PR-12) — see `INTEGRATION_PROPOSAL.md` §7 and
the dependency graph in the GWT v1.1 plan §9. No gap is dropped; every deferral is tracked.
