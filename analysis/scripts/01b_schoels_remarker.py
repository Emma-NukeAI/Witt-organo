"""
01b_schoels_remarker.py — Recovery step for the 2026-06-10 ID-corruption finding.

Re-reports the canonical + segment pronephros markers from the EXISTING QC'd AnnData
(analysis/outputs/schoels_qc.h5ad) using the CORRECT ENSDARG IDs resolved from the
verified-identifier store (DATA INAMOVIBLE v1) via resolve_id.require().

Why this is faithful AND light: the QC + normalize steps in 01_schoels_analysis.py do NOT
depend on the marker IDs (markers are read only at report time). Re-reporting from the
unaffected schoels_qc.h5ad reproduces exactly the marker CSVs a fresh full run would write,
without re-running the scanpy pipeline. See docs/findings/2026-06-10-schoels-phase1-id-corruption.md.

Outputs:
  analysis/outputs/schoels_markers_{canonical,segment}.csv   (corrected; overwrites the absent
      live versions — the corrupted 2026-05-08 ones are preserved under _superseded/, ADR-0002)
  analysis/outputs/schoels_remarker_diff_20260611.json       (before/after per-marker diff)
"""
from pathlib import Path
import sys
import json

import numpy as np
import pandas as pd
import anndata as ad

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.resolve_id import require  # noqa: E402

OUT_DIR = Path("analysis/outputs")
H5AD = OUT_DIR / "schoels_qc.h5ad"
SUPERSEDED = OUT_DIR / "_superseded"

CANONICAL_SYMBOLS = ["wt1a", "pax2a", "pax8", "hnf1ba", "hnf1bb"]
SEGMENT_SYMBOLS = ["podxl", "nphs1", "nphs2", "slc20a1a", "slc4a4a", "trpm7",
                   "slc12a1", "kcnj1a.1", "slc12a3", "gata3", "cdh17"]
CANONICAL_MARKERS = {s: require(s).ensdarg for s in CANONICAL_SYMBOLS}
SEGMENT_MARKERS = {s: require(s).ensdarg for s in SEGMENT_SYMBOLS}


def report_marker(adata, name, ens_id):
    if ens_id not in adata.var_names:
        return {"marker": name, "ens_id": ens_id, "found": False, "n_cells_expressing": 0,
                "pct_expressing": 0.0, "mean_expr": 0.0, "max_expr": 0.0, "reason": "id_not_in_var_names"}
    X = adata[:, ens_id].X
    expr = X.toarray().flatten() if hasattr(X, "toarray") else np.asarray(X).flatten()
    n_pos = int((expr > 0).sum())
    return {"marker": name, "ens_id": ens_id, "found": True, "n_cells_expressing": n_pos,
            "pct_expressing": float(n_pos / len(expr) * 100), "mean_expr": float(expr.mean()),
            "max_expr": float(expr.max()), "reason": ""}


def report_per_day(adata, name, ens_id):
    rows = []
    for day in adata.obs["day"].unique():
        sub = adata[adata.obs["day"] == day]
        rec = report_marker(sub, name, ens_id)
        rec["day"] = day
        rec["n_cells_in_day"] = sub.n_obs
        rows.append(rec)
    return rows


def build_df(adata, markers):
    rows = []
    for name, ens in markers.items():
        rows.append({**report_marker(adata, name, ens), "scope": "all"})
        for r in report_per_day(adata, name, ens):
            rows.append({**r, "scope": r["day"]})
    return pd.DataFrame(rows)


def load_old(stem):
    p = SUPERSEDED / f"{stem}.20260508.csv"
    return pd.read_csv(p) if p.exists() else None


def main():
    print(f"[remarker] loading {H5AD}")
    adata = ad.read_h5ad(H5AD)
    print(f"[remarker] cells={adata.n_obs} genes={adata.n_vars}")

    canonical_df = build_df(adata, CANONICAL_MARKERS)
    segment_df = build_df(adata, SEGMENT_MARKERS)
    canonical_df.to_csv(OUT_DIR / "schoels_markers_canonical.csv", index=False)
    segment_df.to_csv(OUT_DIR / "schoels_markers_segment.csv", index=False)

    new_all = pd.concat([canonical_df, segment_df])
    new_all = new_all[new_all.scope == "all"].set_index("marker")
    old_parts = [x for x in (load_old("schoels_markers_canonical"),
                             load_old("schoels_markers_segment")) if x is not None]
    old_all = pd.concat(old_parts) if old_parts else pd.DataFrame()
    if not old_all.empty:
        old_all = old_all[old_all.scope == "all"].set_index("marker")

    diff_rows = []
    for marker in new_all.index:
        n = new_all.loc[marker]
        o = old_all.loc[marker] if (not old_all.empty and marker in old_all.index) else None
        old_ens = (o["ens_id"] if o is not None else None)
        new_ens = n["ens_id"]
        old_found = bool(o["found"]) if o is not None else False
        new_found = bool(n["found"])
        old_pct = float(o["pct_expressing"]) if o is not None else 0.0
        new_pct = float(n["pct_expressing"])
        id_was_wrong = (old_ens != new_ens)
        if not id_was_wrong:
            status = "unchanged_correct"
        elif old_found and not new_found:
            status = "corrected_false_positive_now_absent"
        elif old_found and new_found:
            status = "corrected_false_positive_reattributed"
        elif (not old_found) and new_found:
            status = "recovered_false_negative"
        else:
            status = "still_absent_check"
        diff_rows.append({"marker": marker, "old_ens": old_ens, "new_ens": new_ens,
                          "id_was_wrong": bool(id_was_wrong), "old_found": old_found,
                          "new_found": new_found, "old_pct": round(old_pct, 3),
                          "new_pct": round(new_pct, 3), "status": status})
    diff_df = pd.DataFrame(diff_rows)

    n_recovered = int((diff_df.status == "recovered_false_negative").sum())
    n_corrected_fp = int(diff_df.status.str.startswith("corrected_false_positive").sum())
    n_now_found = int(diff_df.new_found.sum())
    summary = {
        "h5ad": str(H5AD),
        "n_markers": int(len(diff_df)),
        "n_now_found": n_now_found,
        "n_recovered_false_negatives": n_recovered,
        "n_corrected_false_positives": n_corrected_fp,
        "per_marker": diff_rows,
    }
    (OUT_DIR / "schoels_remarker_diff_20260611.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(diff_df.to_string(index=False))
    print(f"\n[remarker] now_found={n_now_found}/16 | recovered_false_negatives={n_recovered} | "
          f"corrected_false_positives={n_corrected_fp}")
    print("[remarker] wrote corrected CSVs + schoels_remarker_diff_20260611.json")


if __name__ == "__main__":
    main()
