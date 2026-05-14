"""
07_pleiotropy_all_candidates.py
Re-priorización: pleiotropy check para los 6 TFs candidatos novel + 5 validados
en Wagner 14-24 hpf. La output es la matriz comparativa que define cuál es el
candidato más pronefros-específico (= mejor target para KO global del experimento N).

Pipeline:
  1. Cargar Wagner combined (18,932 cells, mismas samples 14/18/24 hpf).
  2. Para cada candidate TF, computar:
     - % cells expressing en pronephros clusters (69, 105, 109, 187)
     - max % en cluster non-pronephros
     - ratio pronephros / max non-pronephros (specificity score)
     - n top non-pronephros tissues con expression alta
  3. Tabla comparativa + re-priorización.

Reads:  analysis/data/wagner/extracted/GSM3067{193,194,195}_*.csv.gz
Writes: analysis/outputs/mafba_design/pleiotropy_all_candidates.csv
        analysis/outputs/mafba_design/pleiotropy_reprioritization.json
        analysis/outputs/mafba_design/pleiotropy_reprioritization.md
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

# Los 13 TFs Tier 1-3 + tbx2b bonus
CANDIDATES = {
    # Validados ya por literatura
    "pax2a":   {"tier": "T1", "status": "validated"},
    "wt1a":    {"tier": "T2", "status": "validated"},
    "wt1b":    {"tier": "T2", "status": "validated"},
    "sim1a":   {"tier": "T3", "status": "validated"},
    "dzip1l":  {"tier": "T3", "status": "validated"},
    # Novel
    "mafba":   {"tier": "T1", "status": "novel"},
    "ripply1": {"tier": "T2", "status": "novel"},
    "sall1a":  {"tier": "T3", "status": "novel"},
    "hipk2":   {"tier": "T3", "status": "novel"},
    "hoxb8a":  {"tier": "T3", "status": "novel"},
    "prox1a":  {"tier": "T3", "status": "novel"},
    # Indirect / bonus
    "foxj1b":  {"tier": "T3", "status": "indirect"},
    "tbx2b":   {"tier": "bonus", "status": "validated"},
}

def log(msg):
    print(f"[priority] {msg}", flush=True)

def parse_cluster_names():
    with gzip.open(CLUSTER_NAMES_FILE, "rt", encoding="utf-8") as f:
        text = f.read()
    parts = text.replace("\n", ",").split(",")
    if parts[0].lower().startswith("timepoint"):
        parts = parts[3:]
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

def load_wagner_combined():
    """Load and concat 3 Wagner samples."""
    adatas = []
    for gsm, tp in SAMPLES.items():
        log(f"Loading {gsm} ({tp})")
        df = pd.read_csv(DATA_DIR / f"{gsm}_{tp}.csv.gz", index_col=0, compression="gzip")
        with gzip.open(DATA_DIR / f"{gsm}_{tp}_clustID.txt.gz", "rt") as f:
            cids = [line.strip() for line in f if line.strip()]
        a = ad.AnnData(
            X=df.T.values.astype(np.float32),
            obs=pd.DataFrame({
                "gsm": gsm, "timepoint": tp,
                "wagner_cluster": cids[:df.shape[1]],
            }, index=df.columns),
            var=pd.DataFrame(index=df.index),
        )
        adatas.append(a)
    adata = ad.concat(adatas, join="outer", merge="same",
                      label="sample", keys=list(SAMPLES.keys()))
    return adata

def compute_pleiotropy(adata, gene_symbol, cluster_info):
    """For one gene, return per-cluster expression + pleiotropy summary."""
    if gene_symbol not in adata.var_names:
        return None, None
    X = adata[:, gene_symbol].X
    expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
    pos = (expr > 0).astype(int)

    rows = []
    for cid in sorted(adata.obs["wagner_cluster"].unique()):
        mask = adata.obs["wagner_cluster"] == cid
        n = int(mask.sum())
        if n < 5:  # too small to be reliable
            continue
        n_pos = int(pos[mask.values].sum())
        pct = n_pos / n * 100
        cinfo = cluster_info.get(cid, {})
        rows.append({
            "gene": gene_symbol,
            "cluster_id": cid,
            "timepoint": cinfo.get("timepoint", "?"),
            "cluster_name": cinfo.get("name", "(unknown)"),
            "n_cells": n,
            "pct_pos": round(pct, 2),
            "is_pronephros": cid in PRONEPHROS_CLUSTERS,
        })
    df = pd.DataFrame(rows)

    pn = df[df["is_pronephros"]]
    non_pn = df[~df["is_pronephros"]]
    pn_avg = float(pn["pct_pos"].mean()) if len(pn) > 0 else 0
    pn_max = float(pn["pct_pos"].max()) if len(pn) > 0 else 0
    non_pn_max = float(non_pn["pct_pos"].max()) if len(non_pn) > 0 else 0
    non_pn_top5_avg = float(non_pn.nlargest(5, "pct_pos")["pct_pos"].mean()) if len(non_pn) >= 5 else 0
    n_non_pn_above_pn_avg = int((non_pn["pct_pos"] > pn_avg).sum())
    n_non_pn_above_50pct = int((non_pn["pct_pos"] > 50).sum())

    # Specificity ratio: pronephros avg / non-pronephros max
    if non_pn_max > 0:
        specificity_ratio = pn_avg / non_pn_max
    else:
        specificity_ratio = float("inf") if pn_avg > 0 else 0

    # Risk classification
    if non_pn_max == 0 or pn_avg == 0:
        risk = "N/A"
    elif specificity_ratio >= 1.5:
        risk = "LOW"
    elif specificity_ratio >= 0.7:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    summary = {
        "gene": gene_symbol,
        "pronephros_pct_avg": round(pn_avg, 2),
        "pronephros_pct_max": round(pn_max, 2),
        "non_pronephros_max_pct": round(non_pn_max, 2),
        "non_pronephros_top5_avg_pct": round(non_pn_top5_avg, 2),
        "n_non_pn_clusters_above_pronephros_avg": n_non_pn_above_pn_avg,
        "n_non_pn_clusters_above_50pct": n_non_pn_above_50pct,
        "specificity_ratio_pn_to_max_nonpn": round(specificity_ratio, 3) if specificity_ratio != float("inf") else "inf",
        "pleiotropy_risk": risk,
        "top3_non_pn_tissues": [
            {"cluster": r["cluster_id"], "name": r["cluster_name"], "pct": r["pct_pos"]}
            for _, r in non_pn.nlargest(3, "pct_pos").iterrows()
        ],
    }
    return df, summary

def main():
    log("=== Pleiotropy comparativo: 13 candidatos en Wagner 14-24 hpf ===")

    # Load
    cluster_info = parse_cluster_names()
    adata = load_wagner_combined()
    log(f"Combined Wagner: {adata.n_obs} cells × {adata.n_vars} genes")

    # Filter + normalize
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    log(f"Post-filter: {adata.n_obs} cells × {adata.n_vars} genes")

    # Compute for each candidate
    all_per_cluster = []
    summaries = []
    for gene, info in CANDIDATES.items():
        log(f"\n--- {gene} ({info['tier']}, {info['status']}) ---")
        if gene not in adata.var_names:
            log(f"  NOT in Wagner var_names — skipping")
            summaries.append({
                "gene": gene, "tier": info["tier"], "status": info["status"],
                "pleiotropy_risk": "NOT_IN_DATASET",
                "pronephros_pct_avg": 0,
                "non_pronephros_max_pct": 0,
                "specificity_ratio_pn_to_max_nonpn": "n/a",
            })
            continue
        df_per, summary = compute_pleiotropy(adata, gene, cluster_info)
        all_per_cluster.append(df_per)
        summary["tier"] = info["tier"]
        summary["status"] = info["status"]
        summaries.append(summary)
        log(f"  pronephros avg: {summary['pronephros_pct_avg']:.1f}% | "
            f"non-pn max: {summary['non_pronephros_max_pct']:.1f}% | "
            f"specificity ratio: {summary['specificity_ratio_pn_to_max_nonpn']} | "
            f"risk: {summary['pleiotropy_risk']}")

    # Combine all per-cluster data
    if all_per_cluster:
        combined = pd.concat(all_per_cluster, ignore_index=True)
        combined.to_csv(OUT_DIR / "pleiotropy_all_candidates.csv", index=False)
        log(f"\nSaved per-cluster data: pleiotropy_all_candidates.csv")

    # Build re-prioritization
    summaries_df = pd.DataFrame(summaries)
    # Sort: novel candidates by best specificity ratio
    novel = summaries_df[summaries_df["status"] == "novel"].copy()
    # Convert "inf" string back to large number for sorting
    novel["sr_numeric"] = pd.to_numeric(novel["specificity_ratio_pn_to_max_nonpn"], errors="coerce").fillna(0)
    novel_ranked = novel.sort_values(
        ["sr_numeric", "pronephros_pct_avg"],
        ascending=[False, False]
    )

    log(f"\n=== RE-PRIORIZACIÓN de candidatos NOVEL (por specificity ratio) ===")
    cols = ["gene", "tier", "pronephros_pct_avg", "non_pronephros_max_pct",
            "specificity_ratio_pn_to_max_nonpn", "pleiotropy_risk"]
    print(novel_ranked[cols].to_string(index=False))

    log(f"\n=== Para CONTEXTO: candidatos VALIDADOS (literatura) ===")
    validated = summaries_df[summaries_df["status"] == "validated"]
    print(validated[cols].to_string(index=False))

    # Save outputs
    output = {
        "analysis": "pleiotropy comparison across 13 TF candidates",
        "n_cells_total": int(adata.n_obs),
        "wagner_samples": list(SAMPLES.keys()),
        "summaries": summaries,
        "novel_ranked_by_specificity": novel_ranked[cols + ["top3_non_pn_tissues"]].to_dict(orient="records"),
    }
    with open(OUT_DIR / "pleiotropy_reprioritization.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Markdown summary
    md_lines = [
        "# Re-priorización de candidatos novel basada en pleiotropy",
        "",
        f"**Análisis:** % cells expressing per gene en Wagner 14-24 hpf, en pronephros clusters (69, 105, 109, 187) vs todos los demás clusters.",
        f"**Métrica clave:** Specificity ratio = pronephros_avg / non_pronephros_max. >= 1.5 = LOW pleiotropy risk; 0.7-1.5 = MEDIUM; < 0.7 = HIGH.",
        "",
        "## Candidatos NOVEL ranked por specificity",
        "",
        "| Gene | Tier | Pronefros avg % | Non-PN max % | Specificity ratio | Risk |",
        "|------|------|-----------------|--------------|-------------------|------|",
    ]
    for _, r in novel_ranked.iterrows():
        md_lines.append(
            f"| `{r['gene']}` | {r['tier']} | {r['pronephros_pct_avg']:.1f}% | "
            f"{r['non_pronephros_max_pct']:.1f}% | {r['specificity_ratio_pn_to_max_nonpn']} | {r['pleiotropy_risk']} |"
        )
    md_lines.extend([
        "",
        "## Candidatos VALIDADOS (referencia)",
        "",
        "| Gene | Tier | Pronefros avg % | Non-PN max % | Specificity ratio | Risk |",
        "|------|------|-----------------|--------------|-------------------|------|",
    ])
    for _, r in validated.iterrows():
        sr = r['specificity_ratio_pn_to_max_nonpn']
        md_lines.append(
            f"| `{r['gene']}` | {r['tier']} | {r['pronephros_pct_avg']:.1f}% | "
            f"{r['non_pronephros_max_pct']:.1f}% | {sr} | {r['pleiotropy_risk']} |"
        )
    md_lines.extend([
        "",
        "## Recomendación operativa",
        "",
        "Basada en specificity ratio (mayor = más pronephros-específico), el orden re-priorizado de candidatos novel para experimento KO global es:",
        "",
    ])
    for i, (_, r) in enumerate(novel_ranked.iterrows(), 1):
        risk_emoji = {"LOW": "✓", "MEDIUM": "~", "HIGH": "⚠️", "N/A": "?", "NOT_IN_DATASET": "?"}.get(r["pleiotropy_risk"], "?")
        md_lines.append(f"{i}. **`{r['gene']}`** {risk_emoji} (SR={r['specificity_ratio_pn_to_max_nonpn']}, risk={r['pleiotropy_risk']})")
    md_lines.append("")
    md_lines.append("**Implicación:** el ranking original priorizaba `mafba` por familia bZIP + Tier 1. Pero en términos de pleiotropy (qué tan limpio sería un KO global), el nuevo top puede no ser mafba.")

    md_file = OUT_DIR / "pleiotropy_reprioritization.md"
    md_file.write_text("\n".join(md_lines), encoding="utf-8")
    log(f"\nSaved MD summary: {md_file}")
    log("=== Re-priorización complete ===")

if __name__ == "__main__":
    sys.exit(main() or 0)
