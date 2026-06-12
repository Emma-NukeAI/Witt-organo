"""
backfill_raw_refs.py — attach provenance-to-raw (raw_ref) to the existing corpus records (GWT v1.1, ADR-0021).

HYBRID policy: ZESTA (CNGB) + GSE218068 (GEO) are PUBLIC, so their raw_ref is a SOURCE-POINTER
(canonical URL + sha256 computed from the local cached copy) — bytes are NOT mirrored. Going forward,
add_dataset.py produces raw_ref at ingest time; this is the one-time backfill for the two seed records.

NO new downloads. Run:  python analysis/scripts/lib/backfill_raw_refs.py
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import raw_store  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
CACHE = ROOT / "mcp_cache"
ZDIR = CACHE / "zesta"
CNGB = "https://ftp.cngb.org/pub/SciRAID/stomics/STDS0000057"
GEO = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE218nnn/GSE218068/suppl"


def zesta_source_url(fname):
    sub = "scrna" if "scRNA" in fname else "stomics"   # stereoseq + spatial live under stomics/
    return f"{CNGB}/{sub}/{fname}"


def main():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {r["corpus_record_id"]: r for r in man["records"]}

    # --- CORPUS-2026-0001 (ZESTA): one source-pointer per downloaded file ---
    z = by_id["CORPUS-2026-0001"]
    zrefs = []
    for p in sorted(ZDIR.glob("*.h5ad")):
        print(f"  hashing {p.name} ({p.stat().st_size/1048576:.0f} MB)...")
        ref = raw_store.source_pointer(zesta_source_url(p.name), path=p, content_type="application/x-hdf5")
        ref["filename"] = p.name
        zrefs.append(ref)
    z["raw_provenance"] = {"policy": "hybrid: public source-pointer (not mirrored)",
                           "store_for_private": "minio (data-inamovible-raw) when private/derived",
                           "n_files": len(zrefs), "files": zrefs,
                           "note": "fetch_raw resolves these to the CNGB source_url + sha256 for on-demand re-download"}
    # link each processed-file entry to its raw_ref by filename
    sha_by_name = {r["filename"]: r["sha256"] for r in zrefs}
    for fp in z.get("files_processed", []):
        fp["raw_ref"] = {"mode": "source-pointer", "source_url": zesta_source_url(fp["file"]),
                         "sha256": sha_by_name.get(fp["file"])}

    # --- CORPUS-2026-0002 (GSE218068): source-pointer for the 10x outs ---
    g = by_id["CORPUS-2026-0002"]
    gmap = {"GSE218068_aggr_matrix.mtx.gz": "GSE218068_Foxc1b_aggregation_outs_matrix.mtx.gz",
            "GSE218068_aggr_barcodes.tsv.gz": "GSE218068_Foxc1b_aggregation_outs_barcodes.tsv.gz",
            "GSE218068_aggr_features.tsv.gz": "GSE218068_Foxc1b_aggregation_outs_features.tsv.gz"}
    grefs = []
    for local, remote in gmap.items():
        p = CACHE / local
        if not p.exists():
            continue
        print(f"  hashing {local} ({p.stat().st_size/1048576:.0f} MB)...")
        ref = raw_store.source_pointer(f"{GEO}/{remote}", path=p,
                                       content_type="application/gzip")
        ref["filename"] = remote
        grefs.append(ref)
    g["raw_provenance"] = {"policy": "hybrid: public source-pointer (not mirrored)",
                           "n_files": len(grefs), "files": grefs,
                           "note": "10x aggregated outs at GEO; fetch_raw -> source_url + sha256"}

    man["manifest_version"] = "2026-06-12.4"
    man["status"] = ("Provenance-to-raw added (raw_ref, hybrid source-pointer for public ZESTA+GSE218068). "
                     "Graph is the guide; fetch_raw drills to the raw. Human-gated.")
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n[backfill] ZESTA: {len(zrefs)} file pointers | GSE218068: {len(grefs)} file pointers")
    print("  manifest_version -> 2026-06-12.4")


if __name__ == "__main__":
    main()
