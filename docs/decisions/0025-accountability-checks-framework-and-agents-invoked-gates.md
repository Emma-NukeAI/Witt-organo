# ADR-0025 — Accountability checks: §4 framework-citation gate + §11 agents_invoked gate (R3)

- **Status:** Accepted (Emmanuel, 2026-06-18) — plan approved this session; R3 built + validated against the live ledger + composite-audited at close.
- **Relates:** ADR-0006 (catalog-agent invocation discipline + the matrix), ADR-0005 (test-claim language), ADR-0023/0024 (R1/R2). CLAUDE.md §4 (framework citation by §section), §11 (agent-invocation preflight). `agent-invocation-matrix.md` §1/§2.
- **Affects:** every substrate-evidence output (§5 claim records); Tests 1/2 (accountability of reasoning + agent invocation); Pillars 2 (agent invocation) + 3 (substrate/framework election). Phase I. Additive — read-and-report, no agent design changed.

## Context

§11 (which catalog agent for this work-type) and §4 (cite the framework by specific §section, not a bare tier) were **hand-consulted reflexes** — a markdown matrix + catalog with **no executable check**. The `failure_log.jsonl` records both as recurring failures that were "resolved: legacy left per ADR-0002, forward-enforced only": `framework_miscited` (the 2026-05-14 records cite "§Tier 2", the §4 anti-pattern) and `contract_field_missing`. "Forward-enforced only" had no enforcer. R3 supplies the deterministic forward-enforcement.

These are **CHECKS, not learned selectors** — a learned framework/agent policy is MITAD_B (the generation engine). R3 stays pure accountability machinery.

## Decision

`substrate_calibration/tools/accountability_checks.py` — read-and-report, mutates nothing:

1. **`check_framework_citation(record)` (§4)** — `framework_applied` must cite a **specific catalog §section** (regex `§\s?\d`), must **not** be a bare `Tier N` header (the documented anti-pattern), and **should** quote a criterion. FAIL on bare-tier / no-section; WARN on missing quote.

2. **`check_agents_invoked(record)` (§11)** — the `agents_invoked` field is present + well-formed (valid status enum {invoked, skipped-ad-hoc, not-applicable}; `skipped-ad-hoc` carries a substantive, non-boilerplate reason), and the **hard-rule work-types it can infer** have their required agent present-or-justified. The coverage rules are a small table **mirroring `agent-invocation-matrix.md` §1/§2** (additive: a new matrix row = one rule here).

## Alternatives considered

- **Parse the matrix markdown directly.** Rejected — the work-type signals are prose; parsing is fragile. The checker mirrors §1/§2 as a small **additive rule table** (the matrix MD stays the human-readable authority; the table is its executable projection, and the checker is itself the drift-catcher between an output and the matrix).
- **Hard-FAIL when `reasoning-exposer` is absent from every §5 record's `agents_invoked`.** Softened to **WARN** — the matrix note legitimizes Phase-I Method-2 skip-with-justification when a human is in the loop; a blanket FAIL would flag every record.
- **A learned framework/agent selector.** Deferred — that is MITAD_B (generation). R3 is a deterministic check.

## Consequences

- **§4 and §11 become verifiable gates**, not just reflexes — drift is caught deterministically.
- **Validated against the live ledger:** 5/10 PASS at claim-time (6/11 once the R3 record lands), 1 WARN, and **4 FAIL = exactly the 2026-05-14 records citing "§Tier 2"** — the **forward-enforcement of the `framework_miscited` failure**. Legacy records are immutable (ADR-0002) → surfaced, **not modified**.
- **Additive:** adding a matrix row = adding one coverage rule; the checker enforces it with no other code change.
- **Honest limits:** the coverage rules are a subset of the matrix (v1: `ranked_candidates` → `causal-pruner`, `substrate_audit` → `composite-auditor`, inferred heuristically); `reasoning-exposer` coverage is WARN not FAIL; work-type inference is heuristic (an output may declare its work-types explicitly for a stricter check).

## Verification

Self-test (NO-SPEND): a compliant record PASSes; a bare-tier citation + a ranked-candidates claim missing `causal-pruner` is caught as FAIL with specific reasons. **Snapshot at claim-time = 10 records → 5 PASS / 1 WARN / 4 FAIL; once the R3 record itself lands the ledger is 11 → 6 PASS / 1 WARN / 4 FAIL (the R3 record PASSes). The invariant asserted is the 4-FAIL §Tier-2 legacy set (stable); totals grow as records accrue.**

**Closing composite-auditor (3 adversarial lenses, this session): 3/3 APPROVE (minor).** No-mutation confirmed (sha256 + `git diff --exit-code` clean over the 4 legacy records; the only write is the report to `--output`); deterministic (regex + dict, no learned selector — no MITAD_B leak); caught the real failure without modifying the legacy records. **Fixes applied:** broadened the §11 `ranked_candidates` detector to catch the legacy "is sufficient to induce" / `*pruner*`-category phrasing (it now fires on `claim_20260514_143000`, where `causal-pruner` is present → coverage PASS, verdict still FAIL via §4); documented that the §4 gate reads `framework_applied` ONLY (a `framework_applied_corrected` retrofit is NOT honored — legacy stays FAIL by design) and that the quoted-criterion check is presence-only (WARN, never FAIL).

## Substrate instrumentation (§5 / §11)

- **Claim record:** `substrate_calibration/records/claim_20260618_160000_r3-accountability-gates.json`.
- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (the checks are deterministic predicates over the record). Self-report per §5.
- **agents_invoked:** `composite-auditor` — invoked (closing audit); `causal-pruner` — not-applicable.

## Update (2026-06-18, during the R4 close)

Running R3's checker over the R4 record surfaced a **false positive**: the broadened `ranked_candidates` keyword path fired on a `methodological` (tooling) record that merely *mentions* a minimal-set it projects. Fixed: the keyword path is now **suppressed for `claim_category == "methodological"`** (a meta/tooling claim is not generating biological candidates); the category path (`ranking` / `*pruner*`/`*generation*`) is unchanged, so genuine generation (e.g. the legacy `claim_20260514_143000`, category `pruner-generation-ad-hoc`) still fires. Re-verified: self-test PASS; the R4 record → PASS; `143000` → still FAIL (category fires + §4 §Tier-2); full ledger → {7 PASS, 1 WARN, 4 FAIL}, the 4-FAIL §Tier-2 invariant unchanged. Also (with R4) `accountability_checks.py` gained the cp1252 `sys.stdout.reconfigure` guard (the encoding gap was systemic across the R-tools).
