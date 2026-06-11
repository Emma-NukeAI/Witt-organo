# RIL_PROGRAM.md — Reasoning-Improvement Loop charter (GWT v1.1)

> **What this is.** The canonical, in-repo "research-org code" for the substrate's reasoning loop —
> the witt-native port of autoresearch's `program.md` v3 (see `docs/autoresearch-handoff/program.v3.md`).
> Every agent and the `retrospector` read this charter. It defines the sacred metrics, the noise
> discipline (EPS), the keep/discard rule, the reactive auto-cap, the honesty clause, PIVOT_AFTER,
> and the human-gated meta-loop. It is **accessible and evolving**: this file improves only via a
> governance-proposal + human gate (§7 below) — its own §15-analog applied to itself.
>
> **Status:** v1.1 Cycle 3. The reactive auto-cap + the retrospector are now defined; the noise-probe
> 3-axis (Cycle 2) activates fully once a retrieval/RAG backend exists.

---

## 1. The two cadences (what the loop *is*)

- **Online (within a run, free):** after each substrate-instrumented output, `calibration-tracker`
  updates a rolling K=6 hit-rate; if it falls below the stream threshold, subsequent confidences are
  **auto-capped** (§4). This is the always-on safety floor.
- **Offline (between runs, default):** the `retrospector` reads the case ledger + calibration stream +
  EPS, scores the reasoning trace against the rubric (§5), writes a self-critique record, and
  regenerates `retrospectives/next_session_prepend.md` — mechanically prepended to the next similar
  task. The session **writes** governance-proposals; it **never** self-applies them (§7).

The user's ask ("improves each run OR is analyzable post-run") is satisfied by BOTH: the cheap offline
retrospective is the default; the online auto-cap is the floor.

## 2. Sacred metrics (per stream)

The substrate has two outcome streams (kept separate; never pooled into one ECE):

| Stream | `outcome_horizon` | Proxy | Sacred metric | Cadence |
|---|---|---|---|---|
| **fast** | `fast` | Proxy-2 (expert rating @ ~T+48h) + Proxy-0/1 (citation/consistency) | rolling K=6 hit-rate + ECE per sub-domain | per output |
| **slow** | `slow` | Proxy-3 (wet-lab outcome, months later) | retro-corrected ECE | per wet-lab result |

`compute_ece.py` decomposes by `claim_category`, `skill_origin`, and `sub_domain`; isotonic fit
activates per sub-domain at n≥10 (structure exists from day 1, fit gated). ADR-0005 language:
"satisfied" only at n≥10 with a computed aggregate; otherwise "case capture" / "infrastructure populated".

## 3. Noise discipline — EPS (closes C.20)

Nothing is counted as a result until it clears the measured noise floor.

- **`EPS_delta = 2σ`** — one-sided signal-detection threshold ("is this delta real, or drift?").
- **`EPS_pass = p25`** — percentile pass/fail threshold on bounded [0,1] metrics (replaces the
  "70% arbitrary" composite-auditor agreement threshold).

EPS is **measured**, not assumed: the noise-probe (Cycle 2, `tools/noise_probe.py`) runs the held-out
set twice identically (temp>0) on three axes — Retrieval Jaccard, Citation overlap, Hypothesis cosine —
and records median + σ per axis. Until a retrieval backend exists, the probe runs on the deterministic
axes available and the cosine axis is scaffolded.

## 4. Reactive calibration — rolling K=6 + per-stream auto-cap (ADR-0012/0014)

State lives in `retrospectives/rolling_calibration.json`, updated **per output** (not batched), over
the last K=6 RESOLVED predictions. When the high-confidence (≥0.70) hit-rate drops below the stream
threshold, `reasoning-exposer` clamps any new `stated_confidence` to the stream's cap until a real
correct high-confidence prediction restores the window.

**Per-stream regime (decided by Emmanuel, GWT v1.1):**

| Stream / claim type | Trigger (rolling K=6 high-conf hit-rate) | Cap |
|---|---|---|
| `extraction` / toy / deterministic | hit-rate < **0.34** | clamp to **0.30** (autoresearch parity, program.v3 §13) |
| biomedical hypotheses (`ranking`, `generation`, signaling/morphogenesis/single-cell sub-domains) | hit-rate < **0.60** | clamp to **max(declared, 0.60)** (INTEGRATION §5.4) |

The stream is selected by `claim_category` + `sub_domain`. This is self-criticism made mechanical:
the stream that was overconfident last window is structurally forced to hedge this window.

## 5. The rubric — what "good reasoning" means (guide §4)

`retrospector` scores each reasoning trace 0–1 on the `research-hypothesis-generation-guide` §4 rubric:
**Factuality, Citation correctness, Completeness, Novelty, Testability, Uncertainty (no overclaiming),
Safety/ethics**. The gate passes when the load-bearing axes clear threshold (Cycle-1 default 0.6;
Novelty is exempt for corrections). The rubric maps to governance triggers (Citation↔citation-drift,
Completeness↔domain-recall-drop, Uncertainty↔auto-cap, Safety↔§7 hard rules).

## 6. Honesty clause — pre-registered confidence

Every prediction records `prediction_preregistered_at` (≤ `observed_at`) and, where possible,
`prediction_commit` (the git SHA that first wrote the record with `observed_outcome: null`). Confidence
cannot be rationalized after the outcome is known. `stated_confidence`, `prior`, and `framework_applied`
are never modified post-hoc (substrate_calibration/README.md). Generator ≠ rater where feasible
(`rater_id`).

## 7. PIVOT_AFTER + the governance meta-loop (human-gated, non-negotiable)

- **PIVOT_AFTER:** after **3 consecutive discards** (outputs failing the keep rule `improvement >
  effective_frontier − EPS_delta`), stop fine-sweeping one knob; pivot to a structural/combination move
  or stop. `program-manager` owns the trigger and raises a governance-proposal.
- **Governance meta-loop:** any agent MAY write a `governance-proposal` to
  `retrospectives/governance_queue.jsonl` when it detects a systematic inefficiency. It **MUST NOT**
  self-apply it (`self_applied: false` is an invariant; `true` is rejected and logged as a violation).
  A human (Martín / Emmanuel, via `program-manager`) approves; an approved proposal that changes agent
  design requires an ADR. **This charter evolves the same way** — propose, human-approve, version-bump.
  This is the autoresearch v2→v3 transition made continuous.

The four pre-approved templates: `domain-recall-drop`, `contradiction-section-empty`,
`citation-coverage-drift`, `sub-domain-calibration-divergence` (see SKILL.md meta-loop section, PR-11).

## 8. What counts as improvement vs noise

- **Improvement (counted):** a delta that (a) followed a same-config effective-frontier re-measure
  within `REMEASURE_EVERY` outputs AND (b) exceeds `EPS_delta` on the relevant axis.
- **Noise (NOT counted):** a delta below `EPS_delta`, or one without a same-config re-measure → logged
  as `drift_suspected`, never as `improvement`. Provider/corpus drift is not substrate learning.

## 9. Versioning

This charter is versioned with the bundle (GWT v1.1). Changes are append-only history via ADR +
governance-proposal. Current: **v1.1** (Cycle 3 — reactive auto-cap per-stream + retrospector defined;
noise-probe 3-axis activates with the RAG backend).
