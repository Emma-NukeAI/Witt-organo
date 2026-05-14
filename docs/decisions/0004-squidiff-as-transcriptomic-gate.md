# ADR 0004 — Adopt Squidiff as the Transcriptomic Hypothesis Gate

- **Date:** 2026-05-13 (initial); 2026-05-14 (v2.0.1 determinism patch)
- **Status:** Accepted (May 13, 2026); patched May 14, 2026 (v2.0.1 determinism fix)
- **Decided by:** Emmanuel (Nuke AI), confirmed via collaboration session May 13; v2.0.1 patch decided May 14
- **Affects:** `skills/custom/squidiff-in-silico-gate/`, `agent-catalog.md`, `SIMULATION_OUTPUTS_DB/` contract, `substrate_calibration/records/` schema

## Context

Phase I needs in-silico hypothesis testing for pronephros perturbation experiments before committing wet-lab budget. The existing skill set covered:
- Morphology prediction (Morpheus 4D viz)
- Agent architecture (organogenesis-agent-architect)
- General simulation orchestration (catalog)

But did not cover transcriptomic-response prediction — a gap most visible in the 13-scenario contractility ablation experiment, where the user's gold-standard verdict ("2B-KO PASA paradigma") requires distinguishing transcriptomic identity preservation from morphological architecture decouple.

## Decision

Adopt Squidiff (He et al., *Nature Methods* 2026, doi:10.1038/s41592-025-02877-y) as the transcriptomic-prediction substrate. Implement as a custom skill (`squidiff-in-silico-gate`) with four operating modes (0 synthetic, 1 real inference, 2 fine-tune, 3 cross-verdict). The skill calls the real pip-installable Squidiff package with pretrained weights from the paper's reproducibility repo.

The skill is installed concurrently with the unified recalibration plan (May 13-14 2026 execution) and includes the Preflight & enforcement section per the recalibration's ACT-N2.1 contract from day 1.

**Patch (v2.0.1, May 14 2026):** A determinism bug was discovered in v2.0.0: the HTML output used `Math.random()` in client-side JS for synthetic data generation, causing values and cluster positions to change on every page refresh. The team noticed this within 24 hours of receiving the figure. v2.0.1 fixes:
- All scripts (`synthetic_fallback.py`, `run_inference.py`, `render_figure.py`) accept `--seed N`, default 42
- Seed propagated to `numpy`, `torch.manual_seed`, `torch.cuda.manual_seed_all`, `torch.backends.cudnn.deterministic`
- Seed recorded in metrics JSON and displayed as figure-header badge
- `references/gate-criteria.md` Section 8 (new) documents determinism as a non-negotiable requirement for HUMAN GATE figures
- The original May 13 HTML was retroactively patched (`squidiff-gate-pronephros-contractility-deterministic.html`) for the team

The patch is conceptually small (seed plumbing) but substantively important: without determinism, the figure isn't citable, isn't comparable across sessions, and undermines reviewer confidence at HUMAN GATE.

## Alternatives considered

1. **Skip transcriptomic gate, rely on wet-lab readouts only.** Rejected: defeats the substrate's purpose of generating evidence before wet experiments.
2. **Build a proxy ourselves (the v1.0 approach).** Rejected by Emmanuel May 13 in favor of using the real published model — *"lo más cercano a la realidad."*
3. **Wait for Squidiff-equivalent zebrafish model.** Rejected: no such model exists; transfer learning from iPSC is the pragmatic path.
4. **(v2.0.1 alternative considered and rejected) Leave the determinism bug as "expected behavior of synthetic mode."** Rejected because the figure had already been shared with the team and lost reviewer trust. The skill's value depends on figures being citable; without determinism the gate cannot function.

## Consequences

**Positive:**
- Closes the transcriptomic-prediction gap with the paper's actual model (not a proxy)
- Provides substrate evidence for Tests 1 and 4 (calibration via real Pearson r vs ground-truth)
- Establishes the file-based cross-skill contract pattern (`SIMULATION_OUTPUTS_DB/<id>/`) that other simulators can adopt
- Recognizes the PASS-DECOUPLE paradigm verdict as a first-class category in the gate vocabulary (paradigm aligned with ADR-0003 tripartite)
- Squidiff Mode 1/3 outputs automatically write claim records to `substrate_calibration/records/` per the Preflight & enforcement section, closing the Test 4 calibration loop
- v2.0.1: figures are deterministic, citable, replayable; same seed + same input = byte-identical output across sessions
- Squidiff complements Morpheus (the primary morphological focus of the project): transcriptomic-only verdicts are not sufficient evidence for paradigm cases, but they reinforce or contradict the morphological story. The cross-verdict pattern (Mode 3) is the operational expression of this complementarity.

**Negative / costs:**
- Adds a Python + PyTorch dependency to any environment running Mode 1+ (acceptable: setup script handles it)
- Pronephros is not in Squidiff's pretrained domain — Mode 1 uses iPSC transfer with mid-distance penalty until Mode 2 fine-tunes on POC data
- Two-skill cross-verdict requires Morpheus to emit JSON, which it currently does not (held as Phase I deferred action in the unified plan)
- The honest limit — Squidiff is transcriptomic only, not morphological — remains and cannot be closed by any version of Squidiff itself
- v2.0.1 lesson: client-side JS in figures was a determinism leak we missed in initial design. Future skills generating HTML figures must include seeded PRNG by construction.

**Discovery from v2.0.1 re-analysis of the 13-scenario contractility experiment:** When the cross-verdict logic (`pair_with_morpheus.py`) is run for real (not via the May 13 preview's hardcoded lookup table), the 13-scenario verdicts are: 5 PASS / 1 PASS-DECOUPLE / 3 SPURIOUS / 3 DIVERGENT / 1 CONTROL. This is different from the May 13 preview's 9/12 converge claim. The difference is honest — Mode 0 without real scRNA-seq cannot resolve scenarios with sustained stress and preserved identity, and correctly flags them as DIVERGENT rather than over-claiming PASS. This validates that the skill behaves correctly when invoked end-to-end. Notable: 1B-KO appeared as FAIL in the May 13 preview (hardcoded `identity == "caotico" → FAIL`), but the real Mode 3 flags it as SPURIOUS because Mode 0 without real data cannot distinguish transcriptomic collapse from preserved-identity-with-stress. Resolution to confident verdict requires Mode 1 with scRNA-seq.

**Out of scope for this ADR:**
- Mode 2 fine-tuning execution. Decision deferred (see unified plan Phase J / Q5). User directive 2026-05-14: no Runpod spending; if fine-tuning desired, use Web Research + Tool Universe with public data only.
- Updating Morpheus to emit JSON. Deferred to Phase I HOLD pending user approval.

## Evidence

- He et al., *Nature Methods* 2026, doi:10.1038/s41592-025-02877-y
- Squidiff GitHub: github.com/siyuh/Squidiff
- Reproducibility repo: github.com/siyuh/Squidiff_reproducibility
- Skill bundle: `skills/custom/squidiff-in-silico-gate/` (v2.0.1)
- Unified execution plan (`EXECUTION-PLAN-v1.1.md`), Phase B
- v2.0.1 13-scenario re-analysis: `squidiff-gate-13scenarios-v2.0.1.html` (shared with team May 14, not committed to repo)
