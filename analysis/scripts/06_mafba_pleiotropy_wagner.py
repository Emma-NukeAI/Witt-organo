"""
06_mafba_pleiotropy_wagner.py
Pre-resolve item 2: verificar mafba expression cross-cluster en Wagner 14-24 hpf
para identificar potencial pleiotropy.

Pipeline:
  1. Cargar 3 Wagner samples (14, 18, 24 hpf) ya extraídos.
  2. Concatenar a AnnData de 18,932 cells.
  3. Mapear cluster IDs a names usando ClusterNames.csv.
  4. Calcular % cells expressing mafba per cluster.
  5. Identificar clusters NO renales con expresión significativa de mafba.
  6. Output: pleiotropy report — qué tejidos podrían confundir el fenotipo de mafba KO.

Reads:  analysis/data/wagner/extracted/GSM3067{193,194,195}_*.csv.gz
        analysis/data/wagner/GSE112294_ClusterNames.csv.gz
Writes: analysis/outputs/mafba_design/mafba_pleiotropy_wagner.csv
        analysis/outputs/mafba_design/mafba_pleiotropy_summary.json
"""

from pathlib import Path
import gzip
import json
import sys

import numpy as np
import pandas as pd
import anndata as ad
import scanpy as sc

DATA_DIR = Path("analysis/data/wagner/extracted")
CLUSTER_NAMES_FILE = Path("analysis/data/wagner/GSE112294_ClusterNames.csv.gz")
OUT_DIR = Path("analysis/outputs/mafba_design")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SAMPLES = {
    "GSM3067193": "14hpf",
    "GSM3067194": "18hpf",
    "GSM3067195": "24hpf",
}

PRONEPHROS_CLUSTERS = ["69", "105", "109", "187"]
PRONEPHROS_NAMES = {
    "69":  "14hpf-mesoderm - pronephric duct",
    "105": "18hpf-pronephric duct - posterior",
    "109": "18hpf-pronephric duct",
    "187": "24hpf-pronephric duct",
}

def log(msg):
    print(f"[pleiotropy] {msg}", flush=True)

def parse_cluster_names():
    """Parse the unusual single-line ClusterNames format from Wagner GEO."""
    with gzip.open(CLUSTER_NAMES_FILE, "rt", encoding="utf-8") as f:
        text = f.read()
    parts = text.replace("\n", ",").split(",")
    if parts[0].lower().startswith("timepoint"):
        parts = parts[3:]  # skip header
    result = {}
    for i in range(0, len(parts) - 2, 3):
        try:
            tp = int(parts[i])
            cid = parts[i + 1].strip()
            name = parts[i + 2].strip()
            result[cid] = {"timepoint": tp, "name": name}
        except (ValueError, IndexError):
            continue
    return result

def load_sample(gsm, tp):
    counts_file = DATA_DIR / f"{gsm}_{tp}.csv.gz"
    clust_file = DATA_DIR / f"{gsm}_{tp}_clustID.txt.gz"
    log(f"Loading {gsm} ({tp})")
    df = pd.read_csv(counts_file, index_col=0, compression="gzip")
    with gzip.open(clust_file, "rt") as f:
        clust_ids = [line.strip() for line in f if line.strip()]
    if len(clust_ids) != df.shape[1]:
        log(f"  WARNING: clust_ids ({len(clust_ids)}) != cells ({df.shape[1]})")
    adata = ad.AnnData(
        X=df.T.values.astype(np.float32),
        obs=pd.DataFrame({
            "gsm": gsm, "timepoint": tp,
            "wagner_cluster": clust_ids[:df.shape[1]],
        }, index=df.columns),
        var=pd.DataFrame(index=df.index),
    )
    return adata

def main():
    log("=== mafba pleiotropy check across Wagner 14-24 hpf ===")

    # Step 1: load samples
    cluster_info = parse_cluster_names()
    log(f"Parsed {len(cluster_info)} cluster definitions from ClusterNames")

    adatas = [load_sample(gsm, tp) for gsm, tp in SAMPLES.items()]
    adata = ad.concat(
        adatas, join="outer", merge="same",
        label="sample", keys=list(SAMPLES.keys()),
    )
    log(f"Combined: {adata.n_obs} cells x {adata.n_vars} genes")

    # Step 2: filter + normalize
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    log(f"Post-filter: {adata.n_obs} cells x {adata.n_vars} genes")

    # Step 3: check mafba present
    if "mafba" not in adata.var_names:
        log("ERROR: mafba not in Wagner gene list — namespace issue")
        sys.exit(1)
    log(f"mafba present in dataset")

    # Step 4: compute mafba expression per cluster
    log("Computing mafba expression per cluster...")
    mafba_X = adata[:, "mafba"].X
    mafba_expr = mafba_X.toarray().flatten() if hasattr(mafba_X, "toarray") else np.asarray(mafba_X).flatten()
    adata.obs["mafba_expr"] = mafba_expr
    adata.obs["mafba_pos"] = (mafba_expr > 0).astype(int)

    # Group by cluster
    rows = []
    for cluster_id in sorted(adata.obs["wagner_cluster"].unique()):
        sub = adata.obs[adata.obs["wagner_cluster"] == cluster_id]
        n = len(sub)
        n_pos = sub["mafba_pos"].sum()
        pct = (n_pos / n * 100) if n > 0 else 0
        mean_expr = sub["mafba_expr"].mean() if n > 0 else 0
        max_expr = sub["mafba_expr"].max() if n > 0 else 0
        cinfo = cluster_info.get(cluster_id, {})
        is_pronephros = cluster_id in PRONEPHROS_CLUSTERS
        rows.append({
            "cluster_id": cluster_id,
            "timepoint": cinfo.get("timepoint", "?"),
            "cluster_name": cinfo.get("name", "(unknown)"),
            "n_cells": int(n),
            "n_mafba_pos": int(n_pos),
            "pct_mafba_pos": round(float(pct), 2),
            "mean_log1p_expr": round(float(mean_expr), 3),
            "max_log1p_expr": round(float(max_expr), 3),
            "is_pronephros": is_pronephros,
        })
    df_per_cluster = pd.DataFrame(rows)
    df_per_cluster = df_per_cluster.sort_values("pct_mafba_pos", ascending=False)
    df_per_cluster.to_csv(OUT_DIR / "mafba_pleiotropy_wagner.csv", index=False)
    log(f"Saved per-cluster expression to mafba_pleiotropy_wagner.csv")

    # Step 5: identify pleiotropy
    # Threshold: clusters with >= 20% mafba+ cells AND >= 10 cells
    significant = df_per_cluster[
        (df_per_cluster["pct_mafba_pos"] >= 20.0) & (df_per_cluster["n_cells"] >= 10)
    ]
    log(f"\n=== Clusters with >=20% mafba+ AND >=10 cells (n={len(significant)}) ===")
    print(significant[["cluster_id", "timepoint", "cluster_name", "n_cells", "pct_mafba_pos", "is_pronephros"]].to_string(index=False))

    pronephros_summary = df_per_cluster[df_per_cluster["is_pronephros"]]
    log(f"\n=== mafba en pronephros clusters específicamente ===")
    print(pronephros_summary[["cluster_id", "cluster_name", "n_cells", "pct_mafba_pos"]].to_string(index=False))

    # Step 6: pleiotropy assessment
    pronephros_pct = pronephros_summary["pct_mafba_pos"].mean()
    non_pronephros_significant = significant[~significant["is_pronephros"]]
    n_non_pronephros_sig = len(non_pronephros_significant)
    max_non_pronephros_pct = non_pronephros_significant["pct_mafba_pos"].max() if len(non_pronephros_significant) > 0 else 0

    if max_non_pronephros_pct == 0:
        risk = "LOW"
        narrative = "mafba expression no detected at significant levels en clusters no-renales — pleiotropy risk minimal."
    elif max_non_pronephros_pct < pronephros_pct:
        risk = "MEDIUM"
        narrative = f"mafba expressed en algunos clusters no-renales (max {max_non_pronephros_pct:.1f}%) pero menor que en pronephros (avg {pronephros_pct:.1f}%) — pleiotropy plausible pero no dominante."
    else:
        risk = "HIGH"
        narrative = f"mafba expressed más fuerte en otros tejidos (max {max_non_pronephros_pct:.1f}%) que en pronephros ({pronephros_pct:.1f}%) — pleiotropy probable; KO phenotype puede ser difícil de aislar a podocyte."

    summary = {
        "tf": "mafba",
        "wagner_samples": list(SAMPLES.keys()),
        "n_cells_total": int(adata.n_obs),
        "n_clusters_analyzed": int(len(df_per_cluster)),
        "pronephros_clusters_pct_mafba_pos": {
            r["cluster_id"]: r["pct_mafba_pos"]
            for _, r in pronephros_summary.iterrows()
        },
        "pronephros_avg_pct_mafba_pos": round(float(pronephros_pct), 2),
        "n_non_pronephros_clusters_significant": int(n_non_pronephros_sig),
        "max_non_pronephros_pct": round(float(max_non_pronephros_pct), 2),
        "non_pronephros_significant_clusters": [
            {"cluster_id": r["cluster_id"], "name": r["cluster_name"], "pct": r["pct_mafba_pos"], "n_cells": r["n_cells"]}
            for _, r in non_pronephros_significant.head(20).iterrows()
        ],
        "pleiotropy_risk": risk,
        "narrative": narrative,
        "implication_for_experiment": {
            "LOW": "Proceed with mafba KO as planned. Phenotype likely podocyte-specific.",
            "MEDIUM": "Proceed with mafba KO. Add IHC/WISH validation in non-pronephros tissues to confirm specificity. Consider tissue-specific KO in Phase II if pleiotropy interferes.",
            "HIGH": "Reconsider experimental design. May need conditional KO from start. Alternative: focus on next candidate (sall1a) which may be more tissue-specific. At minimum: imaging full-embryo phenotype to document pleiotropy."
        }[risk],
    }

    with open(OUT_DIR / "mafba_pleiotropy_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    log(f"\n=== PLEIOTROPY ASSESSMENT ===")
    log(f"Risk level: {risk}")
    log(f"Narrative: {narrative}")
    log(f"Implication: {summary['implication_for_experiment']}")
    log(f"\nSaved summary to mafba_pleiotropy_summary.json")
    log("=== Pleiotropy check complete ===")

if __name__ == "__main__":
    sys.exit(main() or 0)
