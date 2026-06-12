"""
process_zesta.py — extract verified entities + per-timepoint metadata from the full ZESTA atlas (GWT v1.1).

Reads the downloaded ZESTA .h5ad files (mcp_cache/zesta/, gitignored) in anndata backed='r' mode so the
big count matrices stay on disk (only var/obs are loaded). For each file it gathers candidate gene symbols
(var_names + symbol-like .var columns), runs them through the deterministic entity gate (resolve_id), and
keeps the verified subset. It aggregates the union across all timepoints + per-file metadata (timepoint,
modality, n_obs, obs annotations) and updates CORPUS-2026-0001 in the manifest. IDs come ONLY from
resolve_id — none minted. Files that fail to open (truncated download) are skipped + recorded.

NO new downloads. Run with a python that has anndata (system python):
  python analysis/scripts/lib/process_zesta.py
"""
import sys
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import resolve_id  # noqa: E402

ZESTA = ROOT / "mcp_cache" / "zesta"
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
MANIFEST_VERSION = "2026-06-12.3"
SYM_COLS = ("gene_name", "gene_short_name", "symbol", "real_gene_name", "gene_symbol", "features", "Gene")


def _timepoint(fname):
    m = re.search(r"zf(\d+)_", fname)
    if m:
        return [int(m.group(1))]
    if "sixtime" in fname:
        return [3, 5, 10, 12, 18, 24]
    return []


def _candidates(adata):
    """All symbol-like strings to feed the gate: var_names + any symbol-ish var column."""
    cands = set(map(str, adata.var_names))
    try:
        for c in adata.var.columns:
            if c in SYM_COLS or "name" in c.lower() or "symbol" in c.lower():
                cands.update(map(str, adata.var[c].astype(str).tolist()))
    except Exception:
        pass
    return cands


def main():
    import anndata
    files = sorted(p for p in ZESTA.glob("*.h5ad"))
    NF = resolve_id.NOT_FOUND
    per_file, present_count, ent_meta, skipped = [], {}, {}, []

    for p in files:
        try:
            ad = anndata.read_h5ad(p, backed="r")
        except Exception as e:
            skipped.append({"file": p.name, "error": f"{type(e).__name__}: {str(e)[:80]}"})
            print(f"  [skip] {p.name}: {type(e).__name__} (incomplete/corrupt)")
            continue
        cands = _candidates(ad)
        hits = {}
        for s in cands:
            r = resolve_id.resolve(s)
            if r is not NF:
                hits[r.symbol] = r
        for sym, r in hits.items():
            present_count[sym] = present_count.get(sym, 0) + 1
            ent_meta[sym] = (r.ensdarg, "RAW" if r.is_raw_verified else "DERIVED")
        modality = "stereoseq (spatial)" if "stereoseq" in p.name else "scRNA"
        obs_keys = list(map(str, ad.obs.columns))[:12]
        per_file.append({"file": p.name, "timepoint_hpf": _timepoint(p.name), "modality": modality,
                         "n_obs": int(ad.n_obs), "n_vars": int(ad.n_vars),
                         "verified_entities": len(hits), "obs_columns": obs_keys,
                         "size_mb": round(p.stat().st_size / 1048576, 1)})
        print(f"  {p.name:42s} {modality:18s} n_obs={ad.n_obs:>7} vars={ad.n_vars:>6} verified={len(hits)}")
        try:
            ad.file.close()
        except Exception:
            pass

    entities = [{"entity": s, "type": "gene_symbol",
                 "verified_store_ref": f"verified_identifiers.json#{s}",
                 "store_ensdarg": ent_meta[s][0], "verification_tier": ent_meta[s][1],
                 "n_files_present": present_count[s]} for s in sorted(present_count)]
    total_obs = sum(f["n_obs"] for f in per_file)
    raw_n = sum(1 for e in entities if e["verification_tier"] == "RAW")

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rec = next(r for r in man["records"] if r["corpus_record_id"] == "CORPUS-2026-0001")
    prior = len(rec.get("entities_extracted", []))
    rec["entities_extracted"] = entities
    rec["files_processed"] = per_file
    rec["read_summary"] = {
        "source": "ZESTA full atlas (CNGB STDS0000057): 13 .h5ad, 4.84 GB, mcp_cache/zesta/ (gitignored)",
        "files_read": len(per_file), "files_skipped": len(skipped),
        "total_obs_spots_plus_cells": total_obs,
        "timepoints_hpf": [3, 5, 10, 12, 18, 24],
        "modalities": ["stereoseq (spatial)", "scRNA"],
        "verified_entities": len(entities), "verified_RAW": raw_n,
        "note": "var_names + symbol columns run through resolve_id (the gate); union across all timepoints.",
    }
    flags = ["spatial modality (Stereo-seq) is now downloaded; RN9 spatial-transcriptomics analysis path not yet built",
             f"{len(entities)} verified entities (union across timepoints); the dataset's full gene namespace "
             f"(~16-26k) far exceeds the store — only store-verified genes become entities (none minted)"]
    if skipped:
        flags.append("incomplete files (re-download): " + ", ".join(s["file"] for s in skipped))
    rec["gap_flags"] = flags
    rec["audit"] = {"prior_categorization": f"{prior} entities (from the 5 hpf representative slice only)",
                    "proposed_recategorization": f"{len(entities)} verified entities across the full 13-file atlas "
                                                 f"({len(per_file)} files read, {len(skipped)} skipped)",
                    "reason": "full 4.84 GB atlas downloaded (Emmanuel approved); var_names re-bound via resolve_id",
                    "by": "process_zesta.py + anndata (backed) + resolve_id", "at": "2026-06-12"}

    man["manifest_version"] = MANIFEST_VERSION
    man["status"] = (f"ZESTA full atlas processed ({len(per_file)}/{len(files)} files, {total_obs} spots+cells, "
                     f"{len(entities)} verified entities). GSE218068 carries real expression. Human-gated.")
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n[process_zesta] {len(per_file)} files read ({len(skipped)} skipped) | {total_obs} spots+cells")
    print(f"  CORPUS-2026-0001 entities: {prior} -> {len(entities)} ({raw_n} RAW)")
    if skipped:
        print("  skipped:", ", ".join(s["file"] for s in skipped))
    print(f"  manifest_version -> {MANIFEST_VERSION}")


if __name__ == "__main__":
    main()
