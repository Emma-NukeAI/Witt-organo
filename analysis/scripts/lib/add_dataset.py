"""
add_dataset.py — one-command contributor workflow to PROPOSE a new dataset into the DATA INAMOVIBLE
(GWT v1.1, ADR-0021/0017). Chains: raw_ref (source-pointer for public URLs / MinIO mirror for private
files) -> classify (corpus_classifier) -> extract verified entities (resolve_id gate) -> build a PROPOSED
corpus record with approval_chain=pending_review. It NEVER ingests and NEVER writes verified IDs from
memory — it leaves a proposal for the human gate. Approve + ingest with approve_dataset.py.

Examples:
  # public dataset (source-pointer; --download to also fetch+hash for entity extraction):
  python analysis/scripts/lib/add_dataset.py --name "My atlas" --accession GSE999999 \
      --source-db GEO_NCBI --url https://.../features.tsv.gz --download

  # private/derived local file (mirrored into MinIO):
  python analysis/scripts/lib/add_dataset.py --name "Internal MS run" --source-db local \
      --file ./data/run1.csv --private

Run with a python that can read the file type (anndata for .h5ad).  NO verified IDs minted.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import resolve_id, raw_store, corpus_classifier  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
CACHE = ROOT / "mcp_cache"


def _next_id(man):
    ids = [r["corpus_record_id"] for r in man.get("records", [])]
    nums = [int(i.split("-")[-1]) for i in ids if i.startswith("CORPUS-2026-")]
    return f"CORPUS-2026-{(max(nums) + 1) if nums else 1:04d}"


def _download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url} -> {dest.name} ...")
    urllib.request.urlretrieve(url, dest)
    return dest


def extract_symbols(path):
    """Dispatch by extension -> candidate gene symbols. Entities are bound via resolve_id (the gate)."""
    p = Path(path)
    ext = "".join(p.suffixes).lower()
    cands = set()
    if ext.endswith(".h5ad"):
        import anndata
        ad = anndata.read_h5ad(p, backed="r")
        cands.update(map(str, ad.var_names))
        try:
            for c in ad.var.columns:
                if "name" in c.lower() or "symbol" in c.lower():
                    cands.update(map(str, ad.var[c].astype(str).tolist()))
        except Exception:
            pass
    elif "features.tsv" in p.name.lower() or ext.endswith((".tsv.gz", ".tsv")):
        import gzip
        op = gzip.open if p.suffix == ".gz" else open
        with op(p, "rt", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                cands.update(parts[:2])
    elif ext.endswith((".pdf", ".txt", ".md")):
        return []  # text -> handled by the chunker (chunk_document.py), not symbol extraction
    return cands


def verified_entities(path):
    NF = resolve_id.NOT_FOUND
    ents, seen = [], set()
    for s in extract_symbols(path):
        r = resolve_id.resolve(s)
        if r is not NF and r.symbol not in seen:
            seen.add(r.symbol)
            ents.append({"entity": r.symbol, "type": "gene_symbol",
                         "verified_store_ref": f"verified_identifiers.json#{r.symbol}",
                         "store_ensdarg": r.ensdarg,
                         "verification_tier": "RAW" if r.is_raw_verified else "DERIVED"})
    return ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--accession", default=None)
    ap.add_argument("--source-db", default="local")
    ap.add_argument("--url", action="append", default=[], help="public source URL (source-pointer)")
    ap.add_argument("--file", action="append", default=[], help="local file")
    ap.add_argument("--private", action="store_true", help="mirror --file(s) into MinIO (else source-pointer)")
    ap.add_argument("--download", action="store_true", help="download --url(s) to hash + extract entities")
    ap.add_argument("--niche", default=None)
    ap.add_argument("--domain", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cid = _next_id(man)
    raw_files, local_paths = [], []

    for url in a.url:
        fname = url.split("/")[-1]
        if a.download:
            dest = _download(url, CACHE / "incoming" / fname)
            ref = raw_store.source_pointer(url, path=dest); ref["filename"] = fname
            local_paths.append(dest)
        else:
            ref = raw_store.source_pointer(url); ref["filename"] = fname
            print(f"  [pointer] {fname} (no --download: sha256 unknown; add --download to verify)")
        raw_files.append(ref)

    for fp in a.file:
        p = Path(fp); local_paths.append(p)
        if a.private:
            print(f"  mirroring {p.name} -> MinIO ...")
            ref = raw_store.put(p, source_url=None); ref["filename"] = p.name
        else:
            ref = raw_store.source_pointer(f"file://{p.resolve()}", path=p); ref["filename"] = p.name
        raw_files.append(ref)

    ents = []
    for p in local_paths:
        try:
            ents += verified_entities(p)
        except Exception as e:
            print(f"  [warn] entity extraction skipped for {Path(p).name}: {type(e).__name__}: {e}")
    # dedup
    ents = list({e["entity"]: e for e in ents}.values())

    blob = f"{a.name} {' '.join(a.url)} {' '.join(a.file)}"
    cls = corpus_classifier.propose_categorization(a.file[0] if a.file else (a.url[0] if a.url else a.name), blob)

    rec = {
        "corpus_record_id": cid, "version": "v1.0",
        "source_document": {"name": a.name, "accession": a.accession, "source_db": a.source_db},
        "axis_data_niche": {"primary": a.niche or cls["data_niche_candidates"][0],
                            "secondary": cls["data_niche_candidates"][1:]},
        "axis_scientific_domain": {"primary": a.domain or "N1"},
        "entities_extracted": ents,
        "proposed_placement": {"data_niche": a.niche or cls["data_niche_candidates"][0],
                               "confidence": cls["confidence"], "reasoning": "corpus_classifier v1 (extension+keyword); human gate required"},
        "raw_provenance": {"policy": "hybrid", "n_files": len(raw_files), "files": raw_files},
        "approval_chain": [{"gate": "categorization", "status": "pending_review", "approved_by": None, "approved_at": None}],
        "gap_flags": (["classifier ambiguous — review placement"] if cls.get("ambiguous") else []) +
                     ([] if ents else ["no verified entities (none of the dataset's symbols are in the store, or it's a text doc — chunk it)"]),
        "substrate_evidence": ["test_1", "test_3"],
    }
    print(f"\n[add_dataset] PROPOSED {cid}: {len(raw_files)} raw file(s), {len(ents)} verified entities, "
          f"niche={rec['proposed_placement']['data_niche']} (conf {cls['confidence']})")
    if a.dry_run:
        print("  --dry-run: not written. Record preview:")
        print(json.dumps(rec, indent=2, ensure_ascii=False)[:1200])
        return
    man["records"].append(rec)
    man["status"] = f"{cid} PROPOSED (pending_review) via add_dataset.py. Approve with approve_dataset.py."
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  written to manifest as pending_review. HUMAN GATE: review, then "
          f"`python analysis/scripts/lib/approve_dataset.py {cid}` to approve + ingest.")


if __name__ == "__main__":
    main()
