# ADR-0023 — Replay-as-regression + no-regression governance pre-filter + failure-derived regression-case corpus (R1)

- **Status:** Accepted (Emmanuel, 2026-06-18) — plan approved this session; R1 built + verified end-to-end + composite-audited at close.
- **Relates:** ADR-0011 (EPS measured), ADR-0012 (reactive calibration K=6), ADR-0013 (governance meta-loop — *agent proposes, human applies*, `self_applied:false`), ADR-0016 (RIL_PROGRAM charter — §3 EPS, §8 keep/discard), ADR-0005 (test-claim language), ADR-0002 (version-preservation — records immutable), ADR-0022 (the self-reinforcing answer loop). CLAUDE.md §7 (human gates, anti-fabrication), §10/§11.
- **Affects:** the Reasoning-Improvement Loop (`substrate_calibration/`); Tests 3 (iteration) & 4 (calibration); Pillar 5 (loop de automejora). Phase I. Additive — no agent design changed.

## Context

The concept-bridge analysis (`reports/concept-bridge-analysis-v1.html`, composite-audited 3/3) found that MITAD_A's "máquina de rendición de cuentas" already had **persistence** + **replay-as-recalibration** (`compute_ece`/`rolling_calibration`/`retrospect` re-read the whole record buffer), but lacked two §3.1 complements:
- **#3 replay-as-regression** — there was no harness that *re-executes* a stored case against a CHANGED system Σ′ to detect a previously-passing case now failing (Δv<0). "Did the system improve, or merely drift?" was not a measurable predicate.
- **#4 a no-regression gate** — governance proposals were **human-gate-only**; nothing replayed a proposed meta-change (a new rule/scoring-fn/schema/store edit) against the frozen held-out before the human saw it.

The canonical failure this must guard is the **2026-06 marker-ID corruption** (`docs/findings/2026-06-10-…`; `failure_log.jsonl`): 15/16 hardcoded ENSDARG IDs wrong + the `wt1a` false-positive expression row. The founder requirement (this session): *when the human passes through the loop and an error is found, the system must learn from it and reinforce where the gap was* — and MITAD_A is **in continuous improvement**, so the mechanism must be **additive** (grow with new errors/records/rules), human-gated.

## Decision

Add three small, **reuse-first, read-and-report** tools to `substrate_calibration/tools/`, one optional record field, and one durable corpus dir — **mutating nothing** (no DATA INAMOVIBLE, no ledger; reads are free per §7):

1. **`replay_and_regress.py`** — re-executes the deterministically-replayable check embedded in each stored case against the current system Σ′ and reports **Δv** per case (regression = baseline POSITIVE → current NEGATIVE). v1 replay type: `identifier_resolution` (resolver round-trip + `verify_output` gate). Reuses `compute_ece.load_records`/`outcome_to_label`, `resolve_id`, `verify_output`, the record `seed`, and `evaluation/held_out_set_v1.json` (the frozen H, run-snapshot slot ready).

2. **`governance_prefilter.py`** — an **advisory, non-blocking** pre-filter inserted **before** the human gate (queued→approved): it replays the records (+ regression-case corpus) under the proposed Σ′ and reports per-case dominance. Tarski/Gödel: a policy cannot certify its own improvement from within its level; the frozen H is the strictly-higher level. It **never** approves/rejects/applies (ADR-0013 `self_applied:false` intact) — it only surfaces a regression for the human / `composite-auditor`.

3. **`build_regression_cases.py`** — turns `failure_log.jsonl` entries into **permanent, replay-bearing guards** in `substrate_calibration/regression_cases/`. **Self-validating** (a guard is written only if it genuinely passes the live store today). This is the concrete "aprender del error y reforzar": each logged error → one more guard that catches its reintroduction. **Additive by construction** — new failure ⇒ new guard, no tool change.

4. **An optional top-level `replay` block on claim/guard records** (forward-looking; the immutable legacy records — ADR-0002 — are untouched; new records carry it). Guards live in a **separate `regression_cases/` dir**, never mixed into the immutable `records/`.

## Alternatives considered

- **Make the pre-filter blocking** (auto-reject regressive proposals). **Rejected** — violates §7 / ADR-0013 (the human gate is final; agents propose, humans apply). Advisory + surfaced is the correct form.
- **Store guards inside `records/`.** **Rejected** — records are immutable (ADR-0002) and are *claims*, not generated guards; a separate `regression_cases/` keeps provenance clean and is loaded alongside via `--cases-dir`.
- **Build a full held-out re-run harness now** (execute the 30 H questions under Π vs Π′). **Deferred** — needs `evaluation/runs/month_N` (the planned slot) + an answering harness. v1 uses the deterministic identifier guards (testable today) and leaves the per-question run-snapshot path wired and ready (`--baseline-run`/`--proposed-run`).
- **A new heavy dependency / learned drift model.** **Rejected** — *prueba pequeño*: Δv on a discrete label flip + the existing EPS_delta (RIL_PROGRAM §3/§8) suffice; no new deps (numpy already present via `compute_ece`).

## Consequences

- **"Improved vs drifted" is now a measurable per-case predicate** (Δv<0), pairing with the EPS_delta=2σ keep/discard rule (RIL_PROGRAM §3 def / §8 use) → strengthens Test 3.
- **Errors become permanent guards** — the auto-replayable corpus **grows with use** (additive); the loop literally reinforces where gaps were found.
- **Adding a new RULE is now safe-by-construction** — the pre-filter replays a proposed meta-change against H before the human gate. This is the formal mechanism that makes MITAD_A's continuous improvement (substrate/agents/rules) safe.
- **Human gate stays final**; everything is read-and-report; no DI/ledger mutation → additive, backwards-compatible, satisfies §7 (no ADR-breaking change to existing agents).
- **Reuse-first / small code:** 3 tools, 1 optional field, 1 dir; reuses `load_records`, `resolve_id`, `verify_output`, `compute_ece`.
- **Honest limits:** records without a `replay` block are reported `manual` (not silently passed); the held-out per-question path is ready but inert until month-N runs exist; prioritized-replay IS-correction for an unbiased aggregate ECE is an open formal caveat (noted, not resolved).

## Verification

Self-tests + end-to-end chain (this session, NO-SPEND):
- `replay_and_regress.py --selftest`: live store → Δv=0 (no regression); corrupt Σ′ (wt1a→`ENSDARG00000054611`) → **Δv=−1.0, regression caught** (reproduces the 2026-06 corruption). PASS.
- `governance_prefilter.py --selftest`: clean Σ′ → PASS; regressive Σ′ → **FAIL pre-gate** (advisory). PASS.
- `build_regression_cases.py`: extracted **1 guard** (`regcase_wt1a_id_guard`) from `failure_log.jsonl`, self-validated against the live store; the "15-of-16" entry skipped honestly (no single symbol). 
- Chain: build guard → replay records+guards under live store = `NO_REGRESSION` → under corrupt Σ′ = `REGRESSION` (via the **real** guard) → `governance_prefilter` on a real queued proposal under corrupt Σ′ = `FAIL`.
- **Closing composite-auditor (3 adversarial lenses, this session): 3/3 APPROVE (minor).** No-mutation **confirmed** (SHA256 of `verified_identifiers.json` + the `records/` ledger byte-identical before/after the full chain); human-gate-final preserved. **5 minor fixes applied:** (i) `datetime.utcnow()`→timezone-aware across the 3 tools + `compute_ece.py` (deprecation removed); (ii) `must_fail` clarified as a **corroborating** check (for the corrupt-Σ′ class the `assertions` flip alone is sufficient; `must_fail` guards output-text reintroduction of the bad ID under a *clean* store where it is NOT_FOUND) + the self-test now exercises **both** regimes; (iii) an `inconclusive_auto` bucket (an auto check that cannot produce a comparable label is surfaced for the human gate, not absorbed as no-regression); (iv) held-out status now detects **real run files** (`rglob('month_*/*.json')`), not empty placeholder dirs; (v) removed an unused `compute_ece` import in `governance_prefilter.py`.

## Substrate instrumentation (§5 / §11)

- **Claim record:** `substrate_calibration/records/claim_20260618_120000_r1-regression-loop.json` (this decision's §5 record; it carries a `replay` block — dogfooding the new field).
- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (the self-tests are deterministic, re-runnable proofs). Self-report per §5.
- **agents_invoked:** `composite-auditor` — **invoked** (Mode 1, ≥3 adversarial, closing audit, this session); `causal-pruner` — not-applicable (no ranked biological candidates); `retrospector` — the new guards + Δv reports are RIL telemetry it will read.
