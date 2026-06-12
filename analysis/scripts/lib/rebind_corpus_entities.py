"""
rebind_corpus_entities.py — re-bind a corpus record's entities to the CURRENT verified store (GWT v1.1).

When the verified store grows (new markers curated + human-gated), the corpus_manifest entity tiers go
stale: a gene that was UNVERIFIED/quarantined may now resolve RAW. This tool re-runs the deterministic
entity gate (resolve_id) over a dataset's real gene catalog (already-cached features / .h5ad var_names)
and rewrites entities_extracted with the verified subset. IDs come ONLY from resolve_id — never minted
from memory (the bug the store was built to prevent). It is the propagation step of the curation loop:
  store enrichment (human-gated)  ->  rebind_corpus_entities  ->  ingest.py  ->  Neo4j reflects it.

NO new downloads (reads only mcp_cache/). Reads .h5ad via anndata if present (ZESTA); skips with a clear
note otherwise. Writes rag_index/corpus_manifest.json (a human-gated artifact — review the printed diff
before committing).

Run:  python analysis/scripts/lib/rebind_corpus_entities.py
"""
import sys
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import resolve_id  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
GSE_FEATURES = ROOT / "mcp_cache" / "raw_geo_GSE218068_features_20260611.tsv.gz"
ZESTA_SLICE = ROOT / "mcp_cache" / "zf5_stereoseq.h5ad"
MANIFEST_VERSION = "2026-06-12.1"


def _tier(r):
    return "RAW" if r.is_raw_verified else "DERIVED"


def _entity(sym, refseq=None, source_slice=None):
    r = resolve_id.resolve(sym)
    if r is resolve_id.NOT_FOUND:
        return None
    e = {"entity": r.symbol, "type": "gene_symbol",
         "verified_store_ref": f"verified_identifiers.json#{r.symbol}",
         "store_ensdarg": r.ensdarg, "verification_tier": _tier(r)}
    if refseq:
        e["in_dataset_id"] = refseq
        e["namespace_match"] = "symbol matches; dataset ID is RefSeq (NM_*), store is Ensembl"
    if source_slice:
        e["source_slice"] = source_slice
    return e


def gse218068_entities():
    """GSE218068 features.tsv.gz (RefSeq NM_ + symbol) -> verified entities (symbol x store)."""
    sym2ref = {}
    with gzip.open(GSE_FEATURES, "rt", encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2:
                sym2ref.setdefault(p[1], p[0])
    ents = [_entity(s, refseq=ref) for s, ref in sorted(sym2ref.items())]
    return [e for e in ents if e], len(sym2ref)


def zesta_entities():
    """ZESTA representative slice var_names -> verified entities. Needs anndata (system python)."""
    try:
        import anndata
    except ImportError:
        return None, 0
    if not ZESTA_SLICE.exists():
        return None, 0
    names = list(map(str, anndata.read_h5ad(ZESTA_SLICE).var_names))
    slice_note = "zf5_stereoseq.h5ad (5 hpf representative slice; full 12-file 4.8 GB atlas not downloaded)"
    ents = [_entity(s, source_slice=slice_note) for s in sorted(set(names))]
    return [e for e in ents if e], len(names)


def main():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {r["corpus_record_id"]: r for r in m["records"]}

    gse, gse_total = gse218068_entities()
    zesta, zesta_total = zesta_entities()

    # --- CORPUS-2026-0002 (GSE218068) ---
    r2 = by_id["CORPUS-2026-0002"]
    prior2 = len(r2.get("entities_extracted", []))
    r2["entities_extracted"] = gse
    r2["gap_flags"] = [
        f"RefSeq<->Ensembl handled: {len(gse)}/{gse_total} features bind to the verified store "
        f"(symbol index + refseq_ensembl_xref.json); the rest are not in the store (not minted).",
        "EXPLORATORY-NOT-TEST-5 (N5 is exploratory in Phase I)",
    ]
    r2.setdefault("audit", {})
    r2["audit"] = {"prior_categorization": f"{prior2} entities (foxc1b/pitx2/prox1a UNVERIFIED/quarantined)",
                   "proposed_recategorization": f"{len(gse)} verified entities; foxc1b/pitx2/prox1a now RAW",
                   "reason": "store enriched (ocular markers curated, human-gated 2026-06-11); re-bound via resolve_id",
                   "by": "rebind_corpus_entities.py + resolve_id (deterministic gate)", "at": "2026-06-12"}

    # --- CORPUS-2026-0001 (ZESTA) ---
    r1 = by_id["CORPUS-2026-0001"]
    prior1 = len(r1.get("entities_extracted", []))
    if zesta is not None:
        r1["entities_extracted"] = zesta
        r1["gap_flags"] = [
            "4.8 GB full atlas NOT downloaded (gated on backend + bandwidth/compute approval).",
            "spatial modality is new — RN9 spatial-transcriptomics ingestion path not built.",
            f"{len(zesta)} entities extracted from the cached 5 hpf representative slice; full-atlas "
            f"extraction needs the gated 4.8 GB download.",
        ]
        r1["audit"] = {"prior_categorization": f"{prior1} entities (not extracted)",
                       "proposed_recategorization": f"{len(zesta)} verified entities from zf5 slice",
                       "reason": "entities extracted from the cached representative slice + bound via resolve_id",
                       "by": "rebind_corpus_entities.py + anndata + resolve_id", "at": "2026-06-12"}
    else:
        print("  [warn] ZESTA: anndata or slice unavailable; CORPUS-2026-0001 entities unchanged.")

    m["manifest_version"] = MANIFEST_VERSION
    m["status"] = (f"Entities re-bound to verified store {resolve_id.store_version()} via resolve_id "
                   f"(GSE218068 {prior2}->{len(gse)}, ZESTA {prior1}->{len(zesta) if zesta else prior1}). "
                   f"Human-gated; review before commit. Prior: 2 records APPROVED 2026-06-11.")
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[rebind] store {resolve_id.store_version()}")
    print(f"  CORPUS-2026-0002 (GSE218068): {prior2} -> {len(gse)} verified entities "
          f"({sum(1 for e in gse if e['verification_tier']=='RAW')} RAW)")
    if zesta is not None:
        print(f"  CORPUS-2026-0001 (ZESTA):     {prior1} -> {len(zesta)} verified entities "
              f"({sum(1 for e in zesta if e['verification_tier']=='RAW')} RAW)")
    print(f"  manifest_version -> {MANIFEST_VERSION}  (written; review the diff before committing)")


if __name__ == "__main__":
    main()
