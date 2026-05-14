# Morpheus Pairing — Cross-Verdict Protocol

This file specifies the contract by which `squidiff-in-silico-gate` consumes output from `morpheus-4d-viz` to produce consolidated verdicts. The contract is file-based — no direct skill-to-skill coupling — so either skill can change implementation without breaking the other.

## Why a File-Based Contract

Two reasons:

1. **Skill independence.** Morpheus produces morphological visualizations (3D tissue shape over time). Squidiff produces transcriptomic verdicts. They are different things. Coupling them via runtime imports would make either skill harder to evolve.

2. **Substrate integrity.** Witt's SIMULATION OUTPUTS DB is the shared substrate where every simulator dumps its evidence. Going through the DB means every cross-verdict is logged, replayable, and auditable — exactly what Test 4 (calibration tracking) needs.

## The Shared Path Convention

```
SIMULATION_OUTPUTS_DB/<hypothesis_id>/
├── morpheus.json          # Morpheus verdict + summary metrics
├── morpheus.html          # The 3D visualization
├── squidiff_metrics.json  # Squidiff raw metrics (from run_inference.py)
├── squidiff.html          # The transcriptomic figure
└── cross_verdict.json     # Consolidated verdict (from pair_with_morpheus.py)
```

The `hypothesis_id` is a short slug the user (or the orchestrator) assigns at hypothesis creation. Example: `pronephros_2BKO_paradigm`, `bvo_radiation_g_csf`, `ipsc_endoderm_day3`.

If the user doesn't have a working `hypothesis_id` convention yet, the skill auto-generates one from the hypothesis text plus a timestamp.

## Morpheus Output JSON Schema

Squidiff expects to find a `morpheus.json` adjacent to its own outputs with this minimum schema:

```json
{
  "hypothesis_id": "pronephros_2BKO_paradigm",
  "scenario_label": "2B-KO",
  "phenotype_severity": "extreme|moderate|mild|baseline",
  "phenotype_class": "swiss_cheese|catastrophic|dislocated|asymmetric|compressed|preserved_foci|normal|...",
  "morphology_decouple": "pass|partial|fail|pass-paradigm|na",
  "confidence": 0.75,
  "notes": "Free-text rationale, optional",
  "morpheus_version": "1.x"
}
```

Required fields: `hypothesis_id`, `phenotype_severity`, `morphology_decouple`, `confidence`.

Optional fields: `phenotype_class` (used by the spurious-convergence detector), `notes`, `morpheus_version`.

**If the Morpheus skill is not yet emitting this JSON**, the user (or the orchestrator) can write it by hand based on the Morpheus visualization. This is a 2-minute task per scenario and serves as the immediate bridge until the Morpheus skill is updated.

## Cross-Verdict Computation

The aggregator (`scripts/pair_with_morpheus.py`) implements four cases:

### Case 1 — Reinforcing convergence

Both gates agree directionally.

| Squidiff | Morpheus | Cross-verdict | Confidence |
|---|---|---|---|
| PASS | pass | PASS | max(s,m) × 1.15 |
| FAIL | fail | FAIL | max(s,m) × 1.10 |
| MODERATE | partial | MODERATE | max(s,m) × 1.05 |

### Case 2 — Paradigm case (PASS-DECOUPLE)

| Squidiff | Morpheus | Cross-verdict |
|---|---|---|
| PASS or MODERATE | pass-paradigm | PASS-DECOUPLE |

This is the user's 2B-KO. Identity preserved, architecture decoupled, paradigm-testing.

### Case 3 — Spurious convergence

| Squidiff | Morpheus | Cross-verdict |
|---|---|---|
| PASS | extreme severity + Swiss-cheese-like class | TRANSCRIPTOMIC-ONLY PASS (downgraded) |

The flag is visible. Confidence × 0.5. Recommended action: trust morphology over transcriptomics for this hypothesis.

### Case 4 — Genuine divergence

| Squidiff | Morpheus | Cross-verdict |
|---|---|---|
| PASS | fail | DIVERGENT |
| FAIL | pass | DIVERGENT |

Manual review required. Domain expert resolves. Confidence × 0.7.

## Standalone Squidiff (No Morpheus Available)

When `morpheus.json` is not at the expected path, the skill:

1. Emits Mode 1 verdict as usual
2. Labels the verdict as `TRANSCRIPTOMIC-ONLY <verdict>`
3. Discounts confidence × 0.85
4. In the recommended-next-step, says: "Morphology not evaluated. Pair with Morpheus or wet experiment if hypothesis depends on tissue architecture."

This is the right default — better honest about what wasn't checked than pretending the check happened.

## Updating Morpheus to Emit JSON

The current `morpheus-4d-viz` skill produces HTML only. To enable cross-verdict, the Morpheus skill should be updated to also write a `morpheus.json` alongside its HTML. The patch is minimal:

```javascript
// At the end of morpheus' figure-generation pipeline
const summary = {
  hypothesis_id: hypothesisId,
  scenario_label: currentScenario.label,
  phenotype_severity: assessSeverity(currentScenario),
  phenotype_class: currentScenario.pheno_class || "unknown",
  morphology_decouple: currentScenario.decouple || "na",
  confidence: currentScenario.confidence || 0.5,
  notes: currentScenario.pheno || "",
  morpheus_version: "1.0"
};
// Write to /mnt/user-data/outputs/morpheus_<hypothesis_id>.json
```

The user's existing experiment HTML (`visualizacion-cascada-pronefro-v2.html`) already has 80% of these fields per scenario in its `SCENARIOS` object. Conversion is mechanical — the existing `confidence`, `decouple`, `pheno` fields map directly.

This is **out of scope** for the Squidiff skill but recommended as a 30-minute patch to Morpheus when the user is ready.

## Worked Example — User's 13-Scenario Experiment

The user's contractility experiment has 13 scenarios. Each has values for `confidence`, `decouple`, `tx.identity`, `tx.stress`, `tx.yap` already. To run cross-verdict for the full set:

```bash
# Per scenario:
HYPOTHESIS_ID=pronephros_2BKO
mkdir -p SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/

# 1. Generate the Morpheus JSON (from the existing experiment data)
cat > SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/morpheus.json <<EOF
{
  "hypothesis_id": "$HYPOTHESIS_ID",
  "scenario_label": "2B-KO",
  "phenotype_severity": "extreme",
  "phenotype_class": "preserved_foci",
  "morphology_decouple": "pass-paradigm",
  "confidence": 0.58,
  "notes": "Sin túbulo · foci dispersos wt1a+ · identidad preservada"
}
EOF

# 2. Run Squidiff on the relevant data (Mode 1 if data exists, Mode 0 if not)
python scripts/run_inference.py \
    --data data.h5ad --operation addition \
    --source-label control --target-label 2B-KO --label-col scenario \
    --system pronephros --hypothesis "Contractility KO at stage 2 persistent" \
    --out SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/squidiff_metrics.json

# 3. Consolidate
python scripts/pair_with_morpheus.py \
    --squidiff SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/squidiff_metrics.json \
    --morpheus SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/morpheus.json \
    --out SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/cross_verdict.json

# 4. Render the figure
python scripts/render_figure.py \
    --metrics SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/squidiff_metrics.json \
    --cross-verdict SIMULATION_OUTPUTS_DB/$HYPOTHESIS_ID/cross_verdict.json \
    --out /mnt/user-data/outputs/squidiff-gate-$HYPOTHESIS_ID.html
```

For the user's 13 scenarios, this loop runs 12 times (skip control). The output is 12 cross-verdicts logged to `SIMULATION_OUTPUTS_DB`, ready for the human gate review.
