"""
fetch_paper.py — drill to a FULL paper (not just a catalog chunk) for the DATA INAMOVIBLE
answer pipeline (GWT v1.1, ADR-0022, slice 1a). The keystone primitive behind the founder's
requirement: the index is a guide; once you know which asset is relevant, go get the whole paper.

Two modes:
  - fetch_internal(ref): ref = corpus_record_id OR chunk_id ("CORPUS-2026-0007#c003"). Resolves
    the manifest -> raw_ref(s) -> retrievable URL (source-pointer URL or presigned MinIO). This is
    the "accessible once the agent knows the index" path (ADR-0021 fetch_raw, extended to chunk_ids).
  - fetch_external(ident): ident = a free-text query, a PMID, a PMCID, a DOI, or a URL. Resolves via
    Europe PMC (free, no key; abstract always, full text XML if Open Access), caches the RAW response
    (§7.9 — raw, not an AI summary) at mcp_cache/raw_paper_<id>_<YYYYMMDD>.*, and section-chunks it
    (reusing chunk_document.py). This is Path-B retrieval (ADR-0022 component 2).

NO-MINT: never invents identifiers. Spend: Europe PMC is free; the only paid step downstream is the
re-ingest embedding (human-gated, separate). Network: outbound HTTPS to www.ebi.ac.uk.

CLI:
  python analysis/scripts/lib/fetch_paper.py --external-query "zebrafish pronephros osr1 essentiality"
  python analysis/scripts/lib/fetch_paper.py --external PMID:24496627
  python analysis/scripts/lib/fetch_paper.py --internal CORPUS-2026-0002
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import raw_store, chunk_document  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
CACHE = ROOT / "mcp_cache"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = {"User-Agent": "witt-organogenesis-fetch_paper/1.0 (research; contact emmanuel@nuke-ai.com)"}
DATE = "20260613"  # stamped explicitly; no Date.now in-script

try:  # Windows consoles default to cp1252; paper text carries Greek/maths (α, β, …)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _get(url, parse_json=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", errors="replace")
    return json.loads(data) if parse_json else data


# ---------------- Europe PMC (external retrieval) ----------------
def search_europepmc(query, n=5):
    """Free literature search. Returns normalized records (no mint; ids come from EPMC)."""
    url = f"{EPMC}/search?query={urllib.parse.quote(query)}&format=json&resultType=core&pageSize={n}"
    js = _get(url, parse_json=True)
    out = []
    for r in js.get("resultList", {}).get("result", []):
        out.append({
            "epmc_id": r.get("id"), "source": r.get("source"), "pmid": r.get("pmid"),
            "pmcid": r.get("pmcid"), "doi": r.get("doi"), "title": r.get("title"),
            "year": r.get("pubYear"), "journal": (r.get("journalInfo", {}) or {}).get("journal", {}).get("title"),
            "is_oa": r.get("isOpenAccess") == "Y", "abstract": r.get("abstractText"),
            "cited_by": r.get("citedByCount"),
        })
    return out


def _full_text_xml(pmcid):
    """OA full text (PMC only). Endpoint is /{PMCID}/fullTextXML (no source segment). XML or None."""
    if not pmcid:
        return None
    try:
        return _get(f"{EPMC}/{pmcid}/fullTextXML")
    except Exception:
        return None


def _xml_to_text(xml):
    """JATS XML -> plain text PRESERVING structure (section titles as headers, paragraph breaks),
    so chunk_document's section-aware splitter produces real chunks instead of one blob."""
    t = re.sub(r"</(?:p|sec|title|abstract|caption|list-item|td|tr|fig|table-wrap)>", "\n\n", xml, flags=re.I)
    t = re.sub(r"<title[^>]*>", "\n\n### ", t, flags=re.I)   # promote section titles to markdown headers
    t = re.sub(r"<[^>]+>", " ", t)                            # strip remaining tags
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _resolve_one(ident):
    """Resolve a PMID / PMCID / DOI / free-text query to ONE Europe PMC record (top hit)."""
    s = ident.strip()
    if s.upper().startswith("PMID:"):
        q = f"EXT_ID:{s.split(':', 1)[1].strip()} AND SRC:MED"
    elif s.upper().startswith("PMC") or s.upper().startswith("PMCID:"):
        q = f"PMCID:{s.split(':', 1)[-1].strip().upper().replace('PMC', 'PMC')}"
    elif s.upper().startswith("DOI:") or s.startswith("10."):
        q = f"DOI:{s.split(':', 1)[-1].strip()}"
    else:
        q = s  # free-text
    hits = search_europepmc(q, n=1)
    return hits[0] if hits else None


def fetch_external(ident, want_full_text=True):
    """Resolve ident -> paper record, pull OA full text if available, cache RAW (§7.9), chunk it."""
    rec = _resolve_one(ident)
    if rec is None:
        return {"found": False, "ident": ident, "note": "no Europe PMC match"}
    cid = (rec.get("pmcid") or rec.get("pmid") or re.sub(r"[^A-Za-z0-9]", "_", ident))[:40]
    CACHE.mkdir(exist_ok=True)
    # cache the raw metadata record (§7.9 raw, not a summary)
    (CACHE / f"raw_paper_{cid}_{DATE}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    text, full_text_cached = rec.get("abstract") or "", None
    if want_full_text and rec.get("is_oa") and rec.get("pmcid"):
        xml = _full_text_xml(rec["pmcid"])  # /{PMCID}/fullTextXML
        if xml:
            full_text_cached = CACHE / f"raw_paper_{cid}_{DATE}_fulltext.xml"
            full_text_cached.write_text(xml, encoding="utf-8")  # XML stays as the raw artifact
            text = _xml_to_text(xml)

    # source pointer (public, reproducible) -> raw_ref; chunk the text
    src_url = (f"https://europepmc.org/article/{rec.get('source', 'MED')}/{rec.get('pmid') or rec.get('pmcid')}")
    txt_path = CACHE / f"raw_paper_{cid}_{DATE}.txt"
    txt_path.write_text(text or "", encoding="utf-8")
    raw_ref = raw_store.source_pointer(src_url, path=txt_path)
    raw_ref["filename"] = txt_path.name
    chunks = chunk_document.chunk(txt_path) if text else []
    return {"found": True, "ident": ident, "record": rec, "is_oa": rec.get("is_oa"),
            "full_text": full_text_cached is not None, "n_chunks": len(chunks),
            "raw_cached": [str(p.relative_to(ROOT)) for p in CACHE.glob(f"raw_paper_{cid}_{DATE}*")],
            "raw_ref": raw_ref, "chunks_preview": [{"section": c["section"], "chars": c["chars"]} for c in chunks[:6]]}


# ---------------- DATA INAMOVIBLE internal (access by index) ----------------
def fetch_internal(ref, filename=None):
    """ref = corpus_record_id or chunk_id (CORPUS-...#cNNN). Resolve to retrievable raw URL(s)."""
    record_id = str(ref).split("#", 1)[0]  # fix #1: chunk_id -> parent record id
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rec = next((r for r in man.get("records", []) if r["corpus_record_id"] == record_id), None)
    if rec is None:
        # accession fallback (same matching as fetch_raw)
        k = record_id.lower()
        rec = next((r for r in man.get("records", [])
                    if k in str(r.get("source_document", {}).get("accession", "")).lower()), None)
    if rec is None:
        return {"found": False, "ref": ref, "note": "no corpus record (pass CORPUS-YYYY-NNNN[, #cNNN] or accession)"}
    files = rec.get("raw_provenance", {}).get("files", [])
    if filename:
        files = [f for f in files if f.get("filename") == filename]
    out = [{"filename": f.get("filename"), **raw_store.fetch_url(f)} for f in files]
    return {"found": True, "corpus_record_id": rec["corpus_record_id"], "from_ref": ref,
            "n_files": len(out), "files": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", help="PMID:.. / PMCID / DOI:.. / URL to fetch")
    ap.add_argument("--external-query", help="free-text query; fetches the top Europe PMC hit")
    ap.add_argument("--internal", help="corpus_record_id or chunk_id (CORPUS-...#cNNN)")
    ap.add_argument("--no-full-text", action="store_true")
    a = ap.parse_args()
    if a.internal:
        out = fetch_internal(a.internal)
    elif a.external or a.external_query:
        out = fetch_external(a.external or a.external_query, want_full_text=not a.no_full_text)
    else:
        ap.error("pass --external / --external-query / --internal")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
