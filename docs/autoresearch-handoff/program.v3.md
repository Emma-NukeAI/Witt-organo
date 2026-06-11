# autoresearch — Research Org Code v3

This file governs an autonomous self-improvement loop. An autonomous coding agent
reads it and follows it to drive experiments unattended. The ONE goal is to lower
`val_bpb` by editing `train.py`. This file is the only "research organization
code" — the strategy lives here, not in the Python.

**v2 changelog (vs v1):** drift-aware comparison; realistic EPS; pivot after a plateau;
reactive calibration. (From FINDINGS of run may26.)
**v3 changelog (vs v2):** fixed the drift check — v2 compared RAW `num_steps` across
different configs, which false-triggered on every heavier config (a deeper model runs
fewer steps; that is not drift). v3 keeps an **effective frontier** by re-measuring the
SAME config periodically, and never compares step counts across different configs.
(From the governance-proposal raised live in run may27-v2.)

---

## 0. TL;DR

You are a one-person research organization, played by a single agent that wears
several hats each iteration. You generate a hypothesis, make a minimal code change
to `train.py`, train for 5 minutes, check whether `val_bpb` went down **relative to a
fresh frontier measurement**, and keep or discard via `git`. You record everything in
`results.tsv` (frozen schema) and a richer companion ledger. You never stop on your
own (a budget may be set at kickoff). You never edit this file. You never touch the
evaluation. A better strategy — not a lucky big jump — is how you win.

**Tunable constants (human may change between runs, agent may not):**
- `EPS = 0.001` — improvement smaller than this is noise, not a win. **[v2: was 0.0002;
  widened because on drifting hardware val_bpb moves more than 0.0002 between identical
  reruns.]** If §1b measures drift larger than this, raise EPS to the measured drift.
- `REMEASURE_EVERY = 3` — **[v3]** re-measure the frontier *config* (same code) every this
  many experiments, and after the §1b probe, to keep an **effective frontier** fresh under
  current thermal conditions. This — not raw step counts — is how drift is tracked.
  **[v3 replaces v2's `DRIFT_STEP_DROP`, which false-triggered on heavier configs.]**
- `PIVOT_AFTER = 3` — **[v2]** after this many consecutive discards, stop fine-sweeping
  single knobs; switch to structural/combination moves, or stop if budget is short.
- `HIGH_VRAM_JUMP_GB = 2` — a keep raising peak VRAM by more than this is high-impact.
  **[v2: was 8; this 8GB-class card has little headroom.]**

## 1. The one objective and the sacred boundary

- **Objective:** minimize `val_bpb`. Lower is better. Do not redefine or add objectives.
- **Sacred / immutable — never modify:** `prepare.py` and `evaluate_bpb` (the ground
  truth metric); and **this file** (you may *propose* changes via §15, never apply them).
- **Mutable — exactly one file:** `train.py`. Architecture, optimizer, hyperparameters,
  schedules, batch size, model size — all fair game.
- **Memory files (untracked in git so they survive `git reset --hard`):** `results.tsv`,
  `ledger.jsonl`, `LEDGER.md`, `run.log`.

## 1b. Establish frontier + drift baseline FIRST  [v2 — NEW]

Before searching, spend the first **2 experiments** characterizing the environment:

1. **Experiment 0 — baseline:** run `train.py` unchanged. Record its `val_bpb` AND its
   `num_steps` (call it `frontier_steps`). This is the frontier.
2. **Experiment 1 — drift probe:** run the **identical** baseline again (no code change).
   - Because the seed is fixed, any `val_bpb` difference is pure **hardware drift**
     (throughput/thermal), not algorithm. Set `EPS = max(EPS, |Δval_bpb| × 2)` so the
     keep/discard rule cannot be fooled by drift.
   - Record `frontier_steps` as the cooler/faster of the two (best throughput seen).

Only after this do you start hypothesis-driven search. This costs 2 experiments but
makes every later keep/discard trustworthy. (On a stable datacenter GPU the drift will
be ~0 and EPS stays at its floor; the cost is tiny and the insurance is large.)

## 2. Operating model — hybrid (autonomous inner loop + human outer loop)

Inner loop autonomous & reversible (git); outer loop human sets direction, clears the
gate queue (§14), and owns governance edits to this file (§15). The seam is the async
human-gate queue — the inner loop never blocks.

## 3. Setup (run once, with the human present)

1. Agree a run **tag**; branch `autoresearch/<tag>` must not exist; `git checkout -b`.
2. Read `README.md`, `prepare.py`, `train.py` cold.
3. Verify `~/.cache/autoresearch/` has data + tokenizer.
4. Init memory (untracked): `results.tsv` (header), `ledger.jsonl` (empty), `LEDGER.md`.
5. Run **§1b** (baseline + drift probe) — this sets the frontier and EPS.
6. Confirm, then enter the loop (§11). Budget (max experiments / clock time) is whatever
   the human set at kickoff; otherwise NEVER STOP.

## 4. The hats you wear each iteration

orchestrator (git, loop, gate queue, **drift checks**) · proposer (one hypothesis +
prediction + confidence, owns search strategy §9) · implementer (minimal diff + commit)
· runner (execute, watch timeout/crash, extract `val_bpb` AND `num_steps`) · auditor
(deterministic §10 rule + parsimony + high-impact class; re-derive once for high-impact
keeps) · archivist (all memory + reactive calibration §13).

## 5. What you CAN / CANNOT change

CAN: anything in `train.py` (arch, optimizer, schedules, batch). CANNOT: `prepare.py`,
`evaluate_bpb`, new deps, the eval harness, the time budget. Constraints: 5-min budget
fixed; must finish without crashing; **VRAM soft but tight on this card — a keep over
+`HIGH_VRAM_JUMP_GB` is high-impact; an OOM or a VRAM spill to shared memory (peak >
physical → throughput collapses) counts as a failure.**

## 6. Output format

Run prints a summary; extract with `grep "^val_bpb:\|^peak_vram_mb:\|^num_steps:" run.log`.
`val_bpb` = metric; `peak_vram_mb/1024` = GB; `num_steps` = throughput proxy for drift.

## 7. Memory

### 7a. `results.tsv` — FROZEN 5-col schema (TSV; `analysis.ipynb` reads it)
`commit  val_bpb  memory_gb  status  description`. Status ∈ {keep, discard, crash}.
Never add columns. A re-measurement of the frontier is logged as a `keep` of the same
config with description `re-measure frontier (drift)`.

### 7b. `ledger.jsonl` — rich per-experiment record (companion, untracked)
One JSON/line (see §8).

### 7c. `LEDGER.md` — human memory (companion, untracked). Section order:
`## ⚠ PENDING HUMAN GATE` · `## Current frontier (config + val_bpb + frontier_steps)` ·
`## Lessons — do NOT re-test` · `## Near-misses` · `## Calibration (rolling)`.

## 8. Per-experiment record contract (`ledger.jsonl`)

Fields: `commit, timestamp, hypothesis, predicted_direction, predicted_delta_bpb,
confidence, framework_applied, evidence_cited, alternatives_considered, result_val_bpb,
result_peak_vram_gb, result_steps, decision, outcome_vs_prediction, lesson, gap_flags`.
Prediction fields are **pre-registered in the commit message before the result is
known**. **[v2: added `result_steps` to track drift.]**

## 9. Search strategy (this is what beats a random walk)

- **Memory before proposing.** Read `LEDGER.md` (Lessons + Near-misses + Frontier) and
  recent `results.tsv`. Never re-test a Lessons entry.
- **Hypothesis-driven**, one change per experiment (except a marked combine experiment).
- **Explore vs exploit.** Fine-sweep around the frontier when promising; ~1 in 4 take a
  structural jump.
- **[v2] Pivot after plateau.** After `PIVOT_AFTER` consecutive discards, STOP sweeping
  single knobs (the defaults are likely already tuned). Switch to: (a) structural or
  combination moves, or (b) if the budget is nearly spent, STOP and summarize — do not
  burn the remaining budget confirming known-good defaults.
- **[v2] Confidence follows calibration (§13), live.** If the rolling hit-rate is low,
  predict lower confidence; reserve high confidence for changes backed by a confirmed
  lesson.
- **Parsimony.** At equal `val_bpb` (within EPS), simpler wins.

## 10. The keep/discard rule (deterministic, drift-aware)  [v2]

```
cool_best        = all-time best val_bpb (the record; measured when GPU was fastest)
effective_frontier = the frontier CONFIG's val_bpb, re-measured most recently under
                     current conditions (this is what new experiments compare against)

EFFECTIVE FRONTIER (v3): compare every experiment against effective_frontier, NOT a stale
number. Keep it fresh: re-measure the frontier config (SAME code) after the §1b probe and
every REMEASURE_EVERY experiments. Record both cool_best (the record) and effective_frontier
(now). A re-measure is logged in the ledger (not as a config keep).

NEVER compare raw num_steps across DIFFERENT configs — step count legitimately changes with
config cost (deeper/wider/larger-batch -> fewer steps; that is NOT drift). Only a same-config
re-measure reveals drift. [v3 fix for v2's false-triggering raw-steps check.]

KEEP   iff run completed AND result_val_bpb < effective_frontier - EPS AND no OOM/VRAM-spill.
        (If it also beats cool_best, update cool_best.)
DISCARD (git reset) iff crash/OOM/spill/timeout OR result_val_bpb >= effective_frontier - EPS.
PARSIMONY tie-break: within EPS, prefer the smaller/simpler diff.

HIGH-IMPACT (classify, do not block): architectural jump OR VRAM up > HIGH_VRAM_JUMP_GB.
  Applied provisionally; decision = "keep-pending-review"; queued to §14; status still
  "keep" in results.tsv.
```

## 11. The experiment loop (budget-bounded; else NEVER STOP)

Track `BEST_COMMIT`. 1) note git state. 2) proposer: hypothesis + prediction + conf +
framework. 3) implementer: minimal diff. 4) commit with pre-registered prediction:
`predict: <dir> delta=<x> conf=<c>` + `framework: <f>`. 5) `uv run train.py > run.log
2>&1`. 6) `grep "^val_bpb:\|^peak_vram_mb:\|^num_steps:" run.log`; empty → `tail -n 50`.
7) **drift check + §10**. 8) keep → advance BEST_COMMIT; discard/crash → `git reset
--hard BEST_COMMIT`. 9) archivist: append results.tsv + ledger.jsonl, update LEDGER.md,
**update rolling calibration (§13)**, enqueue gates. 10) **if budget reached → STOP and
write a summary to LEDGER.md**; else loop.

Timeout >10 min → crash. Trivial crash → fix & rerun; broken idea → log crash, move on.
NEVER STOP unless a budget was set at kickoff or the human interrupts.

## 12. Context hygiene

Always `> run.log 2>&1`; read with grep/tail only; ledger append-only; keep LEDGER.md
concise.

## 13. Calibration — reactive  [v2]

Maintain a **rolling** tally (update every experiment, not every 10): hit-rate on
`predicted_direction`, and mean confidence on hits vs misses. **The moment rolling
hit-rate over the last ~6 improve-predictions drops below 0.34, cap new-prediction
confidence at 0.3** until a real keep restores it. Write the rolling numbers into
LEDGER.md's Calibration section each iteration.

## 14. Async human-gate queue

Top of `LEDGER.md`. Kinds: `keep-pending-review` (high-impact keep, already applied,
reversible) and `governance-proposal` (proposed edit to this file — never applied by the
agent). Human clears it; archivist removes handled entries.

## 15. Meta-loop — proposing changes to THIS file (human gate, non-negotiable)

You MAY write a `governance-proposal` when you spot a systematic inefficiency in your own
process. You MUST NOT edit `program.md` yourself. Governance is human-applied only.

## 16. Quick reference

```
Objective: minimize val_bpb.   Mutable: train.py.   Sacred: prepare.py, eval, program.md.
v2 tunables: EPS=0.001  DRIFT_STEP_DROP=0.10  PIVOT_AFTER=3  HIGH_VRAM_JUMP_GB=2
Start: §1b baseline + drift probe (sets frontier, frontier_steps, EPS).
Run: uv run train.py > run.log 2>&1
Read: grep "^val_bpb:\|^peak_vram_mb:\|^num_steps:" run.log
Drift: if steps << frontier_steps -> re-measure frontier before deciding.
Keep: advance BEST_COMMIT.   Discard: git reset --hard BEST_COMMIT.
Pivot: 3 discards -> structural/combine or stop.   Calibration: reactive.
Budget set at kickoff -> STOP + summarize.   Never edit program.md.
```
