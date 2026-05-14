#!/usr/bin/env python
"""
prepare_data.py — convert CSV/TSV scRNA-seq files into AnnData h5ad format.

Usage:
  python prepare_data.py --input data.csv --output data.h5ad
  python prepare_data.py --input data.csv --output data.h5ad --transpose

Expected input layouts:
  Layout 1 (cells as rows, default):
    ,GENE_A,GENE_B,GENE_C,cell_type,timepoint
    cell_1,3.2,0.5,1.8,iPSC,day_0
    cell_2,2.9,0.1,2.0,iPSC,day_0
    ...

  Layout 2 (genes as rows, use --transpose):
    ,cell_1,cell_2,cell_3
    GENE_A,3.2,2.9,1.5
    ...

Metadata columns (string or categorical) get moved to obs. Numeric columns
are treated as gene expression. Cell IDs come from the index column.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

try:
    import anndata as ad
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"[prepare_data] FATAL: missing dependency ({e}). Run setup_environment.sh.",
          file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--transpose", action="store_true", help="Genes as rows (default cells as rows)")
    ap.add_argument("--separator", default=None, help="Override auto-detected separator")
    args = ap.parse_args()

    inp = Path(args.input)
    sep = args.separator or ("\t" if inp.suffix.lower() == ".tsv" else ",")

    df = pd.read_csv(str(inp), sep=sep, index_col=0)
    if args.transpose:
        df = df.T

    # Detect metadata vs gene columns
    meta_cols = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) == "category"]
    gene_cols = [c for c in df.columns if c not in meta_cols]

    if not gene_cols:
        print("[prepare_data] ERROR: No numeric gene columns found.", file=sys.stderr)
        print("[prepare_data] Hint: maybe try --transpose, or check for stray string columns.", file=sys.stderr)
        sys.exit(1)

    X = df[gene_cols].values.astype(float)
    obs = df[meta_cols].copy() if meta_cols else pd.DataFrame(index=df.index)
    obs.index = df.index.astype(str)

    adata = ad.AnnData(X=X, obs=obs)
    adata.var_names = gene_cols

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)

    print(f"[prepare_data] Wrote {args.output}")
    print(f"[prepare_data] Shape: {adata.n_obs} cells × {adata.n_vars} genes")
    print(f"[prepare_data] Metadata columns: {list(obs.columns)}")


if __name__ == "__main__":
    main()
