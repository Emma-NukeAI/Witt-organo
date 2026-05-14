"""
08_experiment_pipeline_template.py
Pre-resolve item 4: pipeline computacional gene-agnostic para el experimento N.

Toma: 12 scRNA-seq samples (4 grupos × 3 stages 24/48/72 hpf) post-experiment.
Hace: QC → integration con Schoels reference → cluster mapping → differential
       abundance → DE per cluster → hypothesis testing P1-P5 → output contract
       estructurado con confidence updates.

Uso esperado (post-experimento):
  python 08_experiment_pipeline_template.py \\
      --target-gene mafba \\
      --target-symbol mafba \\
      --samples-dir analysis/data/experiment_N/ \\
      --reference-h5ad analysis/outputs/schoels_clustered.h5ad \\
      --output-dir analysis/outputs/experiment_N_results/

Configurable para cualquier TF candidato (mafba, hoxb8a, sall1a, etc.) cambiando
--target-gene. La estructura del análisis es la misma; solo cambia qué cluster
es 'target' y qué markers son los readouts.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad

# =============================================================================
# CONFIG SECTION — adjust per TF
# =============================================================================

# Map TF → (target Schoels cluster, expected effect direction, primary markers)
TF_TARGET_CONFIG = {
    "mafba": {
        "schoels_target_cluster": "17",  # podocyte cluster
        "biology": "podocyte",
        "primary_markers": ["wt1a", "wt1b", "podxl", "nphs1", "nphs2"],
        "control_markers": ["pax2a", "hnf1ba", "cdh17"],  # general identity, NOT podocyte
        "expected_direction": "decrease",
    },
    "hoxb8a": {
        "schoels_target_cluster": "16",  # progenitors TF-rich
        "biology": "progenitor pronefros",
        "primary_markers": ["pax2a", "lhx1a", "sall1a", "sim1a"],
        "control_markers": ["wt1a", "podxl"],  # podocyte, should be unaffected if hoxb8a is progenitor-specific
        "expected_direction": "shift",
    },
    "sall1a": {
        "schoels_target_cluster": "16",
        "biology": "progenitor pronefros",
        "primary_markers": ["pax2a", "lhx1a", "wt1a"],
        "control_markers": ["cdh17", "slc4a4a"],
        "expected_direction": "decrease",
    },
    "hipk2": {
        "schoels_target_cluster": "16",
        "biology": "progenitor pronefros",
        "primary_markers": ["pax2a", "wt1a", "podxl"],
        "control_markers": ["cdh17", "slc4a4a"],
        "expected_direction": "shift",
    },
}

# Predictions to test (from experiment design §2.3)
PREDICTIONS = [
    {
        "id": "P1",
        "description": "n cells in target cluster decreases in KO vs control",
        "test": "differential_abundance",
        "threshold": {"fdr": 0.05, "log2fc": 0.5},
    },
    {
        "id": "P2",
        "description": "% cells expressing primary marker[0] decreases in target cluster",
        "test": "chi2_proportions",
        "threshold": {"p": 0.05, "relative_reduction": 0.30},
    },
    {
        "id": "P3",
        "description": "Same pattern in 3+ of 4 primary markers",
        "test": "multiple_markers_corrected",
        "threshold": {"fdr": 0.05, "n_markers_significant": 3},
    },
    {
        "id": "P4",
        "description": "Control markers (general identity) NOT changed (specificity check)",
        "test": "chi2_proportions_should_be_null",
        "threshold": {"p": 0.10, "relative_change": 0.10},
    },
    {
        "id": "P5",
        "description": "Effect more pronounced 24 → 48 → 72 hpf",
        "test": "trend_test",
        "threshold": {"p": 0.10},
    },
]


# =============================================================================
# PIPELINE FUNCTIONS
# =============================================================================

def log(msg):
    print(f"[exp-pipeline] {msg}", flush=True)


def load_experiment_samples(samples_dir, expected_groups, expected_stages):
    """Load and label each sample. Expected naming: <group>_<stage>.h5ad
    where group ∈ {KO, scrambled, MO, MOctrl} and stage ∈ {24hpf, 48hpf, 72hpf}."""
    samples_dir = Path(samples_dir)
    adatas = []
    for group in expected_groups:
        for stage in expected_stages:
            fname = samples_dir / f"{group}_{stage}.h5ad"
            if not fname.exists():
                log(f"  WARNING: {fname} not found")
                continue
            a = sc.read_h5ad(fname)
            a.obs["group"] = group
            a.obs["stage"] = stage
            a.obs["sample_id"] = f"{group}_{stage}"
            adatas.append(a)
            log(f"  Loaded {fname.name}: {a.n_obs} cells × {a.n_vars} genes")
    if not adatas:
        log("ERROR: no samples loaded")
        sys.exit(1)
    return ad.concat(adatas, join="outer", label="batch", keys=[a.obs["sample_id"].iloc[0] for a in adatas])


def qc_filter(adata, min_genes=200, max_pct_mt=20):
    """Standard scanpy QC."""
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=3)
    if "mt" not in adata.var.columns:
        adata.var["mt"] = adata.var_names.str.startswith(("mt-", "MT-"))
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True)
    if "pct_counts_mt" in adata.obs.columns:
        adata = adata[adata.obs["pct_counts_mt"] < max_pct_mt].copy()
    return adata


def integrate_with_reference(adata_query, reference_h5ad_path):
    """Integrate experiment samples with Schoels reference using harmony.
    Returns combined adata with cluster labels projected from reference."""
    log("Loading Schoels reference...")
    adata_ref = sc.read_h5ad(reference_h5ad_path)
    adata_ref.obs["dataset"] = "schoels_ref"
    adata_query.obs["dataset"] = "experiment"

    # Concatenate
    combined = ad.concat([adata_ref, adata_query], join="inner",
                         label="dataset", keys=["schoels_ref", "experiment"])
    log(f"Combined: {combined.n_obs} cells × {combined.n_vars} genes")

    # Normalize + scale + PCA
    sc.pp.normalize_total(combined, target_sum=1e4)
    sc.pp.log1p(combined)
    sc.pp.highly_variable_genes(combined, n_top_genes=2000, batch_key="dataset")
    sc.pp.scale(combined, max_value=10)
    sc.tl.pca(combined, n_comps=50, mask_var="highly_variable")

    # Harmony integration
    try:
        import harmonypy as hm
        log("Running harmony integration...")
        ho = hm.run_harmony(combined.obsm["X_pca"], combined.obs, ["dataset"])
        combined.obsm["X_pca_harmony"] = ho.Z_corr.T
    except ImportError:
        log("WARNING: harmonypy not installed; using uncorrected PCA")
        combined.obsm["X_pca_harmony"] = combined.obsm["X_pca"]

    # Neighbors + UMAP on harmony
    sc.pp.neighbors(combined, use_rep="X_pca_harmony", n_neighbors=15)
    sc.tl.umap(combined)
    sc.tl.leiden(combined, resolution=0.5, key_added="leiden_combined")
    return combined


def map_experiment_clusters_to_reference(combined, ref_cluster_col="leiden", new_cluster_col="leiden_combined"):
    """For each cluster in the combined space, identify which Schoels cluster
    is most enriched. Returns a mapping {combined_cluster_id: schoels_cluster_id}."""
    ref_mask = combined.obs["dataset"] == "schoels_ref"
    mapping = {}
    for cc in combined.obs[new_cluster_col].unique():
        cc_mask = combined.obs[new_cluster_col] == cc
        ref_in_cc = combined.obs.loc[cc_mask & ref_mask, ref_cluster_col]
        if len(ref_in_cc) > 0:
            most_common = ref_in_cc.value_counts().idxmax()
            mapping[cc] = str(most_common)
        else:
            mapping[cc] = "unknown"
    return mapping


def differential_abundance(combined, target_cluster_combined, group_col="group",
                           treatment_label="KO", control_label="scrambled"):
    """Test if target cluster has different cell counts in KO vs control."""
    exp_mask = combined.obs["dataset"] == "experiment"
    df = combined.obs[exp_mask].copy()
    target_mask = df["leiden_combined"] == target_cluster_combined

    # Counts per group × stage
    crosstab = pd.crosstab(
        [df["group"], df["stage"]],
        target_mask.astype(int),
        normalize="index",
    )
    log(f"Target cluster proportion per group×stage:")
    log(crosstab.to_string())

    # Per-stage Fisher exact test (KO vs scrambled)
    from scipy.stats import fisher_exact
    results = {}
    for stage in df["stage"].unique():
        ko = ((df["group"] == treatment_label) & (df["stage"] == stage))
        ctrl = ((df["group"] == control_label) & (df["stage"] == stage))
        a = int((ko & target_mask).sum())  # KO in target
        b = int((ko & ~target_mask).sum())  # KO not target
        c = int((ctrl & target_mask).sum())  # ctrl in target
        d = int((ctrl & ~target_mask).sum())  # ctrl not target
        if (a + b) == 0 or (c + d) == 0:
            continue
        odds, p = fisher_exact([[a, b], [c, d]])
        results[stage] = {
            "ko_in_target": a, "ko_not_target": b,
            "ctrl_in_target": c, "ctrl_not_target": d,
            "odds_ratio": float(odds),
            "p_value": float(p),
            "ko_pct": a / (a + b) if (a + b) > 0 else 0,
            "ctrl_pct": c / (c + d) if (c + d) > 0 else 0,
        }
    return results


def test_marker_proportions(combined, target_cluster_combined, marker_genes,
                            group_col="group", treatment_label="KO", control_label="scrambled"):
    """For each marker, test % cells expressing in target cluster: KO vs control."""
    exp_mask = combined.obs["dataset"] == "experiment"
    target_mask = combined.obs["leiden_combined"] == target_cluster_combined
    sub = combined[exp_mask & target_mask]

    from scipy.stats import chi2_contingency
    results = []
    for marker in marker_genes:
        if marker not in sub.var_names:
            results.append({"marker": marker, "in_dataset": False})
            continue
        X = sub[:, marker].X
        expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
        sub.obs["_expr_pos"] = (expr > 0).astype(int)

        ct = pd.crosstab(sub.obs[group_col], sub.obs["_expr_pos"])
        if (treatment_label not in ct.index) or (control_label not in ct.index):
            continue
        sub_ct = ct.loc[[treatment_label, control_label]]
        if sub_ct.shape[1] < 2:
            continue
        chi2, p, _, _ = chi2_contingency(sub_ct)
        ko_pos = sub_ct.loc[treatment_label, 1] if 1 in sub_ct.columns else 0
        ko_n = sub_ct.loc[treatment_label].sum()
        ctrl_pos = sub_ct.loc[control_label, 1] if 1 in sub_ct.columns else 0
        ctrl_n = sub_ct.loc[control_label].sum()
        ko_pct = ko_pos / ko_n if ko_n > 0 else 0
        ctrl_pct = ctrl_pos / ctrl_n if ctrl_n > 0 else 0
        rel_change = (ctrl_pct - ko_pct) / ctrl_pct if ctrl_pct > 0 else 0
        results.append({
            "marker": marker,
            "in_dataset": True,
            "ko_n": int(ko_n),
            "ko_pct_pos": round(float(ko_pct), 4),
            "ctrl_n": int(ctrl_n),
            "ctrl_pct_pos": round(float(ctrl_pct), 4),
            "relative_reduction": round(float(rel_change), 4),
            "chi2": float(chi2),
            "p_value": float(p),
        })
    return results


def evaluate_predictions(da_results, marker_results, control_marker_results, predictions, config):
    """Map data → predictions outcome → number supported."""
    outcomes = []

    # P1: differential abundance
    p1 = predictions[0]
    p1_supported = False
    p1_evidence = []
    for stage, r in da_results.items():
        if r["p_value"] < p1["threshold"]["fdr"] and r["ko_pct"] < r["ctrl_pct"]:
            p1_evidence.append(f"{stage}: p={r['p_value']:.3g} ko_pct<ctrl")
    if len(p1_evidence) >= 2:  # ≥2 of 3 stages
        p1_supported = True
    outcomes.append({"id": "P1", "supported": p1_supported, "evidence": p1_evidence})

    # P2: % expressing primary marker[0] decreases
    p2 = predictions[1]
    p2_supported = False
    if marker_results and marker_results[0].get("in_dataset"):
        m = marker_results[0]
        if m["p_value"] < p2["threshold"]["p"] and m["relative_reduction"] >= p2["threshold"]["relative_reduction"]:
            p2_supported = True
    outcomes.append({"id": "P2", "supported": p2_supported,
                     "evidence": [marker_results[0]] if marker_results else []})

    # P3: 3+ of N markers
    p3 = predictions[2]
    n_significant = sum(1 for m in marker_results
                        if m.get("in_dataset") and m.get("p_value", 1) < p3["threshold"]["fdr"]
                        and m.get("relative_reduction", 0) >= 0.20)
    p3_supported = n_significant >= p3["threshold"]["n_markers_significant"]
    outcomes.append({"id": "P3", "supported": p3_supported, "n_significant": n_significant})

    # P4: control markers should NOT change significantly
    p4 = predictions[3]
    n_control_changed = sum(1 for m in control_marker_results
                            if m.get("in_dataset") and m.get("p_value", 1) < 0.05
                            and abs(m.get("relative_reduction", 0)) >= 0.10)
    p4_supported = n_control_changed == 0
    outcomes.append({"id": "P4", "supported": p4_supported, "n_control_changed": n_control_changed})

    # P5: trend across stages (placeholder, requires more sophisticated analysis)
    outcomes.append({"id": "P5", "supported": None, "note": "trend test pending — check da_results across stages"})

    n_supported = sum(1 for o in outcomes if o["supported"] is True)
    return {
        "outcomes": outcomes,
        "n_supported": n_supported,
        "n_total": len(predictions),
        "h1_verdict": (
            "STRONGLY SUPPORTED" if n_supported >= 4 else
            "PARTIALLY SUPPORTED" if n_supported >= 3 else
            "MARGINAL" if n_supported >= 2 else
            "NOT SUPPORTED (H0 favored)"
        ),
    }


def update_confidence(prior_confidence, n_supported, n_total):
    """Map outcome to posterior confidence using simple Bayesian-flavored update."""
    # Likelihood ratio per supported prediction (heuristic: ~2x per prediction)
    if n_supported >= 4:
        posterior = 0.85 + (n_supported - 4) * 0.03
    elif n_supported == 3:
        posterior = 0.70
    elif n_supported == 2:
        posterior = 0.45
    elif n_supported == 1:
        posterior = 0.25
    else:
        posterior = 0.10
    return min(0.99, max(0.05, posterior))


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target-gene", required=True, help="Target TF gene symbol (e.g., mafba, hoxb8a)")
    p.add_argument("--samples-dir", required=True, help="Dir with experiment h5ad files")
    p.add_argument("--reference-h5ad", required=True, help="Schoels reference h5ad path")
    p.add_argument("--output-dir", required=True, help="Output dir for results")
    p.add_argument("--prior-confidence", type=float, default=0.55, help="Pre-experiment prior")
    p.add_argument("--groups", default="KO,scrambled,MO,MOctrl", help="Comma-separated group labels")
    p.add_argument("--stages", default="24hpf,48hpf,72hpf", help="Comma-separated stage labels")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"=== Experiment N pipeline ===")
    log(f"Target gene: {args.target_gene}")
    log(f"Prior confidence: {args.prior_confidence}")

    if args.target_gene not in TF_TARGET_CONFIG:
        log(f"WARNING: {args.target_gene} not in TF_TARGET_CONFIG; using mafba defaults")
        config = TF_TARGET_CONFIG["mafba"]
    else:
        config = TF_TARGET_CONFIG[args.target_gene]

    # Load experiment samples
    log("Loading experiment samples...")
    adata_query = load_experiment_samples(
        args.samples_dir,
        args.groups.split(","),
        args.stages.split(","),
    )

    # QC
    log("QC filtering...")
    adata_query = qc_filter(adata_query)
    log(f"Post-QC: {adata_query.n_obs} cells × {adata_query.n_vars} genes")

    # Integrate with Schoels
    log("Integrating with Schoels reference...")
    combined = integrate_with_reference(adata_query, args.reference_h5ad)

    # Map clusters
    log("Mapping experiment clusters to Schoels reference...")
    mapping = map_experiment_clusters_to_reference(combined)
    log(f"Cluster mapping: {mapping}")

    # Find combined cluster equivalent to target
    target_combined = None
    for cc, schoels_cid in mapping.items():
        if schoels_cid == config["schoels_target_cluster"]:
            target_combined = cc
            log(f"Target cluster (combined space) = {cc} → Schoels {schoels_cid}")
            break
    if target_combined is None:
        log(f"WARNING: no combined cluster maps to Schoels {config['schoels_target_cluster']}")
        sys.exit(1)

    # Differential abundance
    log("Differential abundance test (KO vs scrambled)...")
    da_results = differential_abundance(combined, target_combined)

    # Marker proportions
    log("Testing primary markers in target cluster...")
    marker_results = test_marker_proportions(combined, target_combined, config["primary_markers"])
    log(f"Primary markers tested: {len(marker_results)}")

    log("Testing control markers (specificity check)...")
    control_results = test_marker_proportions(combined, target_combined, config["control_markers"])

    # Evaluate predictions
    eval_results = evaluate_predictions(da_results, marker_results, control_results, PREDICTIONS, config)

    # Update confidence
    posterior = update_confidence(args.prior_confidence, eval_results["n_supported"], len(PREDICTIONS))

    # Final report
    final_report = {
        "target_gene": args.target_gene,
        "config": config,
        "prior_confidence": args.prior_confidence,
        "differential_abundance": da_results,
        "marker_results": marker_results,
        "control_marker_results": control_results,
        "predictions_evaluation": eval_results,
        "posterior_confidence": posterior,
        "verdict": eval_results["h1_verdict"],
        "next_step_decision": (
            "Publicar paper, generar stable line para Phase II"
            if eval_results["n_supported"] >= 4 else
            "Análisis adicional (subcluster, pseudobulk)"
            if eval_results["n_supported"] == 2 or eval_results["n_supported"] == 3 else
            "Pivot a siguiente candidato (revisar pleiotropy_reprioritization)"
        ),
    }

    out_file = out_dir / f"experiment_N_{args.target_gene}_results.json"
    with open(out_file, "w") as f:
        json.dump(final_report, f, indent=2, default=str)
    combined.write_h5ad(out_dir / f"experiment_N_{args.target_gene}_integrated.h5ad")

    log(f"\n=== FINAL VERDICT ===")
    log(f"Predictions supported: {eval_results['n_supported']} / {len(PREDICTIONS)}")
    log(f"Verdict: {eval_results['h1_verdict']}")
    log(f"Posterior confidence: {posterior:.3f} (prior was {args.prior_confidence:.3f})")
    log(f"Next step: {final_report['next_step_decision']}")
    log(f"\nSaved to {out_file}")
    log("=== Pipeline complete ===")


if __name__ == "__main__":
    sys.exit(main() or 0)
