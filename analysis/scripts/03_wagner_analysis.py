"""
03_wagner_analysis.py
Opción I: cross-validar hallazgos de Schoels (Fase 1-2) contra Wagner 2018
(GSE112294, ~92K células del primer día zebrafish, 18 samples).

Estrategia:
  - Wagner ya tiene cluster IDs anotados por célula (en _clustID.txt.gz por GSM).
  - ClusterNames.csv da el mapping cluster ID -> nombre (incluye 4 clusters
    explícitos de pronephric duct: 69, 105, 109, 187).
  - Por lo tanto NO re-clusterizamos: cargamos, subseteamos a las pronephric
    duct cells, y replicamos el marker analysis.

Samples relevantes para pronefros (untreated time-course):
  GSM3067193 (14hpf) — contiene cluster 69
  GSM3067194 (18hpf) — contiene clusters 105, 109
  GSM3067195 (24hpf) — contiene cluster 187

Archivos esperados en RAW.tar después de untar:
  GSM3067193_14hpf.csv.gz       — counts (genes × cells)
  GSM3067193_14hpf_clustID.txt.gz — cluster assignment per cell
  GSM3067193_14hpf_nm.csv.gz    — normalized matrix (no usamos)
  ... idem para GSM3067194, GSM3067195

Lee:   analysis/data/wagner/GSE112294_RAW.tar (after download completes)
Escribe: analysis/outputs/wagner_pronephros.h5ad
        analysis/outputs/wagner_markers.csv
        analysis/outputs/wagner_vs_schoels_comparison.csv
"""

from pathlib import Path
import sys
import json
import re
import tarfile
import gzip
import io
import time

import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad

DATA_DIR = Path("analysis/data/wagner")
OUT_DIR = Path("analysis/outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Pronephric duct cluster IDs (from ClusterNames.csv inspection)
# These are 1-indexed integer cluster IDs for the corresponding timepoints.
PRONEPHROS_CLUSTERS = {
    14: [69],         # "14hpf-mesoderm - pronephric duct"
    18: [105, 109],   # "18hpf-pronephric duct - posterior" + "18hpf-pronephric duct"
    24: [187],        # "24hpf-pronephric duct"
}

# Samples relevant to pronephros window (untreated time-course)
PRONEPHROS_SAMPLES = {
    "GSM3067193": "14hpf",
    "GSM3067194": "18hpf",
    "GSM3067195": "24hpf",
}

# Reuse mapping from Schoels phase 2
SYM_MAP_FILE = OUT_DIR / "ensembl_symbol_map.json"


def log(msg):
    print(f"[wagner] {msg}", flush=True)


def parse_cluster_names(cluster_names_path):
    """Parse ClusterNames.csv.gz which has been observed to have unusual line breaks.
    Returns: {(timepoint, cluster_id): cluster_name}"""
    with gzip.open(cluster_names_path, "rt", encoding="utf-8") as f:
        text = f.read()
    # Try newline-split first
    lines = text.splitlines()
    if len(lines) < 5:
        # Likely all on one line - try to recover by splitting on the timepoint pattern
        # The pattern is "<num>,<id>,<name>" where each new entry begins with a small
        # integer (4, 6, 8, 10, 14, 18, 24). Split before each timepoint integer.
        # This is brittle; fall back to regex.
        # More robust: split on commas then group every 3.
        parts = text.replace("\n", ",").split(",")
        # Skip header
        if parts[0].lower().startswith("timepoint") or "timepoint" in parts[0].lower():
            parts = parts[3:]  # skip 3 header tokens
        else:
            parts = parts[3:]
        # Group every 3
        result = {}
        for i in range(0, len(parts) - 2, 3):
            try:
                tp = int(parts[i])
                cid_raw = parts[i + 1].strip()
                # cluster_id may be "1.1" style or "69" style
                cid = cid_raw  # keep as string for now
                name = parts[i + 2].strip()
                result[(tp, cid)] = name
            except (ValueError, IndexError):
                continue
        return result
    # Standard CSV parsing
    rows = [line.split(",", 2) for line in lines[1:] if line.strip()]
    return {(int(r[0]), r[1].strip()): r[2].strip() for r in rows if len(r) >= 3}


def extract_sample_files(tar_path, gsm, timepoint, dest_dir):
    """Get counts + clustID files for a single GSM.
    Strategy:
      1. If files already exist in dest_dir (e.g., direct-downloaded), use them.
      2. Otherwise try to extract from RAW.tar (may fail if tar truncated).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "counts": f"{gsm}_{timepoint}.csv.gz",
        "clustID": f"{gsm}_{timepoint}_clustID.txt.gz",
    }
    extracted = {}
    # Step 1: check direct presence
    for key, fname in expected.items():
        out = dest_dir / fname
        if out.exists() and out.stat().st_size > 0:
            extracted[key] = out
    if len(extracted) == len(expected):
        return extracted

    # Step 2: try tar extraction
    if not tar_path.exists():
        return extracted
    try:
        with tarfile.open(tar_path, "r") as tar:
            # iterate members defensively (tar may be truncated)
            try:
                members = tar.getmembers()
            except Exception as e:
                log(f"  WARN: tar metadata read failed: {e}; trying iter")
                members = []
                tar2 = tarfile.open(tar_path, "r")
                for m in tar2:
                    members.append(m)
                tar2.close()
            for member in members:
                base = Path(member.name).name
                for key, fname in expected.items():
                    if key in extracted:
                        continue
                    if base == fname:
                        out = dest_dir / fname
                        try:
                            with tar.extractfile(member) as src, open(out, "wb") as dst:
                                dst.write(src.read())
                            extracted[key] = out
                        except Exception as e:
                            log(f"  ERROR extracting {fname}: {e}")
                        break
    except Exception as e:
        log(f"  WARN: tar open failed: {e}")
    return extracted


def load_sample(gsm, timepoint, files):
    """Load counts and cluster IDs for one sample. Returns AnnData."""
    log(f"Loading {gsm} ({timepoint})")
    # Counts: rows = genes, cols = cells (Wagner convention)
    counts_df = pd.read_csv(files["counts"], index_col=0, compression="gzip")
    log(f"  counts: genes={counts_df.shape[0]}, cells={counts_df.shape[1]}")
    # ClustID: one cluster ID per cell (one cluster ID per line, in cell-column order)
    with gzip.open(files["clustID"], "rt") as f:
        clust_ids = [line.strip() for line in f if line.strip()]
    log(f"  clustID entries: {len(clust_ids)}")
    if len(clust_ids) != counts_df.shape[1]:
        log(f"  WARNING: clustID count ({len(clust_ids)}) != cell count ({counts_df.shape[1]})")
    adata = ad.AnnData(
        X=counts_df.T.values.astype(np.float32),
        obs=pd.DataFrame({
            "gsm": gsm,
            "timepoint": timepoint,
            "wagner_cluster": clust_ids[:counts_df.shape[1]],
        }, index=counts_df.columns),
        var=pd.DataFrame(index=counts_df.index),
    )
    return adata


def main():
    log("=== Wagner GSE112294 — Opción I cross-validation ===")

    tar_path = DATA_DIR / "GSE112294_RAW.tar"
    extract_dir = DATA_DIR / "extracted"

    # Either tar OR pre-extracted files in extract_dir must exist
    have_tar = tar_path.exists()
    pre_extracted = list(extract_dir.glob("*.csv.gz")) if extract_dir.exists() else []

    if have_tar:
        size_mb = tar_path.stat().st_size / (1024 * 1024)
        log(f"RAW.tar size: {size_mb:.1f} MB")
    elif pre_extracted:
        log(f"No tar; using {len(pre_extracted)} pre-extracted files in {extract_dir}")
    else:
        log(f"ERROR: neither {tar_path} nor pre-extracted files in {extract_dir}")
        sys.exit(1)

    # 1. Parse ClusterNames to confirm pronephros cluster IDs
    log("Parsing ClusterNames...")
    cluster_names = parse_cluster_names(DATA_DIR / "GSE112294_ClusterNames.csv.gz")
    log(f"  {len(cluster_names)} cluster entries parsed")

    pronephros_clusters_found = []
    for tp, cluster_ids in PRONEPHROS_CLUSTERS.items():
        for cid in cluster_ids:
            for key, name in cluster_names.items():
                key_tp = key[0]
                key_cid = key[1].strip()
                if key_tp == tp and (key_cid == str(cid) or key_cid == f"{cid}"):
                    pronephros_clusters_found.append((tp, cid, name))
                    log(f"  CONFIRMED tp={tp} cluster={cid}: {name}")
    if not pronephros_clusters_found:
        log("  WARN: pronephros cluster IDs not matched in ClusterNames; proceeding with hardcoded list")

    # 2. Extract relevant samples from tar
    extract_dir = DATA_DIR / "extracted"
    extracted = {}
    for gsm, tp in PRONEPHROS_SAMPLES.items():
        log(f"Extracting {gsm} ({tp}) from tar...")
        files = extract_sample_files(tar_path, gsm, tp, extract_dir)
        if "counts" not in files or "clustID" not in files:
            log(f"  WARNING: missing files for {gsm}: got {list(files.keys())}")
        extracted[gsm] = files

    # 3. Load all relevant samples
    adatas = []
    for gsm, tp in PRONEPHROS_SAMPLES.items():
        if "counts" in extracted[gsm] and "clustID" in extracted[gsm]:
            try:
                adatas.append(load_sample(gsm, tp, extracted[gsm]))
            except Exception as e:
                log(f"  ERROR loading {gsm}: {e}")

    if not adatas:
        log("ERROR: no samples loaded; aborting")
        sys.exit(1)

    adata = ad.concat(adatas, join="outer", merge="same",
                      label="sample", keys=list(PRONEPHROS_SAMPLES.keys()))
    log(f"Combined: {adata.n_obs} cells × {adata.n_vars} genes across {len(adatas)} samples")
    log(f"Cells per sample: {adata.obs['gsm'].value_counts().to_dict()}")
    log(f"Cluster distribution (top 20): {adata.obs['wagner_cluster'].value_counts().head(20).to_dict()}")

    # 4. Subset to pronephric duct clusters
    target_cluster_ids = set()
    for tp, cluster_ids in PRONEPHROS_CLUSTERS.items():
        for cid in cluster_ids:
            target_cluster_ids.add(str(cid))
    log(f"Target pronephros cluster IDs: {sorted(target_cluster_ids)}")

    adata_pn = adata[adata.obs["wagner_cluster"].isin(target_cluster_ids)].copy()
    log(f"Pronephros subset: {adata_pn.n_obs} cells × {adata_pn.n_vars} genes")
    log(f"Pronephros cells per cluster: {adata_pn.obs['wagner_cluster'].value_counts().to_dict()}")
    log(f"Pronephros cells per timepoint: {adata_pn.obs['timepoint'].value_counts().to_dict()}")

    if adata_pn.n_obs == 0:
        log("ERROR: pronephros subset has 0 cells. Cluster IDs may not match expected format.")
        log(f"Unique cluster IDs in data: {adata.obs['wagner_cluster'].unique()[:30]}")
        sys.exit(1)

    # 5. Normalize + log
    sc.pp.filter_genes(adata_pn, min_cells=3)
    sc.pp.normalize_total(adata_pn, target_sum=1e4)
    sc.pp.log1p(adata_pn)

    # 6. Marker analysis. Wagner uses gene SYMBOLS (e.g., "wt1a", "pax2a") in
    # var_names — NOT Ensembl IDs like Schoels does. So we lookup by symbol
    # directly in Wagner. Schoels mapping cached in ensembl_symbol_map.json
    # gives us the symbol list (keys); we use the symbol directly here.
    sym_map = json.loads(SYM_MAP_FILE.read_text()) if SYM_MAP_FILE.exists() else {}
    log(f"Using {len(sym_map)} markers from Schoels symbol map (lookup by symbol in Wagner)")

    rows = []
    for sym, ens in sym_map.items():
        # Lookup by SYMBOL in Wagner (different namespace than Schoels)
        if sym not in adata_pn.var_names:
            rows.append({
                "marker": sym, "ens_id": ens or "",
                "in_dataset": False,
                "n_cells_expressing": 0, "pct_expressing": 0.0,
            })
            continue
        X = adata_pn[:, sym].X
        expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
        n_pos = int((expr > 0).sum())
        rows.append({
            "marker": sym, "ens_id": ens, "in_dataset": True,
            "n_cells_expressing": n_pos,
            "pct_expressing": float(n_pos / len(expr) * 100),
            "mean_expr": float(expr.mean()),
            "max_expr": float(expr.max()),
        })
        # Per timepoint
        for tp in adata_pn.obs["timepoint"].unique():
            sub = adata_pn[adata_pn.obs["timepoint"] == tp]
            X_tp = sub[:, sym].X
            expr_tp = X_tp.toarray().flatten() if hasattr(X_tp, "toarray") else np.asarray(X_tp).flatten()
            rows.append({
                "marker": sym, "ens_id": ens, "in_dataset": True,
                "scope": tp,
                "n_cells_expressing": int((expr_tp > 0).sum()),
                "pct_expressing": float((expr_tp > 0).mean() * 100),
                "mean_expr": float(expr_tp.mean()),
                "max_expr": float(expr_tp.max()),
            })
        # Per cluster
        for clust in sorted(adata_pn.obs["wagner_cluster"].unique()):
            sub = adata_pn[adata_pn.obs["wagner_cluster"] == clust]
            X_c = sub[:, sym].X
            expr_c = X_c.toarray().flatten() if hasattr(X_c, "toarray") else np.asarray(X_c).flatten()
            rows.append({
                "marker": sym, "ens_id": ens, "in_dataset": True,
                "scope": f"cluster_{clust}",
                "n_cells_expressing": int((expr_c > 0).sum()),
                "pct_expressing": float((expr_c > 0).mean() * 100),
                "mean_expr": float(expr_c.mean()),
                "max_expr": float(expr_c.max()),
            })

    markers_df = pd.DataFrame(rows)
    markers_df.to_csv(OUT_DIR / "wagner_markers.csv", index=False)

    log("\n=== Markers in Wagner pronephric duct cells ===")
    overall = markers_df[~markers_df.get("scope", pd.Series([None]*len(markers_df))).notna()] if "scope" in markers_df.columns else markers_df
    print(overall[overall["in_dataset"]].sort_values("pct_expressing", ascending=False)[
        ["marker", "ens_id", "n_cells_expressing", "pct_expressing"]
    ].head(25).to_string(index=False))

    # 7. Cross-validation table: Wagner vs Schoels
    schoels_csv = OUT_DIR / "schoels_markers_v2.csv"
    if schoels_csv.exists():
        schoels_df = pd.read_csv(schoels_csv)
        schoels_overall = schoels_df[~schoels_df["group"].str.contains("::", na=False)]
        # Map symbol -> schoels pct
        schoels_pct = schoels_overall.set_index("symbol")["pct_expressing"].to_dict()

        comparison_rows = []
        for sym, ens in sym_map.items():
            wagner_match = markers_df[(markers_df["marker"] == sym) & (~markers_df.get("scope", pd.Series([None]*len(markers_df))).notna())]
            wagner_pct = float(wagner_match["pct_expressing"].iloc[0]) if len(wagner_match) > 0 else 0.0
            wagner_in = bool(wagner_match["in_dataset"].iloc[0]) if len(wagner_match) > 0 else False
            comparison_rows.append({
                "marker": sym,
                "ens_id": ens or "",
                "schoels_pct": schoels_pct.get(sym, 0.0),
                "wagner_pn_pct": wagner_pct,
                "wagner_in_dataset": wagner_in,
            })
        comp_df = pd.DataFrame(comparison_rows)
        comp_df["delta"] = comp_df["wagner_pn_pct"] - comp_df["schoels_pct"]
        comp_df = comp_df.sort_values("schoels_pct", ascending=False)
        comp_df.to_csv(OUT_DIR / "wagner_vs_schoels_comparison.csv", index=False)
        log("\n=== Wagner pronephric duct vs Schoels (whole pronefros) — % expressing ===")
        print(comp_df.head(25).to_string(index=False))

    # 8. Save AnnData
    adata_pn.write_h5ad(OUT_DIR / "wagner_pronephros.h5ad")

    # 9. Run summary
    summary = {
        "phase": "Option I",
        "wagner_total_cells_loaded": int(adata.n_obs),
        "wagner_pronephros_cells": int(adata_pn.n_obs),
        "pronephros_per_timepoint": {k: int(v) for k, v in adata_pn.obs["timepoint"].value_counts().to_dict().items()},
        "pronephros_per_cluster": {k: int(v) for k, v in adata_pn.obs["wagner_cluster"].value_counts().to_dict().items()},
        "schoels_pronephros_cells": 2065,
        "wagner_to_schoels_ratio": float(adata_pn.n_obs / 2065),
    }
    with open(OUT_DIR / "wagner_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log(f"\nSummary:\n{json.dumps(summary, indent=2)}")
    log("=== Wagner cross-validation done ===")


if __name__ == "__main__":
    sys.exit(main() or 0)
