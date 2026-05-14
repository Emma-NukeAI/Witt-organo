#!/usr/bin/env python
"""
synthetic_fallback.py — Mode 0, the conceptual proxy.

Generates synthetic scRNA-seq driven by canonical marker biology for the
specified system, applies a PCA-based proxy of the Squidiff operations,
and emits the same metrics JSON format as run_inference.py.

The skill should fall back to this when:
  - User has no real data (hypothesis-only request)
  - Mode 1 setup fails (dependencies not installed, weights unavailable)
  - User explicitly requests Mode 0

Honesty:
  - This is NOT real Squidiff. It's a methodology demonstrator.
  - Confidence is capped at 0.50 in the verdict layer.
  - Every output of this script carries the flag mode="0_synthetic_proxy".
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np


# Marker sets per system (see references/synthetic-data.md)
MARKER_SETS = {
    "pronephros": {
        "pluripotent":   ["nanog", "pou5f1", "sox2"],
        "lateral_plate": ["hand2", "gata4", "gata6"],
        "renal_prog":    ["wt1a", "wt1b", "pax2a", "pax8", "lhx1a"],
        "tubule":        ["cdh17", "slc20a1a", "gata3"],
        "glomerulus":    ["nphs1", "nphs2", "podxl"],
        "stress":        ["cdkn1a", "gdf15", "atf3"],
        "yap_targets":   ["ctgfa", "cyr61", "amotl2a"],
    },
    "bvo": {
        "pluripotent": ["NANOG", "POU5F1"],
        "endothelial": ["CDH5", "CLDN5", "PECAM1", "KDR", "SOX17"],
        "mural":       ["ACTA2", "MYH11", "PDGFRB"],
        "fibroblast":  ["COL1A1", "COL3A1", "LUM", "DCN"],
        "stress":      ["CDKN1A", "MDM2", "GDF15"],
        "yap_targets": ["CTGF", "CYR61"],
    },
    "ipsc_diff": {
        "pluripotent":         ["NANOG", "POU5F1", "SOX2"],
        "mesendoderm":         ["T", "EOMES", "MIXL1"],
        "definitive_endoderm": ["SOX17", "FOXA2", "GATA6"],
    },
    "generic": {
        "state_a": ["STATE_A_1", "STATE_A_2", "STATE_A_3"],
        "state_b": ["STATE_B_1", "STATE_B_2", "STATE_B_3"],
        "state_c": ["STATE_C_1", "STATE_C_2", "STATE_C_3"],
    },
}


def generate_synthetic(system: str, n_states: int = 2, n_cells_per: int = 300, seed: int = 42):
    """Generate a synthetic AnnData-like dict."""
    rng = np.random.default_rng(seed)
    markers = MARKER_SETS.get(system, MARKER_SETS["generic"])
    state_names = list(markers.keys())[:n_states] if n_states <= len(markers) else list(markers.keys())
    n_states = len(state_names)

    # Build gene list: marker genes + 100 baseline
    all_markers = []
    for k in state_names:
        all_markers.extend(markers[k])
    # Add markers from other state types for context (stress, yap)
    extras = []
    for k, v in markers.items():
        if k not in state_names:
            extras.extend(v)
    gene_names = all_markers + extras + [f"G{i:03d}" for i in range(100)]
    n_genes = len(gene_names)

    matrix = np.zeros((n_states * n_cells_per, n_genes))
    labels = []
    for si, state_name in enumerate(state_names):
        state_marker_idxs = [gene_names.index(g) for g in markers[state_name]]
        for c in range(n_cells_per):
            row = rng.normal(0.5, 0.3, n_genes).clip(0)
            # Elevate this state's markers
            for gi in state_marker_idxs:
                row[gi] = rng.normal(3.5, 0.5)
            # Add structure to baseline genes
            for bi in range(len(gene_names) - 100, len(gene_names)):
                row[bi] = max(0, 1 + 0.6 * np.sin(si * 0.7 + bi * 0.1) + 0.3 * rng.normal())
            matrix[si * n_cells_per + c] = row
        labels.extend([state_name] * n_cells_per)

    return matrix, np.array(labels), gene_names, state_names


def pca_2d(X):
    Xc = X - X.mean(axis=0, keepdims=True)
    U, S, _ = np.linalg.svd(Xc, full_matrices=False)
    return U[:, :2] * S[:2]


def run_addition_proxy(matrix, labels, gene_names, source_label, target_label):
    """PCA-based proxy of the addition operation."""
    src_mask = labels == source_label
    tgt_mask = labels == target_label
    X_src = matrix[src_mask]
    X_tgt = matrix[tgt_mask]

    # Top variable genes for PCA
    var_per_gene = matrix.var(axis=0)
    top_genes = np.argsort(var_per_gene)[-30:]
    Z_all = pca_2d(matrix[:, top_genes])
    z_src = Z_all[src_mask].mean(axis=0)
    z_tgt = Z_all[tgt_mask].mean(axis=0)
    delta_norm = float(np.linalg.norm(z_tgt - z_src))

    # "Predicted" perturbed = source mean + delta in gene space
    mean_src = X_src.mean(axis=0)
    mean_tgt = X_tgt.mean(axis=0)
    mean_pred = mean_src + (mean_tgt - mean_src) * 0.9  # imperfect proxy

    pearson_r = float(np.corrcoef(mean_pred, mean_tgt)[0, 1])
    r2 = pearson_r ** 2

    true_dir = np.sign(mean_tgt - mean_src)
    pred_dir = np.sign(mean_pred - mean_src)
    abs_change = np.abs(mean_tgt - mean_src)
    top_idx = np.argsort(abs_change)[-20:]
    direction_acc = float((true_dir[top_idx] == pred_dir[top_idx]).mean())

    return {
        "operation": "addition",
        "pearson_r": pearson_r,
        "r_squared": r2,
        "directional_accuracy_top20_de": direction_acc,
        "delta_zsem_norm": delta_norm,
        "n_source": int(X_src.shape[0]),
        "n_target": int(X_tgt.shape[0]),
        "n_genes": len(gene_names),
        "latent_pca": {
            "source": Z_all[src_mask].tolist()[:200],
            "target": Z_all[tgt_mask].tolist()[:200],
            "predicted": (Z_all[src_mask] + (z_tgt - z_src)).tolist()[:200],
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypothesis", default="(unspecified)")
    ap.add_argument("--operation", default="addition",
                    choices=["interpolation", "addition"])
    ap.add_argument("--system", default="generic")
    ap.add_argument("--source-label", default=None)
    ap.add_argument("--target-label", default=None)
    ap.add_argument("--seed", type=int, default=42,
                    help="PRNG seed for reproducibility. Same seed → identical output. Default 42.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    matrix, labels, gene_names, state_names = generate_synthetic(args.system, seed=args.seed)
    src = args.source_label or state_names[0]
    tgt = args.target_label or state_names[-1]

    if args.operation == "addition":
        metrics = run_addition_proxy(matrix, labels, gene_names, src, tgt)
    else:
        # Interpolation proxy — minimal: just report latent positions
        Z_all = pca_2d(matrix[:, np.argsort(matrix.var(axis=0))[-30:]])
        metrics = {
            "operation": "interpolation",
            "fractions": [0.25, 0.5, 0.75],
            "delta_zsem_norm": float(np.linalg.norm(
                Z_all[labels == tgt].mean(axis=0) - Z_all[labels == src].mean(axis=0))),
            "latent_pca": {
                "source_mean": Z_all[labels == src].mean(axis=0).tolist(),
                "target_mean": Z_all[labels == tgt].mean(axis=0).tolist(),
                "coords": Z_all.tolist()[:500],
            },
        }

    metrics["mode"] = "0_synthetic_proxy"
    metrics["hypothesis"] = args.hypothesis
    metrics["system"] = args.system
    metrics["seed"] = args.seed
    metrics["checkpoint"] = {"tag": "Mode 0 PCA proxy (no real model)",
                             "transfer_distance": "n/a"}
    metrics["warning"] = ("This is a methodology proxy, not real Squidiff. "
                          "Confidence capped at 0.50. "
                          f"Deterministic (seed={args.seed}) — same input produces same output. "
                          "Recommend escalating to Mode 1 with real data.")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"[synthetic_fallback] Wrote synthetic metrics to {args.out}")


if __name__ == "__main__":
    main()
