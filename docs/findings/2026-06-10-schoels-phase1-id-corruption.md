# Finding — `01_schoels_analysis.py` shipped 15 wrong gene IDs and corrupted its marker CSVs

- **Date:** 2026-06-10
- **Severity:** High (live CLAUDE.md §7/§10 violation that poisoned Identity/Specificity gate proxies)
- **Status:** Fixed in `feat/gwt-v1.1-cycle1` (GWT v1.1 Cycle 1, Track A)
- **Tests touched:** Test 1 (reasoning quality), Test 3 (iteration/correction is logged evidence)

## What happened

`analysis/scripts/01_schoels_analysis.py` hardcoded 16 zebrafish marker ENSDARG IDs under a
`# Ensembl IDs from Ensembl release 111` comment and a second comment promising a
"symbol fallback via gene_name lookup later". Two problems, both verified by reading the code
and its outputs:

1. **15 of the 16 IDs were WRONG** versus the verified map `analysis/outputs/ensembl_symbol_map.json`.
   Only `pax2a` matched. (`wt1a`, `pax8`, `hnf1ba`, `hnf1bb`, `podxl`, `nphs1`, `nphs2`,
   `slc20a1a`, `slc4a4a`, `trpm7`, `slc12a1`, `kcnj1a.1`, `slc12a3`, `gata3`, `cdh17` were all wrong.)
2. **The promised fallback did not exist.** `report_marker()` simply returned `found=False` when
   an ID was absent from `var_names`, with no reason recorded — so a wrong ID failed silently.

## Blast radius — the outputs were already corrupted

The script had run (outputs dated 2026-05-08). Reading `schoels_markers_canonical.csv` confirms
**two distinct corruption modes**, both dangerous because they feed the Identity gate proxy:

| marker | hardcoded ID | found | what it actually is |
|---|---|---|---|
| `pax2a` | ENSDARG00000028148 ✓ | True, 22.0% cells | the ONLY correct row |
| `wt1a` | ENSDARG00000054611 ✗ | True, **0.44%** cells | **false positive** — wrong ID collided with an unrelated gene present in `var_names`; spurious low expression attributed to "wt1a" |
| `hnf1bb` | ENSDARG00000040149 ✗ | True, **1.5%** cells | **false positive** — same mechanism |
| `pax8` | ENSDARG00000007570 ✗ | False, 0% | **false negative** — a real early-kidney marker wrongly absent |
| `hnf1ba` | ENSDARG00000016281 ✗ | False, 0% | **false negative** |

`schoels_markers_segment.csv` used 11 wrong IDs (all 11), so every segment marker is likewise
either a false negative (ID not in `var_names`) or a false positive (ID collided with an
unrelated gene). The exact per-marker breakdown is re-derivable by re-running the fixed script.

The false positives are the more insidious mode: they inject plausible-but-false expression
numbers for canonical kidney markers into a gate proxy.

**Unaffected:** `schoels_qc.h5ad` (markers are read at report time, not baked into QC) and
`02_schoels_phase2.py` / `schoels_markers_v2.csv` (Phase 2 rebuilds IDs via live Ensembl
symbol-lookup with the verified map — independent and sound).

## Fix (Cycle 1, Track A)

1. Replaced the 16 hardcoded IDs with **runtime resolution from the verified-identifier store**
   via `analysis/scripts/lib/resolve_id.require(symbol)`, which raises if a symbol is unverified.
   IDs are no longer carried from memory (CLAUDE.md §7). Verified 16/16 resolve and equal
   `ensembl_symbol_map.json`.
2. `report_marker()` now records `reason: "id_not_in_var_names"` on absence, so a future
   wrong/stale ID is visible, not silent.
3. The misleading `# Ensembl release 111` comment was removed; each marker block now carries a
   `# verified: 2026-06-10 source: ensembl (...via resolve_id.py)` tag.
4. The new deterministic gate `analysis/scripts/lib/verify_output.verify_identifiers()` FAILS on
   the exact fabrication (`wt1a == ENSDARG00000054611`), so it cannot recur in any output.

## Version preservation (ADR-0002)

The corrupted 2026-05-08 CSVs were **not overwritten**. They were moved to
`analysis/outputs/_superseded/schoels_markers_{canonical,segment}.20260508.csv`.

## Recovery — RESOLVED (2026-06-11)

The recovery ran via `analysis/scripts/01b_schoels_remarker.py`, which re-reports the markers from
the **unaffected** `schoels_qc.h5ad` (QC/normalize never depended on the marker IDs) using the
correct IDs from the verified store. Faithful to a fresh run's marker step, without re-running the
full scanpy pipeline. Result (full per-marker diff in `analysis/outputs/schoels_remarker_diff_20260611.json`):

- **now found: 15/16** (was a mix of false-positives + false-negatives).
- **10 false-negatives recovered** — real pronephros markers wrongly absent are now detected with
  substantial expression: `cdh17` 0→35.1%, `hnf1ba` 0→25.3%, `slc20a1a` 0→12.9%, `podxl` 0→12.5%,
  `pax8` 0→11.3%, `trpm7` 0→10.6%, `slc12a3` 0→9.9%, `gata3` 0→5.9%, `nphs2` 0→4.7%, `kcnj1a.1` 0→4.1%.
- **4 false-positives corrected** (expression was attributed to an unrelated gene the wrong ID hit):
  `slc4a4a` 45.5%→22.3% (a dramatic spurious value), `wt1a` 0.44%→5.23%, `nphs1` 2.28%→3.78%,
  `hnf1bb` 1.50%→0.97%.
- **1 genuinely absent**: `slc12a1` (correct ID `ENSDARG00000098096`) is not in `var_names` — now
  reported as absent **with `reason: id_not_in_var_names`** (a true technical/biological absence in
  this dataset, no longer masked by a colliding wrong ID).

The fixed `01_schoels_analysis.py` (full scanpy pipeline) regenerates the same marker CSVs on a
fresh run; `01b_schoels_remarker.py` is the lightweight recovery that produced the live corrected
CSVs now in `analysis/outputs/`. Logged as Test-3 iteration evidence: a real, audited correction
that recovered 10 markers and removed 4 spurious expression values from the Identity/Specificity
gate proxies.
