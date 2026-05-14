"""
02_schoels_phase2.py
Fase 2 de Opción G:
  (1) Refresh symbol→ENSDARG via Ensembl REST API.
  (2) Re-score canonical + segment markers with corrected IDs.
  (3) HVG + PCA + neighbors + Leiden + UMAP.
  (4) DE per cluster (rank_genes_groups) + DE per day.
  (5) Cross-reference: top DE genes per cluster vs known segment markers
      to data-drive segment annotation of clusters.
  (6) Save figures + tables.

Reads:  analysis/outputs/schoels_qc.h5ad (from script 01)
Writes: analysis/outputs/schoels_markers_v2.csv
        analysis/outputs/schoels_clustered.h5ad
        analysis/outputs/schoels_DE_per_cluster.json
        analysis/outputs/schoels_DE_per_day.json
        analysis/outputs/schoels_segment_annotation.json
        analysis/outputs/figures/umap_*.png
"""

from pathlib import Path
import json
import sys
import time
import urllib.request
import urllib.error

import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_DIR = Path("analysis/outputs")
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
sc.settings.figdir = FIG_DIR
sc.settings.verbosity = 1

# All markers we care about for the user's question
# (Identity + Specificity gates of Organogenesis POC)
MARKERS_BY_GROUP = {
    "canonical_identity": ["wt1a", "wt1b", "pax2a", "pax8", "hnf1ba", "hnf1bb", "lhx1a"],
    "podocyte":           ["podxl", "nphs1", "nphs2", "mafba"],
    "proximal_tubule":    ["slc20a1a", "slc4a4a", "trpm7", "slc13a3", "slc13a1"],
    "distal_early":       ["slc12a1", "kcnj1a.1", "slc12a1a"],
    "distal_late":        ["slc12a3", "clcnkb"],
    "duct_general":       ["gata3", "cdh17", "atp1a1a.2", "atp1b1b"],
    "intermediate_meso":  ["emx1", "irx3b", "sim1a", "tbx2b"],
    "transcription_factor_panel": ["mecom", "foxc1a", "pou3f3a", "tbx2b", "gata3"],
}

ALL_SYMBOLS = sorted({s for v in MARKERS_BY_GROUP.values() for s in v})


def log(msg):
    print(f"[phase2] {msg}", flush=True)


def query_ensembl(symbol: str) -> str | None:
    """Look up ENSDARG ID for a zebrafish gene symbol via Ensembl REST.
    Returns None if not found."""
    url = f"https://rest.ensembl.org/lookup/symbol/danio_rerio/{symbol}?content-type=application/json"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("id")
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        raise


def build_marker_map():
    cache_file = OUT_DIR / "ensembl_symbol_map.json"
    if cache_file.exists():
        log(f"Using cached symbol map at {cache_file}")
        return json.loads(cache_file.read_text())
    log(f"Querying Ensembl REST for {len(ALL_SYMBOLS)} symbols...")
    mapping = {}
    for sym in ALL_SYMBOLS:
        ens = query_ensembl(sym)
        mapping[sym] = ens
        log(f"  {sym}: {ens or '(not found)'}")
        time.sleep(0.1)  # be polite
    cache_file.write_text(json.dumps(mapping, indent=2))
    return mapping


def score_marker(adata, ens_id):
    if not ens_id or ens_id not in adata.var_names:
        return None
    X = adata[:, ens_id].X
    expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
    n_pos = int((expr > 0).sum())
    return {
        "n_cells_expressing": n_pos,
        "pct_expressing": float(n_pos / len(expr) * 100),
        "mean_expr": float(expr.mean()),
        "max_expr": float(expr.max()),
    }


def main():
    log("=== Fase 2 ===")

    # 1. Marker mapping
    sym_map = build_marker_map()
    found_count = sum(1 for v in sym_map.values() if v)
    log(f"Resolved {found_count}/{len(sym_map)} symbols")

    # 2. Load h5ad from Phase 1
    adata = sc.read_h5ad(OUT_DIR / "schoels_qc.h5ad")
    log(f"Loaded: cells={adata.n_obs}, genes={adata.n_vars}")

    # 3. Re-score markers with updated mapping
    rows = []
    for group, syms in MARKERS_BY_GROUP.items():
        for sym in syms:
            ens = sym_map.get(sym)
            scores = score_marker(adata, ens) or {
                "n_cells_expressing": 0, "pct_expressing": 0.0,
                "mean_expr": 0.0, "max_expr": 0.0,
            }
            in_dataset = bool(ens and ens in adata.var_names)
            rows.append({
                "group": group, "symbol": sym, "ens_id": ens,
                "in_dataset": in_dataset, **scores,
            })
            # Per-day
            if in_dataset:
                for day in adata.obs["day"].unique():
                    sub = adata[adata.obs["day"] == day]
                    s = score_marker(sub, ens)
                    rows.append({
                        "group": group + f"::{day}", "symbol": sym, "ens_id": ens,
                        "in_dataset": True, **s,
                    })
    markers_df = pd.DataFrame(rows)
    markers_df.to_csv(OUT_DIR / "schoels_markers_v2.csv", index=False)

    log("\n=== Marker presence (overall) ===")
    overall = markers_df[~markers_df["group"].str.contains("::")]
    print(overall[["group", "symbol", "in_dataset", "pct_expressing", "n_cells_expressing"]].to_string(index=False))

    # 4. HVG + PCA + neighbors + Leiden + UMAP
    log("\nHVG selection...")
    sc.pp.highly_variable_genes(adata, n_top_genes=2000, flavor="seurat", min_disp=0.5)
    n_hvg = int(adata.var["highly_variable"].sum())
    log(f"  HVG: {n_hvg}")

    log("PCA...")
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=50, mask_var="highly_variable")

    log("Neighbors + Leiden + UMAP...")
    sc.pp.neighbors(adata, n_neighbors=15, n_pcs=30)
    sc.tl.leiden(adata, resolution=0.5, flavor="igraph", n_iterations=2, directed=False)
    sc.tl.umap(adata)

    n_clusters = adata.obs["leiden"].nunique()
    sizes = adata.obs["leiden"].value_counts().sort_index().to_dict()
    log(f"  {n_clusters} clusters: {sizes}")

    # 5. DE per cluster
    log("\nDE per cluster...")
    sc.tl.rank_genes_groups(adata, "leiden", method="wilcoxon", n_genes=100)
    de_per_cluster = {}
    for cluster in sorted(adata.obs["leiden"].unique()):
        names = adata.uns["rank_genes_groups"]["names"][cluster]
        scores = adata.uns["rank_genes_groups"]["scores"][cluster]
        pvals_adj = adata.uns["rank_genes_groups"]["pvals_adj"][cluster]
        de_per_cluster[cluster] = [
            {"ens": str(n), "score": float(s), "padj": float(p)}
            for n, s, p in zip(names[:30], scores[:30], pvals_adj[:30])
        ]
    with open(OUT_DIR / "schoels_DE_per_cluster.json", "w") as f:
        json.dump(de_per_cluster, f, indent=2)

    # 6. DE per day
    log("DE per day...")
    sc.tl.rank_genes_groups(adata, "day", method="wilcoxon", n_genes=100, key_added="rank_genes_day")
    de_per_day = {}
    for day in sorted(adata.obs["day"].unique()):
        names = adata.uns["rank_genes_day"]["names"][day]
        scores = adata.uns["rank_genes_day"]["scores"][day]
        pvals_adj = adata.uns["rank_genes_day"]["pvals_adj"][day]
        de_per_day[day] = [
            {"ens": str(n), "score": float(s), "padj": float(p)}
            for n, s, p in zip(names[:30], scores[:30], pvals_adj[:30])
        ]
    with open(OUT_DIR / "schoels_DE_per_day.json", "w") as f:
        json.dump(de_per_day, f, indent=2)

    # 7. Cross-reference: which clusters express which segment markers?
    # For each cluster, check the % expressing for each marker group's symbols.
    log("\nSegment annotation by cluster...")
    seg_annotation = {}
    for cluster in sorted(adata.obs["leiden"].unique()):
        sub = adata[adata.obs["leiden"] == cluster]
        cluster_scores = {"n_cells": int(sub.n_obs)}
        for group, syms in MARKERS_BY_GROUP.items():
            group_pcts = []
            for sym in syms:
                ens = sym_map.get(sym)
                if ens and ens in sub.var_names:
                    s = score_marker(sub, ens)
                    if s:
                        group_pcts.append((sym, s["pct_expressing"]))
            cluster_scores[group] = group_pcts
        seg_annotation[cluster] = cluster_scores
    with open(OUT_DIR / "schoels_segment_annotation.json", "w") as f:
        json.dump(seg_annotation, f, indent=2)

    # Summary table: top group per cluster
    log("\n=== Cluster annotation by segment markers ===")
    print(f"{'cluster':>7} {'n':>4}  top group (avg %)")
    for cluster in sorted(adata.obs["leiden"].unique()):
        sub = seg_annotation[cluster]
        n = sub["n_cells"]
        # Compute avg pct per group (only over symbols actually in dataset)
        group_avgs = {}
        for group in MARKERS_BY_GROUP:
            pcts = [p for _, p in sub[group]]
            if pcts:
                group_avgs[group] = float(np.mean(pcts))
        if group_avgs:
            top = sorted(group_avgs.items(), key=lambda x: -x[1])[:3]
            top_str = ", ".join(f"{g}={p:.0f}%" for g, p in top)
        else:
            top_str = "(no markers in dataset)"
        print(f"{cluster:>7} {n:>4}  {top_str}")

    # 8. Save final h5ad + figures
    adata.write_h5ad(OUT_DIR / "schoels_clustered.h5ad")

    log("\nGenerating figures...")
    sc.pl.umap(adata, color="leiden", legend_loc="on data",
               title="Schoels GSE162031 — Leiden clusters",
               save="_schoels_leiden.png", show=False)
    sc.pl.umap(adata, color="day",
               title="Schoels GSE162031 — Developmental day",
               save="_schoels_day.png", show=False)

    # Marker overlay on UMAP (only for markers actually in dataset)
    found_markers = []
    found_labels = []
    for group, syms in MARKERS_BY_GROUP.items():
        for sym in syms:
            ens = sym_map.get(sym)
            if ens and ens in adata.var_names:
                found_markers.append(ens)
                found_labels.append(sym)
    if found_markers:
        # Display first 12 to keep figure size reasonable
        sc.pl.umap(adata, color=found_markers[:12],
                   title=found_labels[:12],
                   save="_schoels_markers_top12.png", show=False, ncols=4)

    # Run summary
    summary = {
        "phase": 2,
        "markers_resolved": int(found_count),
        "markers_attempted": len(sym_map),
        "n_cells_post_filter": int(adata.n_obs),
        "n_genes_post_filter": int(adata.n_vars),
        "n_hvg": n_hvg,
        "n_clusters": n_clusters,
        "cluster_sizes": sizes,
        "cells_per_day": {k: int(v) for k, v in adata.obs["day"].value_counts().to_dict().items()},
    }
    with open(OUT_DIR / "schoels_phase2_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log(f"\nSummary:\n{json.dumps(summary, indent=2)}")
    log("=== Fase 2 done ===")


if __name__ == "__main__":
    sys.exit(main() or 0)
