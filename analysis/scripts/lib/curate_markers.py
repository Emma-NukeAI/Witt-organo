"""
curate_markers.py — Verify gene symbols against Ensembl REST and emit a curation file (GWT v1.1).

Producer/verifier (like scripts/lbpp_verify.py): for each symbol it calls Ensembl REST
lookup/symbol -> ENSDARG (+ ZFIN acc) and xrefs/id -> RefSeq mRNA (NM_*), caches the RAW JSON
responses per CLAUDE.md §6/§7.9, and writes:
  analysis/outputs/ocular_markers_curated.json   {symbol: {ensdarg, refseq[], zfin?, raw_cache_ref, verified_on}}
  analysis/outputs/refseq_ensembl_xref.json       {NM_*: {symbol, ensdarg}}   (RefSeq<->Ensembl cross-map)
It also MERGES the resolved symbols into analysis/outputs/ensembl_symbol_map.json (the store seed).

NO paid spend (Ensembl REST is free, no key). A human gate governs whether to rebuild the store
(build_verified_store.py) afterward. Default marker set = the ocular/corneal markers the Nat Witt
N5 handoff + the corpus-feasibility test (la prueba) flagged as missing.

Usage:  python analysis/scripts/lib/curate_markers.py [sym1 sym2 ...]
"""
from pathlib import Path
import sys
import json
import time
import subprocess

ANALYSIS = Path(__file__).resolve().parents[2]
OUT = ANALYSIS / "outputs"
CACHE = ANALYSIS.parent / "mcp_cache"
MAP = OUT / "ensembl_symbol_map.json"
VERIFIED_ON = "2026-06-11"
REST = "https://rest.ensembl.org"

OCULAR = ["foxc1b", "foxc2", "pitx2", "prox1a", "pax6a", "pax6b", "tp63",
          "krt12", "aldh3a1", "aldh1a3", "col1a1a", "col1a1b", "lum", "kera"]


def _get(url, cache_path):
    # curl via subprocess (proven; python sockets throttled). Retry on transient empty/invalid
    # responses so a timeout does NOT become a false NOT_FOUND. A valid JSON error body (400
    # not-found) is a REAL response (returned, not retried).
    for attempt in range(4):
        try:
            raw = subprocess.run(["curl", "-sL", "--max-time", "45", "--retry", "2",
                                  "-H", "Content-Type: application/json", url],
                                 capture_output=True, text=True, timeout=70).stdout
        except Exception:
            raw = ""
        if raw.strip():
            try:
                parsed = json.loads(raw)
                cache_path.write_text(raw, encoding="utf-8")  # cache only a valid response (§7.9)
                return parsed
            except Exception:
                pass
        time.sleep(2 * (attempt + 1))
    return None


def curate(symbols):
    CACHE.mkdir(exist_ok=True)
    curated, xref = {}, {}
    for sym in symbols:
        look = _get(f"{REST}/lookup/symbol/danio_rerio/{sym}?content-type=application/json",
                    CACHE / f"raw_ensembl_ocular_lookup_{sym}_{VERIFIED_ON.replace('-','')}.json")
        ensdarg = (look or {}).get("id") if isinstance(look, dict) else None
        rec = {"ensdarg": ensdarg, "refseq": [], "zfin": None,
               "raw_cache_ref": f"mcp_cache/raw_ensembl_ocular_lookup_{sym}_{VERIFIED_ON.replace('-','')}.json",
               "verified_on": VERIFIED_ON}
        if ensdarg:
            desc = (look or {}).get("description", "")
            if "ZDB-GENE" in desc:
                rec["zfin"] = desc.split("Acc:")[-1].rstrip("]")
            xr = _get(f"{REST}/xrefs/id/{ensdarg}?content-type=application/json;external_db=RefSeq_mRNA",
                      CACHE / f"raw_ensembl_ocular_refseq_{sym}_{VERIFIED_ON.replace('-','')}.json")
            if isinstance(xr, list):
                nms = sorted({x.get("primary_id") for x in xr if str(x.get("primary_id", "")).startswith("NM_")})
                rec["refseq"] = nms
                for nm in nms:
                    xref[nm] = {"symbol": sym, "ensdarg": ensdarg}
            time.sleep(0.2)
        curated[sym] = rec
        print(f"  {sym:10s} -> {ensdarg or 'NOT_FOUND'}  refseq={rec['refseq']}")
        time.sleep(0.2)

    for sym, rec in curated.items():
        if rec["ensdarg"] is None:
            rec["needs_alias_resolution"] = True  # exact-symbol lookup failed; not asserted absent
    # MERGE into any existing curation file (incremental curation; never lose prior resolved markers).
    out_path = OUT / "ocular_markers_curated.json"
    merged = {}
    if out_path.exists():
        merged = json.loads(out_path.read_text(encoding="utf-8"))
    merged.update(curated)
    out_path.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n", encoding="utf-8")
    if xref:
        (OUT / "refseq_ensembl_xref.json").write_text(json.dumps(xref, indent=2) + "\n", encoding="utf-8")
    # NOTE: this script does NOT mutate ensembl_symbol_map.json. The curation file is the ocular-marker
    # source; build_verified_store.py is the single writer that merges map + curation into the store.
    n_found = sum(1 for r in curated.values() if r["ensdarg"])
    print(f"[curate] {n_found}/{len(symbols)} resolved -> ocular_markers_curated.json | {len(xref)} RefSeq xrefs | "
          f"NOT_FOUND (needs alias): {[s for s,r in curated.items() if not r['ensdarg']]}")


if __name__ == "__main__":
    curate(sys.argv[1:] or OCULAR)
