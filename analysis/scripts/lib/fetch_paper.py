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

ADR-0078 (Path A/B hygiene) — what changed in this module:
  - search_europepmc_ledger(query, n, sort, synonym): the SAME search, but it returns (items, ledger)
    and NEVER raises (§6 no-hang): a timeout / URLError / bad JSON leaves status 'error' in the
    ledger and items=[]; hitCount 0 is status 'no-match' (searched-and-found-nothing is NOT a failure).
    search_europepmc() keeps its old signature and semantics (raises) for existing callers.
  - The cache stamp is the REAL UTC date of the download (was the frozen literal "20260613") and the
    cached JSON carries 'fetched_at' (ISO-8601 UTC) next to the record.
  - READ cache: before touching the network, fetch_external looks for a raw_paper_<id>_*.json no
    older than WITT_CACHE_TTL_DAYS (default 7) and reuses it, declaring cache_hit=True + cached_at.
    A cache hit is never presented as fresh; a stale or absent cache goes to the network.
  - User-Agent: the hardcoded e-mail is gone. WITT_NCBI_EMAIL (no default) is used as the contact
    when set; when unset the UA says "contact: unset". The ledger declares only the STATE of the
    contact — contact:'declared'|'unset' — never the address itself: the ledger travels to the frozen
    bundle, to GET /runs/{id} and into the synthesizer/panel prompts (ADR-0078 corrector, 2026-09-14).
  - Throttle: WITT_EPMC_MIN_INTERVAL_S (default 0.2 s) between Europe PMC calls, via
    analysis.scripts.lib.net_throttle.get_throttle(host, interval).wait(). net_throttle is a HARD
    dependency (same policy as pubmed_literature): if pacing cannot be obtained at call time the search
    is declared status 'error' — a request is never fired unpaced. throttle_slept_s is the measured sleep
    of THIS call (per-call meta, no module-global: two worker threads never read each other's number).

Env vars (ADR-0078; defaults declared here, read at call time so tests can flip them):
  WITT_CACHE_TTL_DAYS        default 7    — read-cache freshness window for raw_paper_*.json
  WITT_EPMC_MIN_INTERVAL_S   default 0.2  — min seconds between Europe PMC requests (process-wide)
  WITT_NCBI_EMAIL            no default   — contact for the User-Agent; absent => 'contact: unset'

NO-MINT: never invents identifiers. Spend: Europe PMC is free; the only paid step downstream is the
re-ingest embedding (human-gated, separate). Network: outbound HTTPS to www.ebi.ac.uk.

CLI:
  python analysis/scripts/lib/fetch_paper.py --external-query "zebrafish pronephros osr1 essentiality"
  python analysis/scripts/lib/fetch_paper.py --external PMID:24496627
  python analysis/scripts/lib/fetch_paper.py --internal CORPUS-2026-0002
  python analysis/scripts/lib/fetch_paper.py --search "osr1 pronephros" --n 5 --sort CITED
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import raw_store, chunk_document  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
CACHE = ROOT / "mcp_cache"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA_PRODUCT = "witt-organogenesis-fetch_paper/1.1"

# ADR-0078 defaults — declared once, read at call time (see _ttl_days / _min_interval_s).
CACHE_TTL_DAYS_DEFAULT = 7
EPMC_MIN_INTERVAL_S_DEFAULT = 0.2
EPMC_SORTS = {"CITED", "P_PDATE_D", "RELEVANCE"}   # RELEVANCE == EPMC default (no sort param sent)
HTTP_TIMEOUT_S = 30

try:  # Windows consoles default to cp1252; paper text carries Greek/maths (α, β, …)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- ADR-0078: throttle seam ----------------
# net_throttle exposes a process-global per-host limiter:
#   net_throttle.get_throttle(host, min_interval_s).wait() -> seconds actually slept (a measurement)
# HARD import (ADR-0078 corrector): the module lives in this repo and pubmed_literature already fails
# 'error' without it; two policies for one module inside one ADR was a disguised fallback. A pacing
# failure AT CALL TIME propagates out of _get and the caller declares status 'error' for that search.
EPMC_HOST = "www.ebi.ac.uk"
from lib import net_throttle as _net_throttle  # noqa: E402
_THROTTLE_BACKEND = "net_throttle"


def _ttl_days():
    """WITT_CACHE_TTL_DAYS (ADR-0078), default 7. Non-numeric => default (declared, not silent)."""
    try:
        return float(os.environ.get("WITT_CACHE_TTL_DAYS", CACHE_TTL_DAYS_DEFAULT))
    except (TypeError, ValueError):
        return float(CACHE_TTL_DAYS_DEFAULT)


def _min_interval_s():
    """WITT_EPMC_MIN_INTERVAL_S (ADR-0078), default 0.2 s."""
    try:
        return float(os.environ.get("WITT_EPMC_MIN_INTERVAL_S", EPMC_MIN_INTERVAL_S_DEFAULT))
    except (TypeError, ValueError):
        return float(EPMC_MIN_INTERVAL_S_DEFAULT)


def _contact():
    """WITT_NCBI_EMAIL if set (ADR-0078), else the literal 'unset' — declared, never invented.
    Used ONLY to build the User-Agent header; the ledger carries _contact_state(), never this value."""
    return (os.environ.get("WITT_NCBI_EMAIL") or "").strip() or "unset"


def _contact_state():
    """'declared' | 'unset' — what the LEDGER says about the contact (ADR-0078 corrector). The address
    itself never enters a ledger: ledgers persist in the bundle, are served by the API and are fed to
    the synthesizer and the four judges. Three states honoured: env set -> 'declared'; absent/blank ->
    'unset'."""
    return "declared" if _contact() != "unset" else "unset"


def _ua():
    """User-Agent built per request. No hardcoded e-mail (ADR-0078)."""
    return {"User-Agent": f"{UA_PRODUCT} (research; contact: {_contact()})"}


def _throttle():
    """Wait for the Europe PMC slot (WITT_EPMC_MIN_INTERVAL_S). Returns (backend, slept_s) for THIS
    call — the caller copies them into its own ledger (no module-global: ADR-0078 corrector). A pacing
    failure RAISES: the request is never fired unpaced; search_europepmc_ledger turns it into status
    'error' for that search and the run continues with the other sources (§6 no-hang)."""
    slept = _net_throttle.get_throttle(EPMC_HOST, _min_interval_s()).wait()
    return _THROTTLE_BACKEND, slept


def _now_utc():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stamp(dt):
    """YYYYMMDD of the REAL UTC download time (ADR-0078; was the frozen literal '20260613')."""
    return dt.strftime("%Y%m%d")


def _get(url, parse_json=False, meta=None, timeout=None):
    """One throttled GET. Raises on network / JSON / pacing failure — callers decide whether to declare.
    `meta` (dict, optional) receives throttle/throttle_slept_s for THIS call (per-call measurement).
    `timeout` (ADR-0080 corrector): socket timeout for THIS call; None = HTTP_TIMEOUT_S (module default)."""
    backend, slept = _throttle()
    if meta is not None:
        meta["throttle"], meta["throttle_slept_s"] = backend, slept
    req = urllib.request.Request(url, headers=_ua())
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S if timeout is None else timeout) as r:
        data = r.read().decode("utf-8", errors="replace")
    return json.loads(data) if parse_json else data


# ---------------- Europe PMC (external retrieval) ----------------
def _search_url(query, n, sort=None, synonym=True):
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": int(n),
              "synonym": "TRUE" if synonym else "FALSE"}
    if sort and sort.upper() != "RELEVANCE":
        params["sort"] = f"{sort.upper()} desc"
    return f"{EPMC}/search?" + urllib.parse.urlencode(params)


def _normalize_hit(r):
    return {
        "epmc_id": r.get("id"), "source": r.get("source"), "pmid": r.get("pmid"),
        "pmcid": r.get("pmcid"), "doi": r.get("doi"), "title": r.get("title"),
        "year": r.get("pubYear"), "journal": ((r.get("journalInfo", {}) or {}).get("journal", {}) or {}).get("title"),
        "is_oa": r.get("isOpenAccess") == "Y", "abstract": r.get("abstractText"),
        "cited_by": r.get("citedByCount"),
        "license": r.get("license"),   # ADR-0083 (A.2): 'cc by' | 'cc by-nc-nd' | … tal como lo manda EPMC; None si no viene
    }


def search_europepmc(query, n=5, sort=None, synonym=True):
    """Free literature search. Returns normalized records (no mint; ids come from EPMC).
    Legacy signature/semantics kept for existing callers: RAISES on network / JSON failure.
    New code should use search_europepmc_ledger (ADR-0078)."""
    js = _get(_search_url(query, n, sort, synonym), parse_json=True)
    return [_normalize_hit(r) for r in (js.get("resultList", {}) or {}).get("result", []) or []]


def search_europepmc_ledger(query, n=5, sort=None, synonym=True, timeout=None):
    """ADR-0078: the same search, returning (items, ledger) and NEVER raising (§6 no-hang).

    ledger = {source:'europepmc', status: 'success'|'no-match'|'error', query_sent, n_found (EPMC
              hitCount — total matches, a measurement from the source; None + n_found_note when the
              payload carried no hitCount — NEVER filled with the page size), n_returned (len(items);
              None when the search did not complete), elapsed_s, sort, synonym, throttle,
              throttle_slept_s (this call's measured sleep), contact: 'declared'|'unset' (state only,
              never the address), error?: str}
    - 'no-match' == the index answered and hitCount was 0 (searched, found nothing).
    - 'error'    == timeout / URLError / HTTPError / bad JSON / pacing failure; items=[], n_returned
                    None and the message is declared.
    sort ∈ {None|'RELEVANCE', 'CITED', 'P_PDATE_D'} (EPMC vocabulary; None = EPMC default ranking).
    synonym: EPMC's MeSH/synonym expansion flag (True = EPMC default).
    timeout (ADR-0080 corrector): socket timeout of the search GET; None = HTTP_TIMEOUT_S. The harness passes
    the family budget here so a slow index cannot consume the whole round; declared in `timeout_s`."""
    sort_norm = (sort or "RELEVANCE").upper()
    ledger = {"source": "europepmc", "status": "error", "query_sent": query, "n_found": None,
              "n_returned": None, "elapsed_s": None, "sort": sort_norm, "synonym": bool(synonym),
              "throttle": _THROTTLE_BACKEND, "throttle_slept_s": None, "contact": _contact_state(),
              "timeout_s": HTTP_TIMEOUT_S if timeout is None else timeout,
              "timeout_s_source": "module-default (HTTP_TIMEOUT_S)" if timeout is None else "caller"}
    if sort_norm not in EPMC_SORTS:
        ledger["error"] = f"ValueError: unknown sort {sort!r} (allowed: {sorted(EPMC_SORTS)})"
        ledger["elapsed_s"] = 0.0
        return [], ledger
    t0 = time.monotonic()
    try:
        js = _get(_search_url(query, n, sort_norm, synonym), parse_json=True, meta=ledger,
                  **({} if timeout is None else {"timeout": timeout}))
        if not isinstance(js, dict):
            raise ValueError(f"unexpected Europe PMC payload type {type(js).__name__}")
        items = [_normalize_hit(r) for r in (js.get("resultList", {}) or {}).get("result", []) or []]
        hit_count = js.get("hitCount")
        if isinstance(hit_count, int):
            ledger["n_found"] = hit_count
        else:  # ADR-0078 corrector: the page size is n_returned, not the total — never dressed as one
            ledger["n_found"] = None
            ledger["n_found_note"] = "hitCount absent in EPMC payload (total matches not measured)"
        ledger["n_returned"] = len(items)
        ledger["status"] = "success" if items else "no-match"
    except Exception as e:  # urllib.error.URLError/HTTPError, socket.timeout, ValueError (JSON), pacing
        items = []
        ledger["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    ledger["elapsed_s"] = round(time.monotonic() - t0, 3)
    return items, ledger


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


def _ident_query(ident):
    """ident -> (epmc_query, {pmid|pmcid|doi: value}) without touching the network (no mint)."""
    s = ident.strip()
    if s.upper().startswith("PMID:"):
        v = s.split(":", 1)[1].strip()
        return f"EXT_ID:{v} AND SRC:MED", {"pmid": v}
    if s.upper().startswith("PMC") or s.upper().startswith("PMCID:"):
        v = s.split(":", 1)[-1].strip().upper()
        return f"PMCID:{v}", {"pmcid": v}
    if s.upper().startswith("DOI:") or s.startswith("10."):
        v = s.split(":", 1)[-1].strip()
        return f"DOI:{v}", {"doi": v.lower()}
    return s, {}  # free-text: no identifier to match against the cache


def _resolve_one(ident):
    """Resolve a PMID / PMCID / DOI / free-text query to ONE Europe PMC record (top hit).
    Returns (record|None, ledger) — never raises (ADR-0078)."""
    q, _ = _ident_query(ident)
    hits, ledger = search_europepmc_ledger(q, n=1)
    return (hits[0] if hits else None), ledger


# ---------------- ADR-0078: read cache ----------------
_CACHE_NAME = re.compile(r"^raw_paper_(?P<cid>.+)_(?P<stamp>\d{8})\.json$")


def _load_cached_json(path):
    """A cached raw_paper JSON is either the legacy flat record (pre-ADR-0078, no fetched_at) or the
    ADR-0078 envelope {fetched_at, record}. Returns (record, fetched_at_iso|None)."""
    js = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(js, dict) and "record" in js and "fetched_at" in js:
        return js["record"], js["fetched_at"]
    return js, None


def _cache_lookup(ident, cache_dir, ttl_days, now):
    """Find a fresh cached record for ident (by pmid / pmcid / doi, matched against the cached record
    itself so PMID:x still hits a file stamped with its PMCID). Returns None when nothing usable or
    when the newest candidate is older than ttl_days — staleness is declared to the caller as a miss,
    never silently served as fresh."""
    _, keys = _ident_query(ident)
    if not keys or not cache_dir.exists():
        return None
    # ADR-0078 corrector: files are stamped raw_paper_<pmcid|pmid>_<date>.json, so the ids we hold are
    # tried BY NAME first (O(1) globs); only when nothing matches by name does the full scan run (a
    # PMID:x lookup can still hit a file stamped with its PMCID, matched against the record inside).
    by_name = []
    for cid in (keys.get("pmcid"), keys.get("pmid")):
        if cid:
            by_name.extend(cache_dir.glob(f"raw_paper_{cid}_*.json"))
    candidates = by_name if by_name else list(cache_dir.glob("raw_paper_*.json"))
    best = None
    for p in candidates:
        m = _CACHE_NAME.match(p.name)
        if not m:
            continue
        try:
            rec, fetched_at = _load_cached_json(p)
        except Exception:
            continue  # corrupt cache file: skip, the network path re-creates it
        if not isinstance(rec, dict):
            continue
        hit = (("pmid" in keys and str(rec.get("pmid") or "") == keys["pmid"])
               or ("pmcid" in keys and str(rec.get("pmcid") or "").upper() == keys["pmcid"])
               or ("doi" in keys and str(rec.get("doi") or "").lower() == keys["doi"]))
        if not hit:
            continue
        if fetched_at:
            try:
                cached_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                src = "fetched_at"
            except ValueError:
                cached_dt, src = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc), "mtime"
        else:  # legacy file: the only clock we have is the file's mtime — declared as such
            cached_dt, src = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc), "mtime"
        cand = {"path": p, "record": rec, "cached_at": _iso(cached_dt), "cached_at_source": src,
                "cid": m.group("cid"), "stamp": m.group("stamp"),
                "age_days": round((now - cached_dt).total_seconds() / 86400.0, 3)}
        if best is None or cand["age_days"] < best["age_days"]:
            best = cand
    if best is None or ttl_days <= 0 or best["age_days"] > ttl_days:
        return None  # ttl_days <= 0 == "never trust the cache" (explicit refresh)
    return best


def fetch_external(ident, want_full_text=True, cache_dir=None, ttl_days=None):
    """Resolve ident -> paper record, pull OA full text if available, cache RAW (§7.9), chunk it.

    ADR-0078: (a) read-cache first — a raw_paper_<id>_*.json younger than ttl_days (default
    WITT_CACHE_TTL_DAYS=7) is reused with cache_hit=True + cached_at; (b) the cache stamp and the
    'fetched_at' inside the JSON are the real UTC download time; (c) a search failure returns
    found:false + fetch_error + search_ledger instead of raising (§6 no-hang).
    `cache_dir` (Path, optional) overrides mcp_cache — for tests; never pass it in production."""
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE
    ttl = float(ttl_days) if ttl_days is not None else _ttl_days()
    now = _now_utc()

    cached = _cache_lookup(ident, cache_dir, ttl, now)
    if cached is not None:
        rec, cid, stamp = cached["record"], cached["cid"], cached["stamp"]
        fetched_at, cache_meta = cached["cached_at"], {
            "cache_hit": True, "cached_at": cached["cached_at"], "cached_at_source": cached["cached_at_source"],
            "cache_age_days": cached["age_days"], "cache_ttl_days": ttl, "search_ledger": None}
    else:
        rec, ledger = _resolve_one(ident)
        if rec is None:
            out = {"found": False, "ident": ident, "cache_hit": False, "search_ledger": ledger,
                   "note": "no Europe PMC match" if ledger["status"] == "no-match" else "Europe PMC search failed"}
            if ledger["status"] == "error":
                out["fetch_error"] = ledger.get("error")
            return out
        cid = (rec.get("pmcid") or rec.get("pmid") or re.sub(r"[^A-Za-z0-9]", "_", ident))[:40]
        stamp, fetched_at = _stamp(now), _iso(now)
        cache_dir.mkdir(exist_ok=True, parents=True)
        # cache the raw metadata record (§7.9 raw, not a summary) inside the ADR-0078 envelope
        (cache_dir / f"raw_paper_{cid}_{stamp}.json").write_text(
            json.dumps({"fetched_at": fetched_at, "source": "europepmc", "ident": ident, "record": rec},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        cache_meta = {"cache_hit": False, "cached_at": None, "cached_at_source": None,
                      "cache_age_days": None, "cache_ttl_days": ttl, "search_ledger": ledger}

    txt_path = cache_dir / f"raw_paper_{cid}_{stamp}.txt"
    xml_path = cache_dir / f"raw_paper_{cid}_{stamp}_fulltext.xml"
    text, full_text_cached = rec.get("abstract") or "", None
    if cache_meta["cache_hit"] and txt_path.exists():
        # reuse the cached text as-is (abstract or full text, whatever was downloaded then)
        text = txt_path.read_text(encoding="utf-8")
        full_text_cached = xml_path if xml_path.exists() else None
        if want_full_text and full_text_cached is None and rec.get("is_oa") and rec.get("pmcid"):
            # ADR-0078 corrector: the cached text is abstract-only although full text was asked and
            # is reachable — declared, not silently served as "the paper has no full text"
            cache_meta["full_text_skipped_reason"] = "cache-hit-abstract-only"
    elif want_full_text and rec.get("is_oa") and rec.get("pmcid"):
        xml = _full_text_xml(rec["pmcid"])  # /{PMCID}/fullTextXML
        if xml:
            full_text_cached = xml_path
            xml_path.write_text(xml, encoding="utf-8")  # XML stays as the raw artifact
            text = _xml_to_text(xml)

    # source pointer (public, reproducible) -> raw_ref; chunk the text
    src_url = (f"https://europepmc.org/article/{rec.get('source', 'MED')}/{rec.get('pmid') or rec.get('pmcid')}")
    if not txt_path.exists() or not cache_meta["cache_hit"]:
        txt_path.write_text(text or "", encoding="utf-8")
    raw_ref = raw_store.source_pointer(src_url, path=txt_path)
    raw_ref["filename"] = txt_path.name
    chunks = chunk_document.chunk(txt_path) if text else []

    def _rel(p):
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)
    return {"found": True, "ident": ident, "record": rec, "is_oa": rec.get("is_oa"),
            "full_text": full_text_cached is not None, "n_chunks": len(chunks),
            "fetched_at": fetched_at, **cache_meta,
            "raw_cached": sorted(_rel(p) for p in cache_dir.glob(f"raw_paper_{cid}_{stamp}*")),
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
    ap.add_argument("--search", help="ADR-0078: Europe PMC search with ledger (no fetch)")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--sort", default=None, help="RELEVANCE (default) | CITED | P_PDATE_D")
    ap.add_argument("--no-synonym", action="store_true")
    ap.add_argument("--no-full-text", action="store_true")
    ap.add_argument("--cache-dir", default=None, help="override mcp_cache (tests only)")
    ap.add_argument("--ttl-days", type=float, default=None, help="override WITT_CACHE_TTL_DAYS")
    a = ap.parse_args()
    if a.internal:
        out = fetch_internal(a.internal)
    elif a.search:
        items, ledger = search_europepmc_ledger(a.search, n=a.n, sort=a.sort, synonym=not a.no_synonym)
        out = {"items": items, "ledger": ledger}
    elif a.external or a.external_query:
        out = fetch_external(a.external or a.external_query, want_full_text=not a.no_full_text,
                             cache_dir=a.cache_dir, ttl_days=a.ttl_days)
    else:
        ap.error("pass --external / --external-query / --internal / --search")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
