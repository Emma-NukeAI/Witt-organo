"""
openalex_search — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 lote C / rebanada C5).

WHY THIS TOOL EXISTS: the search harness of ADR-0080 dispatches an `openalex` family (evidence_kind
'paper') as a THIRD literature index next to Europe PMC and PubMed. Its value is the same as PubMed's
over EPMC (ADR-0062): ranking diversity and source independence — plus two things the other two do not
give for free: a reconstructable ABSTRACT for works outside PubMed, and cross-identifiers (DOI, PMID,
PMCID, OpenAlex id) in one record. Layer 0: stdlib-pure, importable by path (ADR-0062).

WHAT IT DOES: GET https://api.openalex.org/works?search=<q>&per-page=<n>&select=<fields>[&mailto=<contact>]
Returns ranked works {openalex_id, doi, pmid, pmcid, title, year, type, journal, cited_by_count, is_oa,
oa_url, url, abstract, n_authors}. NO key required. OPENALEX_API_KEY (optional) is sent as the `api_key`
request HEADER when set (spec ADR-0080 D) and only its PRESENCE is declared (`api_key_present`); the value
never reaches the output. Credits / rate-limit response headers, when the server sends any, are returned
as a MEASUREMENT in `credits_headers` (None when the response carried none — declared absence).

THE ABSTRACT IS RECONSTRUCTED, AND SAYS SO: OpenAlex serves `abstract_inverted_index` ({word: [positions]}).
The tool rebuilds the text by position (a deterministic transform, `abstract_source:
'inverted-index-reconstructed'`), caps it at ABSTRACT_CAP and declares the cut. A work without an
inverted index has `abstract: null`, `abstract_source: null` — absent, not empty.

CONTACT (mailto, "polite pool") IS DECLARED, NEVER WRITTEN OUT: sent only when WITT_UNPAYWALL_EMAIL or
WITT_NCBI_EMAIL is set (`contact: 'declared' | 'unset'`, `contact_source` names the env); the address
lives only in the URL / User-Agent.

THREE STATES, NEVER CONFLATED (ADR-0043 / ADR-0080):
  'success'        — meta.count > 0 and >= 1 work parsed
  'no-match'       — meta.count == 0 (searched, nothing found; NOT an error)
  'error'          — the call failed ({status:'error', error:'<Type>: <msg>', http_status?})
  'skipped-budget' — timeout <= 0 before the call (nothing sent)

READ CACHE PER DAY (CLAUDE.md §6): the RAW response is persisted at
mcp_cache/raw_openalex_<slug>_<sha8>_<YYYYMMDD>.json as {fetched_at, url, response, headers} (URL stored
WITHOUT mailto); a same-day file is served instead of the network (`cache_hit`, `cached_at`, `cache_path`).

PACING: process-wide Throttle for api.openalex.org (DEFAULT_MIN_INTERVAL_S = 0.1 s — OpenAlex allows 10/s)
and ONE retry on HTTP 429 via lib/net_throttle (imported by path). Without net_throttle the call still
runs with `throttle: null`, `retry_available: false` declared.

ENV VARS (all with a declared default):
  OPENALEX_API_KEY       default unset  — optional; sent as header `api_key`; presence declared only
  WITT_OPENALEX_PER_PAGE default 5      — works per query (clamped to [1, 200], the API ceiling)
  WITT_UNPAYWALL_EMAIL / WITT_NCBI_EMAIL — optional contact for the polite pool (declared, never echoed)

OUTPUT CONTRACT:
  {status, query_sent, url_sent (public, no mailto), elapsed_s, n_http_gets, cache_hit, cache_path,
   cached_at, contact, contact_source, api_key_present, credits_headers, throttle, retries_429,
   retry_available, identifier_provenance: 'openalex-works', evidence_kind: 'paper',
   data: {query, query_sent, per_page_sent, n_found_total, n_returned, abstract_chars_cap, records: [...]}}
Identifiers returned are EXTERNAL identifiers RETRIEVED with provenance (OpenAlex), not verified-for-
citation (CLAUDE.md §7 — the integrator resolves or gap_flags them).
Fixture recorded from the live API: rag_index/query_service/fixtures/openalex_works_wt1a_20260915.json
Offline gate: rag_index/query_service/smoke_tools_c.py
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "mcp_cache"                        # ADR-0080: declared cache root (gitignored)
_LIB_PARENT = str(_ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)
try:
    from lib import net_throttle  # noqa: E402
    _THROTTLE_IMPORT_ERROR = None
except Exception as _e:  # declared in the output, never hidden
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

BASE = "https://api.openalex.org/works"
HOST = "api.openalex.org"
_UA_BASE = "witt-organo/1.0 (openalex-tool)"

DEFAULT_TIMEOUT_S = 30        # urllib socket timeout per GET when the caller passes none
DEFAULT_PER_PAGE = 5          # ADR-0080: WITT_OPENALEX_PER_PAGE
PER_PAGE_CEILING = 200        # OpenAlex API maximum
DEFAULT_MIN_INTERVAL_S = 0.1  # ADR-0080: OpenAlex documents 10 requests/second
ABSTRACT_CAP = 2500           # chars of reconstructed abstract kept; the cut is declared per record
SELECT_FIELDS = ("id", "doi", "title", "display_name", "publication_year", "type", "cited_by_count",
                 "primary_location", "open_access", "ids", "authorships", "abstract_inverted_index")
IDENTIFIER_PROVENANCE = "openalex-works"
EVIDENCE_KIND = "paper"
ABSTRACT_SOURCE = "inverted-index-reconstructed"
_CREDIT_HEADER_HINTS = ("x-ratelimit", "x-api", "credit", "retry-after")


def _get(url, timeout=DEFAULT_TIMEOUT_S, with_headers=False, api_key=None, ua_suffix=None):
    """The ONLY network seam of this module (the offline smoke monkeypatches it to serve fixtures).
    Returns parsed JSON; with `with_headers=True` returns (json, credits_headers_or_None). `api_key`
    goes in the request header `api_key` only; `ua_suffix` (contact) only in the User-Agent."""
    hdrs = {"User-Agent": _UA_BASE + (f" (mailto:{ua_suffix})" if ua_suffix else ""),
            "Accept": "application/json"}
    if api_key:
        hdrs["api_key"] = api_key
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        js = json.loads(body)
        if not with_headers:
            return js
        return js, _credit_headers(getattr(r, "headers", None))


def _credit_headers(hdrs):
    """Rate-limit / credit headers as MEASURED (None when the response carried none)."""
    if hdrs is None:
        return None
    try:
        found = {k: v for k, v in hdrs.items()
                 if any(h in str(k).lower() for h in _CREDIT_HEADER_HINTS)}
    except Exception:
        found = {}
    return found or None


def resolve_per_page(per_page=None):
    """ADR-0080: explicit `per_page` > WITT_OPENALEX_PER_PAGE > DEFAULT_PER_PAGE (5). Clamped to [1, 200]."""
    val = per_page
    if val is None:
        raw = os.environ.get("WITT_OPENALEX_PER_PAGE", "").strip()
        val = raw if raw else DEFAULT_PER_PAGE
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = DEFAULT_PER_PAGE
    return max(1, min(n, PER_PAGE_CEILING))


def resolve_contact():
    """(address | None, env_name | None): WITT_UNPAYWALL_EMAIL, else WITT_NCBI_EMAIL. Nothing invented."""
    for env in ("WITT_UNPAYWALL_EMAIL", "WITT_NCBI_EMAIL"):
        v = os.environ.get(env, "").strip()
        if v:
            return v, env
    return None, None


def _api_key():
    return os.environ.get("OPENALEX_API_KEY", "").strip() or None


def reconstruct_abstract(inv):
    """abstract_inverted_index {word: [pos, ...]} -> text by position. Deterministic; None when absent."""
    if not isinstance(inv, dict) or not inv:
        return None
    slots = {}
    for word, positions in inv.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            if isinstance(p, int) and p >= 0:
                slots[p] = word
    if not slots:
        return None
    return " ".join(slots[k] for k in sorted(slots))


def _strip_prefix(value, prefix):
    if not isinstance(value, str):
        return None
    return value[len(prefix):] if value.startswith(prefix) else value


def parse_work(w):
    """ONE OpenAlex work -> the tool's record. Deterministic; every absence stays None."""
    w = w or {}
    ids = w.get("ids") or {}
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {}) if isinstance(loc, dict) else {}
    oa = w.get("open_access") or {}
    abstract_full = reconstruct_abstract(w.get("abstract_inverted_index"))
    abstract = abstract_full[:ABSTRACT_CAP] if abstract_full else None
    authorships = w.get("authorships") or []
    doi = _strip_prefix(w.get("doi") or ids.get("doi"), "https://doi.org/")
    pmid = _strip_prefix(ids.get("pmid"), "https://pubmed.ncbi.nlm.nih.gov/")
    pmcid = _strip_prefix(ids.get("pmcid"), "https://www.ncbi.nlm.nih.gov/pmc/articles/")
    return {
        "openalex_id": _strip_prefix(w.get("id") or ids.get("openalex"), "https://openalex.org/"),
        "doi": doi.lower() if doi else None,
        "pmid": pmid,
        "pmcid": pmcid,
        "title": w.get("title") or w.get("display_name"),
        "year": w.get("publication_year") if isinstance(w.get("publication_year"), int) else None,
        "type": w.get("type"),
        "journal": src.get("display_name") if isinstance(src, dict) else None,
        "cited_by_count": w.get("cited_by_count") if isinstance(w.get("cited_by_count"), int) else None,
        "is_oa": oa.get("is_oa") if isinstance(oa.get("is_oa"), bool) else None,
        "oa_url": oa.get("oa_url") or (loc.get("pdf_url") if isinstance(loc, dict) else None),
        "url": (loc.get("landing_page_url") if isinstance(loc, dict) else None) or w.get("id"),
        "abstract": abstract,
        "abstract_truncated": bool(abstract_full) and len(abstract_full) > ABSTRACT_CAP,
        "abstract_source": ABSTRACT_SOURCE if abstract else None,
        "n_authors": len(authorships) if isinstance(authorships, list) else None,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
    }


def _slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:n].strip("-") or "query"


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def build_url(query, per_page):
    """PUBLIC URL (no mailto): the literal that is declared in `url_sent` and stored in the cache."""
    return (f"{BASE}?search={urllib.parse.quote(query)}&per-page={per_page}"
            f"&select={','.join(SELECT_FIELDS)}")


def query_openalex(query, per_page=None, timeout=DEFAULT_TIMEOUT_S, cache_dir=None):
    """Core logic (stdlib-only, importable for standalone testing). See the module docstring for the
    contract. ONE GET. `cache_dir` overrides mcp_cache (tests only). Never raises."""
    t0 = time.monotonic()
    term = (query or "").strip()
    n = resolve_per_page(per_page)
    base = {"query_sent": term or None, "url_sent": None, "elapsed_s": 0.0, "n_http_gets": 0,
            "cache_hit": False, "cache_path": None, "cached_at": None,
            "contact": "unset", "contact_source": None, "api_key_present": bool(_api_key()),
            "credits_headers": None, "throttle": None, "retries_429": 0,
            "retry_available": net_throttle is not None,
            "identifier_provenance": IDENTIFIER_PROVENANCE, "evidence_kind": EVIDENCE_KIND}
    data_head = {"query": query, "query_sent": term or None, "per_page_sent": n}

    def _done(status, **kw):
        base["elapsed_s"] = round(time.monotonic() - t0, 4)
        return dict(base, status=status, **kw)

    if not term:
        return _done("error", error="empty query", data=data_head)
    if timeout is not None and timeout <= 0:
        return _done("skipped-budget", data=data_head,
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    contact, contact_env = resolve_contact()
    if contact:
        base["contact"], base["contact_source"] = "declared", contact_env
    url_public = build_url(term, n)
    base["url_sent"] = url_public
    url = url_public + (f"&mailto={urllib.parse.quote(contact)}" if contact else "")

    cdir = Path(cache_dir) if cache_dir else CACHE_DIR
    sha8 = hashlib.sha256(url_public.encode("utf-8")).hexdigest()[:8]
    cpath = cdir / f"raw_openalex_{_slug(term)}_{sha8}_{_now_utc().strftime('%Y%m%d')}.json"
    base["cache_path"] = _rel(cpath)
    cached = None
    if cpath.exists():
        try:
            cached = json.loads(cpath.read_text(encoding="utf-8"))
            if not (isinstance(cached, dict) and "fetched_at" in cached and "response" in cached):
                cached = None
        except Exception:
            cached = None

    try:
        if cached is not None:
            base["cache_hit"], base["cached_at"] = True, cached.get("fetched_at")
            base["credits_headers"] = cached.get("headers")
            js = cached["response"]
        else:
            thr = net_throttle.get_throttle(HOST, DEFAULT_MIN_INTERVAL_S) if net_throttle else None
            if thr is not None:
                base["throttle"] = {"host": HOST, "min_interval_s": DEFAULT_MIN_INTERVAL_S,
                                    "min_interval_source": "constant", "waited_s": 0.0}
            stats = {}

            def _once():
                if thr is not None:
                    base["throttle"]["waited_s"] += thr.wait()
                base["n_http_gets"] += 1
                try:
                    js_, hd = _get(url, timeout=timeout, with_headers=True, api_key=_api_key(), ua_suffix=contact)
                except urllib.error.HTTPError as e:
                    hd = _credit_headers(getattr(e, "headers", None))
                    if hd:
                        base["credits_headers"] = hd
                    raise
                if hd:
                    base["credits_headers"] = hd
                return js_
            try:
                js = net_throttle.retry_once_on_429(_once, stats) if net_throttle else _once()
            finally:
                base["retries_429"] += int(stats.get("retries_429") or 0)
            _cache_write(cpath, url_public, js, base["credits_headers"])
        meta = js.get("meta", {}) if isinstance(js, dict) else {}
        n_total = meta.get("count") if isinstance(meta.get("count"), int) else None
        results = js.get("results") if isinstance(js, dict) else None
        if not isinstance(results, list):
            return _done("error", data=data_head, error="OpenAlex payload without results[]")
        records = [parse_work(w) for w in results if isinstance(w, dict)]
        status = "success" if records else "no-match"
        # meta.cost_usd is what OpenAlex itself reports for THIS call (a measurement of theirs, class
        # 'medicion' with source declared) — None when the payload carries none.
        cost = meta.get("cost_usd")
        return _done(status, data=dict(data_head, n_found_total=n_total, n_returned=len(records),
                                       abstract_chars_cap=ABSTRACT_CAP,
                                       cost_usd_reported=cost if isinstance(cost, (int, float)) else None,
                                       cost_usd_reported_source="openalex meta.cost_usd" if isinstance(cost, (int, float)) else None,
                                       records=records))
    except urllib.error.HTTPError as e:
        return _done("error", http_status=getattr(e, "code", None), data=data_head,
                     error=f"HTTPError: {getattr(e, 'code', '?')} {getattr(e, 'reason', '')}".strip())
    except Exception as e:
        return _done("error", data=data_head, error=f"{type(e).__name__}: {e}")


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
AFFILIATION_FIELDS_DROPPED = ("raw_affiliation_strings", "raw_affiliation_string")


def strip_affiliation_strings(response):
    """ADR-0080 corrector: drop the free-text affiliation strings from every authorship (they carry author
    e-mail addresses in the wild — measured on the wt1a fixture). Structured `institutions`, `countries`,
    `author` and `n_authors` are untouched. Returns (copy, n_fields_dropped)."""
    n = 0
    if not isinstance(response, dict):
        return response, 0
    out = json.loads(json.dumps(response))
    for w in out.get("results") or []:
        for a in (w.get("authorships") or []) if isinstance(w, dict) else []:
            if not isinstance(a, dict):
                continue
            if "raw_affiliation_strings" in a:
                a["raw_affiliation_strings"] = "<dropped: may contain author emails (ADR-0080)>"
                n += 1
            for aff in a.get("affiliations") or []:
                if isinstance(aff, dict) and "raw_affiliation_string" in aff:
                    aff["raw_affiliation_string"] = "<dropped: may contain author emails (ADR-0080)>"
                    n += 1
    return out, n


def redact_emails(text):
    """(text, n_redacted) — every e-mail address in `text` becomes '<email-redacted>' (ADR-0080 corrector:
    correos jamás en fixtures, ledgers ni caché)."""
    n = len(_EMAIL_RE.findall(text))
    return (_EMAIL_RE.sub("<email-redacted>", text) if n else text), n


def _cache_write(path, url_public, response, headers):
    """Persist the response (parsed body with the free-text affiliation strings DROPPED and any remaining
    e-mail redacted — both counted and declared in the envelope) + measured headers; URL without mailto.
    Best effort. The tool's own `data.records` never carried affiliations (parse_work reads n_authors only)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body, n_dropped = strip_affiliation_strings(response)
        text = json.dumps({"fetched_at": _now_utc().isoformat(timespec="seconds"), "url": url_public,
                           "headers": headers, "response": body,
                           "cut": {"fields": list(AFFILIATION_FIELDS_DROPPED), "n_fields_dropped": n_dropped,
                                   "reason": "may contain author emails (ADR-0080 corrector)"}},
                          ensure_ascii=False, indent=1)
        text, n_red = redact_emails(text)
        if n_red:
            text = text.replace('"reason": "may contain author emails (ADR-0080 corrector)"',
                                f'"reason": "may contain author emails (ADR-0080 corrector)", "emails_redacted": {n_red}', 1)
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class OpenAlex_search_works_workspace:
    name = "OpenAlex_search_works_workspace"
    description = (
        "OpenAlex works search (relevance-ranked). Returns {openalex_id, doi, pmid, pmcid, title, year, "
        "type, journal, cited_by_count, is_oa, oa_url, url, abstract (reconstructed from the inverted "
        "index and declared as such), n_authors}. No key required; OPENALEX_API_KEY optional (header, "
        "presence declared only); credits/rate-limit headers returned as measured. Status 'no-match' = "
        "searched, nothing found (ADR-0080). DEDUP by DOI/PMID against Europe PMC and PubMed before use."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "English keyword query, e.g. 'wt1a zebrafish pronephros'."},
            "per_page": {"type": ["integer", "null"], "description": "Works per query (default WITT_OPENALEX_PER_PAGE, 5)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 30)."},
        },
        "required": ["query"],
    }

    def run(self, query, per_page=None, timeout=DEFAULT_TIMEOUT_S):
        return query_openalex(query, per_page=per_page, timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    # Standalone smoke (no key required, real API; writes the same-day raw cache under mcp_cache/).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = query_openalex(" ".join(sys.argv[1:]) or "wt1a zebrafish pronephros", per_page=5)
    print(json.dumps(out, ensure_ascii=False, indent=2))
