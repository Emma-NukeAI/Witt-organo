# ADR-0026 — Unified World-State-Transition claim contract (do-typed) + explicit Tool Universe Path-B directive (R4)

- **Status:** Accepted (Emmanuel, 2026-06-18) — plan approved this session; R4 built + verified offline + composite-audited at close.
- **Relates:** ADR-0022 (answer pipeline / Path B / self-reinforcing loop), ADR-0003 (decouple paradigm — the failure predicate F as a boolean over readouts), ADR-0011/0014 (calibration / outcome vocabulary), ADR-0023/0024/0025 (R1–R3). CLAUDE.md §5/§7.
- **Affects:** the claim contract + simulators (`causal-ablation-cascade-sim`, `squidiff-in-silico-gate`); `analysis/scripts/lib/answer_pipeline.py`; Test 4 (calibration) + biological gates Induction/Specificity; Pillar 4 (fetch). Phase I. Additive — read-and-report / code-only; no DI mutation.

## Context

§3.1 #2: the **World-State-Transition Schema** — a claim as a typed tuple `⟨S, do(a), Δŝ, W, F⟩` — was present but **dispersed**: the cascade-sim's `⟨Mode A/B × hipo/KO, predicted transition, decouple-test⟩`, squidiff's source→target verdict, and the claim-record's `expected_outcome_if_h1/h0 + observable_at + observed_outcome`. Two things were missing: (1) a **single typed object** unifying the five fields, and (2) the **interventional typing** — the intervention slot was never typed as Pearl's `do(a)` vs conditioning, even though `P(S'|do(a)) ≠ P(S'|a)` in general is exactly what excludes confounders from an Induction/Specificity *causal* claim.

Separately (Pillar 4 / ADR-0022), the Path-B **Tool Universe** step was a silent stub (`_search_tooluniverse` returned `[]`) — the one loop item never wired/verified live.

## Decision

Two reuse-first, read-and-report additions (zero DI mutation):

1. **`substrate_calibration/tools/world_state.py` — the unified WSTS contract.**
   - `validate_wsts(block)` → well-formedness of `⟨S, do(a), Δŝ, W, F⟩` **plus Pearl-typing**: returns `causal_admissible = True` only when the intervention is `do`-typed. An `observe`-typed tuple is valid as a *description* but flagged **not causal-admissible** (conditioning ≠ causation) — the formal device that stops an association from masquerading as an Induction/Specificity claim.
   - `wsts_from_claim(record)` → **projects** an existing claim record's dispersed fields into the WSTS view (no mutation; inferred fields tagged) — demonstrating the unification over the immutable records (ADR-0002).
   - `calibration_datum(record)` → the **native Test-4 datum** a WSTS claim emits — `(stated_confidence, observed_label)` via `compute_ece.outcome_to_label`.

2. **`answer_pipeline.tool_universe_directive()` + threading.** When Path B triggers, the bundle now carries an explicit `tool_universe_directive` (the exact MCP tools to run — `PubMed_search_articles` / `EuropePMC_search` / `tooluniverse-literature-deep-research` — + merge-back through the **same** composite-auditor gate, ADR-0022), and the `required_next_action` instructs the agent to run it. Tool Universe is now **NAMED + actionable**, not silently dropped.

## Alternatives considered

- **Mutate claim records to carry the WSTS block.** Rejected — records are immutable (ADR-0002); project non-destructively via `wsts_from_claim` instead. New records may carry an explicit `world_state_transition` block going forward.
- **Make `_search_tooluniverse` call the Tool Universe Python SDK.** Rejected — the SDK is absent in `.venv` and the project reaches Tool Universe via the **MCP** (per-session), not the SDK. The honest wiring is the agent-run **directive**, not a fake SDK branch.
- **Heavy world-model / learned encoder for S.** Out of scope (that is MITAD_B / generation). R4 is the typed contract + the do-operator discipline.

## Consequences

- **Every claim is projectable to a do-typed WSTS that natively emits a Test-4 datum** — calibration data falls out of the claim structure with no extra bookkeeping.
- **"Association ≠ causation" is enforceable** for Induction/Specificity: a WSTS claim must name a `do(a)`; an `observe`-typed claim is flagged non-causal-admissible.
- **Tool Universe Path B is explicit + audited** — the pipeline names the MCP query; the agent runs it; results route through the same ≥3 composite-auditor gate before any answer/propose.
- **Honest limits (gap_flags):** `wsts_from_claim` infers the do/observe typing heuristically from `claim_text` (tagged inferred); the Tool Universe directive is **NOT live-verified this session** (the MCP is not connected — the known open POC item, per `docs/HANDOFF.md`); making `causal-ablation-cascade-sim`/`squidiff-in-silico-gate` EMIT the `world_state_transition` block natively is a forward doc step (the projector already maps their outputs).

## Verification

Offline (NO-SPEND): `world_state --selftest` — do-typed validates + is causal-admissible; observe-typed is valid-but-not-causal-admissible; malformed fails; the real `claim_20260514_143000` minimal-set claim projects to a `do`-WSTS (causal-admissible); a resolved claim emits `(0.95, 1.0)` as its native calibration datum. `tool_universe_directive()` emits the explicit MCP query; `answer_pipeline.py` + `world_state.py` compile clean. The directive's live execution is deferred to the MCP-connected agent context (not run here).

**Closing composite-auditor (3 adversarial lenses, this session): REVISE (major) → addressed + re-verified.** The audit confirmed the do-typing theorem (`causal_admissible` gated on `do`-typing, never on confidence), no-mutation, and no-MITAD_B-leak — but flagged two real defects my `PYTHONIOENCODING=utf-8` runs had masked: (1) `validate_wsts` crashed (AttributeError) on a **non-dict `intervention`**; (2) the self-test raised **`UnicodeEncodeError` under the default Windows cp1252 console** (the unqualified "PASS" was conditional on the env var). **Both FIXED:** `is_interventional`/`validate_wsts` now guard a non-dict intervention (reject, not crash; new self-test edge case) + `wsts_from_claim` prefers an explicit `world_state_transition` block over keyword inference; and `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` was added at the CLI entry of `world_state.py` **and the other four R-tools** (`replay_and_regress`, `governance_prefilter`, `build_regression_cases`, `accountability_checks`) matching the existing `answer_pipeline.py:194` pattern — the cp1252 gap was **systemic** (latent in the R1/R3 tools too), now closed. **Re-verified under forced `PYTHONIOENCODING=cp1252`: all 5 self-tests exit 0 (no UnicodeEncodeError); the non-dict edge case returns `valid=False`/`causal_admissible=False` without crashing.** Non-ASCII glyphs in returned/printed strings de-risked (`≠`→`!=`).

## Substrate instrumentation (§5 / §11)

- **Claim record:** `substrate_calibration/records/claim_20260618_180000_r4-wsts-tooluniverse.json`.
- **framework_applied:** Logic-LM (Symbolic Verification) — per `reasoning-frameworks-catalog.md §5`: *"Problems where the answer must be provably correct, not just plausible"* (the WSTS validator + do-typing is a deterministic predicate; the self-test is a re-runnable proof). Self-report per §5.
- **agents_invoked:** `composite-auditor` — invoked (closing audit); `causal-pruner` — not-applicable.
