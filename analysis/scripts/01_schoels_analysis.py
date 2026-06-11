"""
01_schoels_analysis.py
Phase 1 of Option G: analyze GSE162031 (Schoels et al. 2021) — zebrafish
pronephros scRNA-seq at 3 developmental timepoints.

Goals:
  1. Load and combine the 3 day-stratified count matrices.
  2. Basic QC (cell/gene filter, count distributions).
  3. Check expression of canonical pronephros markers (Identity gate proxies).
  4. Check expression of segment-specific markers (Specificity gate proxies).
  5. Save AnnData and tables for downstream analysis.

Output: analysis/outputs/schoels_qc.h5ad and CSV tables.
"""

from pathlib import Path
import sys
import json
import pandas as pd
import numpy as np
import scanpy as sc
import anndata as ad

# Resolve marker IDs at runtime from the verified-identifier store (DATA INAMOVIBLE v1),
# never hardcoded from memory (CLAUDE.md §7, GWT v1.1 §6.3). require() raises ResolveError if a
# symbol does not resolve, so a wrong/stale ID can no longer silently enter this script.
# This replaces a block of 16 hardcoded IDs of which 15 were WRONG vs the verified map
# (only pax2a matched) under a misleading "# Ensembl release 111" comment — they produced
# 9 false-negative markers + one false-positive wt1a expression row. See
# docs/findings/2026-06-10-schoels-phase1-id-corruption.md.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.resolve_id import require  # noqa: E402

DATA_DIR = Path("analysis/data/schoels")
OUT_DIR = Path("analysis/outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Canonical pronephros markers (zebrafish) — Identity gate proxies.
# verified: 2026-06-10 source: ensembl (analysis/outputs/verified_identifiers.json via resolve_id.py)
CANONICAL_SYMBOLS = ["wt1a", "pax2a", "pax8", "hnf1ba", "hnf1bb"]

# Segment-specific markers (zebrafish) — Specificity gate proxies.
# verified: 2026-06-10 source: ensembl (analysis/outputs/verified_identifiers.json via resolve_id.py)
SEGMENT_SYMBOLS = [
    "podxl", "nphs1", "nphs2",        # podocyte
    "slc20a1a", "slc4a4a", "trpm7",   # proximal tubule (PT)
    "slc12a1", "kcnj1a.1",            # distal early (DE)
    "slc12a3",                        # distal late (DL)
    "gata3", "cdh17",                 # pronephric duct general
]

# {symbol: ENSDARG} resolved from the store; require() guarantees each ID is verified.
CANONICAL_MARKERS = {s: require(s).ensdarg for s in CANONICAL_SYMBOLS}
SEGMENT_MARKERS = {s: require(s).ensdarg for s in SEGMENT_SYMBOLS}

def log(msg):
    print(f"[schoels] {msg}", flush=True)

def load_day(day_label):
    """Load one day's CSV.gz; rows are genes, columns are cells.
    Returns scanpy-ready AnnData (cells as obs, genes as var)."""
    csv_path = DATA_DIR / f"GSE162031_raw_counts_{day_label}.csv.gz"
    log(f"Loading {csv_path}")
    df = pd.read_csv(csv_path, index_col=0, compression="gzip")
    log(f"  raw shape: genes={df.shape[0]}, cells={df.shape[1]}")
    # Build AnnData: cells x genes
    adata = ad.AnnData(
        X=df.T.values.astype(np.float32),
        obs=pd.DataFrame({"day": day_label}, index=df.columns),
        var=pd.DataFrame(index=df.index),
    )
    return adata

def report_marker(adata, name, ens_id):
    """Return per-marker stats: presence, n cells expressing, % expressing, mean."""
    if ens_id not in adata.var_names:
        # Record WHY a marker is absent so a future wrong/stale ID is visible, not silent.
        # (The prior version returned found=False with no reason, which let 15 wrong IDs pass.)
        return {
            "marker": name, "ens_id": ens_id, "found": False,
            "n_cells_expressing": 0, "pct_expressing": 0.0,
            "mean_expr": 0.0, "max_expr": 0.0,
            "reason": "id_not_in_var_names",
        }
    X = adata[:, ens_id].X
    expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
    n_pos = int((expr > 0).sum())
    return {
        "marker": name,
        "ens_id": ens_id,
        "found": True,
        "n_cells_expressing": n_pos,
        "pct_expressing": float(n_pos / len(expr) * 100),
        "mean_expr": float(expr.mean()),
        "max_expr": float(expr.max()),
        "reason": "",
    }

def report_marker_per_day(adata, name, ens_id):
    """Per-day marker expression breakdown."""
    rows = []
    for day in adata.obs["day"].unique():
        sub = adata[adata.obs["day"] == day]
        rec = report_marker(sub, name, ens_id)
        rec["day"] = day
        rec["n_cells_in_day"] = sub.n_obs
        rows.append(rec)
    return rows

def main():
    log("=== Schoels GSE162031 — Phase 1 analysis ===")

    # Load + concatenate
    adatas = [load_day(d) for d in ("day1", "day2", "day3")]
    adata = ad.concat(
        adatas, join="outer", merge="same",
        label="day_batch", keys=["day1", "day2", "day3"],
    )
    log(f"Combined: cells={adata.n_obs}, genes={adata.n_vars}")
    log(f"Cells per day: {adata.obs['day'].value_counts().to_dict()}")

    # Basic stats before filtering
    sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
    qc_pre = adata.obs[["n_genes_by_counts", "total_counts"]].describe()
    log(f"Pre-filter QC summary:\n{qc_pre}")
    qc_pre.to_csv(OUT_DIR / "schoels_qc_prefilter.csv")

    # Light filtering: drop cells with <200 genes, drop genes in <3 cells
    n_cells_before, n_genes_before = adata.shape
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)
    log(f"After filter: cells {n_cells_before} -> {adata.n_obs}, genes {n_genes_before} -> {adata.n_vars}")

    # Save raw counts before normalization
    adata.layers["counts"] = adata.X.copy()

    # Normalize + log
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Marker analyses (use log-normalized values for expression scoring)
    log("=== Canonical pronephros markers (Identity gate proxies) ===")
    canonical_rows = []
    for name, ens_id in CANONICAL_MARKERS.items():
        # Overall
        canonical_rows.append({**report_marker(adata, name, ens_id), "scope": "all"})
        # Per day
        for r in report_marker_per_day(adata, name, ens_id):
            canonical_rows.append({**r, "scope": r["day"]})
    canonical_df = pd.DataFrame(canonical_rows)
    canonical_df.to_csv(OUT_DIR / "schoels_markers_canonical.csv", index=False)
    log("Canonical markers (overall):")
    print(canonical_df[canonical_df["scope"] == "all"][
        ["marker", "found", "n_cells_expressing", "pct_expressing", "mean_expr"]
    ].to_string(index=False))

    log("=== Segment-specific markers (Specificity gate proxies) ===")
    segment_rows = []
    for name, ens_id in SEGMENT_MARKERS.items():
        segment_rows.append({**report_marker(adata, name, ens_id), "scope": "all"})
        for r in report_marker_per_day(adata, name, ens_id):
            segment_rows.append({**r, "scope": r["day"]})
    segment_df = pd.DataFrame(segment_rows)
    segment_df.to_csv(OUT_DIR / "schoels_markers_segment.csv", index=False)
    log("Segment markers (overall):")
    print(segment_df[segment_df["scope"] == "all"][
        ["marker", "found", "n_cells_expressing", "pct_expressing", "mean_expr"]
    ].to_string(index=False))

    # Save processed AnnData
    out_h5ad = OUT_DIR / "schoels_qc.h5ad"
    adata.write_h5ad(out_h5ad)
    log(f"Wrote {out_h5ad} ({out_h5ad.stat().st_size / 1024 / 1024:.1f} MB)")

    # Save run summary
    summary = {
        "n_cells_post_filter": int(adata.n_obs),
        "n_genes_post_filter": int(adata.n_vars),
        "cells_per_day": {k: int(v) for k, v in adata.obs["day"].value_counts().to_dict().items()},
        "median_genes_per_cell": int(adata.obs["n_genes_by_counts"].median()),
        "median_total_counts_per_cell": int(adata.obs["total_counts"].median()),
        "canonical_markers_found": int(canonical_df[canonical_df["scope"] == "all"]["found"].sum()),
        "canonical_markers_total": len(CANONICAL_MARKERS),
        "segment_markers_found": int(segment_df[segment_df["scope"] == "all"]["found"].sum()),
        "segment_markers_total": len(SEGMENT_MARKERS),
    }
    with open(OUT_DIR / "schoels_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log(f"Run summary:\n{json.dumps(summary, indent=2)}")

    log("=== Phase 1 complete ===")

if __name__ == "__main__":
    sys.exit(main() or 0)
