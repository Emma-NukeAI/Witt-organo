"""
unpaywall_crossref — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 lote C / rebanada C5).

WHY THIS TOOL EXISTS: the search harness of ADR-0080 dispatches an `unpaywall_crossref` family so a DOI
that reached the evidence bundle (from Europe PMC, PubMed, OpenAlex or the model's own citation) can be
RESOLVED against its registration agency (Crossref) and its open-access status looked up (Unpaywall) —
by code, before anything is cited. CLAUDE.md §7: an external identifier is either resolved through a
source of truth or it is a gap_flag; this tool is the resolver for DOIs, at Layer 0 (stdlib-pure,
importable by path, no SDK, no MCP session — ADR-0062).

WHAT IT DOES: two independent sources over ONE normalized DOI, each with its OWN status row (§6 no-hang:
one source failing never silences the other):
  Crossref  GET https://api.crossref.org/works/{doi}[?mailto=<contact>]
            -> {doi, title, journal, year, type, publisher, authors (capped, declared), n_authors,
                is_referenced_by_count, url, abstract (JATS tags stripped, capped, declared), license[]}
  Unpaywall GET https://api.unpaywall.org/v2/{doi}?email=$WITT_UNPAYWALL_EMAIL
            -> {is_oa, oa_status, best_oa_url, best_oa_pdf_url, host_type, version, license,
                n_oa_locations, journal_is_oa}
            Unpaywall REQUIRES an email. Without WITT_UNPAYWALL_EMAIL the row is status 'tool-unavailable'
            with `reason 'WITT_UNPAYWALL_EMAIL unset'` and NO request is sent. No email is ever invented
            (ADR-0078 §6 discipline) — the fixture for this source is SYNTHETIC and named as such.

CONTACT (mailto) IS DECLARED, NEVER WRITTEN OUT: Crossref's "polite pool" asks for a `mailto` — it is sent
ONLY when a contact env is set (WITT_UNPAYWALL_EMAIL first, then WITT_NCBI_EMAIL; `contact_source` names
which). The address itself lives only in the URL / User-Agent; the output declares `contact: 'declared' |
'unset'` (the ledger travels to the bundle, the record and the judges — ADR-0078 corrector).

THREE STATES PER SOURCE, NEVER CONFLATED (ADR-0043 / ADR-0080):
  'success'          — the DOI resolved (HTTP 200, a work / an OA record parsed)
  'no-match'         — HTTP 404: the agency does not know this DOI (searched, absent; NOT an error)
  'error'            — any other failure ({status:'error', error:'<Type>: <msg>', http_status?})
  'tool-unavailable' — Unpaywall without WITT_UNPAYWALL_EMAIL (declared; nothing sent)
  'skipped-budget'   — timeout <= 0 before the call (the caller's clock is spent; nothing sent)
  'not-requested'    — the caller asked for one source only (query_doi(..., sources=[...]))
The COMBINED envelope's status is Crossref's (the resolver of record); Unpaywall is additive OA context.

READ CACHE PER DAY (CLAUDE.md §6): each RAW response is persisted at
mcp_cache/raw_crossref_<doi-slug>_<YYYYMMDD>.json and mcp_cache/raw_unpaywall_<doi-slug>_<YYYYMMDD>.json
as {fetched_at, url, response} (the URL is stored WITHOUT mailto/email — no address in the cache either);
a same-day file is served instead of the network (`cache_hit`, `cached_at`, `cache_path`). A 404 is cached
too (`response: null, http_status: 404`) so the same absent DOI is not re-asked the same day.

PACING: one process-wide Throttle per host (api.crossref.org / api.unpaywall.org, min interval
DEFAULT_MIN_INTERVAL_S = 0.2 s, declared in `throttle`) and ONE retry on HTTP 429 via
lib/net_throttle (imported by path like pubmed_literature does). If net_throttle is not importable the
call still runs, with `throttle: null` and `retry_available: false` declared.

ENV VARS (all with a declared default):
  WITT_UNPAYWALL_EMAIL   default unset  — REQUIRED by Unpaywall; also the first choice of Crossref mailto
  WITT_NCBI_EMAIL        default unset  — fallback contact for the Crossref mailto (never for Unpaywall)

DOIs returned are EXTERNAL identifiers RETRIEVED with provenance ('crossref-works' / 'unpaywall-v2'), not
verified-for-citation by themselves — the integrator's resolve/gap_flag step still owns that decision.
Fixtures: rag_index/query_service/fixtures/crossref_works_dev02071_20260915.json (REAL, live 2026-09-15)
          rag_index/query_service/fixtures/unpaywall_SYNTHETIC_dev02071_20260915.json (SYNTHETIC — no email)
Offline gate: rag_index/query_service/smoke_tools_c.py
"""
import datetime
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
except Exception as _e:  # declared in the output (`throttle: None, retry_available: False`), never hidden
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

CROSSREF_BASE = "https://api.crossref.org/works/"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2/"
CROSSREF_HOST = "api.crossref.org"
UNPAYWALL_HOST = "api.unpaywall.org"
_UA_BASE = "witt-organo/1.0 (doi-tool)"

DEFAULT_TIMEOUT_S = 30        # urllib socket timeout per GET when the caller passes none
DEFAULT_MIN_INTERVAL_S = 0.2  # ADR-0080: pacing per host (Crossref / Unpaywall polite usage)
AUTHORS_CAP = 5               # authors kept per work; the cut is declared
ABSTRACT_CAP = 2000           # chars of Crossref abstract kept; the cut is declared
SOURCES = ("crossref", "unpaywall")
PROVENANCE = {"crossref": "crossref-works", "unpaywall": "unpaywall-v2"}
EVIDENCE_KIND = {"crossref": "paper-metadata", "unpaywall": "oa-location"}
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _get(url, timeout=DEFAULT_TIMEOUT_S, with_headers=False, ua_suffix=None):
    """The ONLY network seam of this module (the offline smoke monkeypatches it to serve fixtures).
    Returns parsed JSON; with `with_headers=True` returns (json, headers_dict_or_None). `ua_suffix`
    (the contact) is appended to the User-Agent only — never echoed anywhere else."""
    hdrs = {"User-Agent": _UA_BASE + (f" (mailto:{ua_suffix})" if ua_suffix else ""),
            "Accept": "application/json"}
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        js = json.loads(body) if body.strip() else None
        if not with_headers:
            return js
        h = None
        raw = getattr(r, "headers", None)
        if raw is not None:
            try:
                h = {k: v for k, v in raw.items()} or None
            except Exception:
                h = None
        return js, h


def normalize_doi(doi):
    """ADR-0078 dedup rule: lowercase, strip `https://doi.org/`, `http://dx.doi.org/`, `doi:` prefixes and
    whitespace. Returns None when what remains is not a DOI (`10.<registrant>/<suffix>`)."""
    s = (doi or "").strip()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I).strip().lower()
    return s if _DOI_RE.match(s) else None


def resolve_contact(source):
    """(address | None, env_name | None). Unpaywall: WITT_UNPAYWALL_EMAIL ONLY (its API contract).
    Crossref mailto: WITT_UNPAYWALL_EMAIL, else WITT_NCBI_EMAIL. Nothing is invented."""
    order = ("WITT_UNPAYWALL_EMAIL",) if source == "unpaywall" else ("WITT_UNPAYWALL_EMAIL", "WITT_NCBI_EMAIL")
    for env in order:
        v = os.environ.get(env, "").strip()
        if v:
            return v, env
    return None, None


def _slug(doi, n=48):
    return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")[:n].strip("-") or "doi"


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _cache_read(path):
    """Same-day RAW envelope {fetched_at, url, response, http_status?} or None (absent / corrupt = miss)."""
    if not path.exists():
        return None
    try:
        js = json.loads(path.read_text(encoding="utf-8"))
        return js if isinstance(js, dict) and "fetched_at" in js and "response" in js else None
    except Exception:
        return None


def _cache_write(path, url_public, response, http_status=None):
    """Best effort; the URL stored is the PUBLIC one (no mailto / email)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        env = {"fetched_at": _now_utc().isoformat(timespec="seconds"), "url": url_public,
               "response": response}
        if http_status is not None:
            env["http_status"] = http_status
        path.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _cap_text(text, cap):
    t = text or ""
    return (t[:cap], len(t) > cap) if t else (None, False)


def _first(lst):
    return lst[0] if isinstance(lst, list) and lst else None


def parse_crossref_work(msg, doi_norm):
    """ONE Crossref `message` -> the tool's record. Deterministic; every cap declared."""
    msg = msg or {}
    authors_all = []
    for a in msg.get("author") or []:
        if not isinstance(a, dict):
            continue
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name")
        if name:
            authors_all.append(name)
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(key) or {}).get("date-parts") if isinstance(msg.get(key), dict) else None
        if parts and parts[0] and isinstance(parts[0][0], int):
            year = parts[0][0]
            break
    abstract_raw = msg.get("abstract")
    abstract, abs_trunc = _cap_text(_TAG_RE.sub("", abstract_raw).strip() if abstract_raw else None, ABSTRACT_CAP)
    return {
        "doi": (msg.get("DOI") or doi_norm or "").lower() or None,
        "title": _first(msg.get("title")),
        "journal": _first(msg.get("container-title")),
        "year": year,
        "type": msg.get("type"),
        "publisher": msg.get("publisher"),
        "authors": authors_all[:AUTHORS_CAP],
        "n_authors": len(authors_all),
        "authors_truncated": len(authors_all) > AUTHORS_CAP,
        "is_referenced_by_count": msg.get("is-referenced-by-count") if isinstance(msg.get("is-referenced-by-count"), int) else None,
        "url": msg.get("URL") or (f"https://doi.org/{doi_norm}" if doi_norm else None),
        "abstract": abstract,
        "abstract_truncated": abs_trunc,
        "abstract_source": "crossref-jats-stripped" if abstract else None,
        "license": [x.get("URL") for x in (msg.get("license") or []) if isinstance(x, dict) and x.get("URL")],
        "identifier_provenance": PROVENANCE["crossref"],
    }


def parse_unpaywall(js):
    """ONE Unpaywall v2 record -> the tool's record. Deterministic; absent fields stay None."""
    js = js or {}
    best = js.get("best_oa_location") or {}
    locs = js.get("oa_locations") or []
    return {
        "doi": (js.get("doi") or "").lower() or None,
        "is_oa": js.get("is_oa") if isinstance(js.get("is_oa"), bool) else None,
        "oa_status": js.get("oa_status"),
        "best_oa_url": best.get("url") if isinstance(best, dict) else None,
        "best_oa_pdf_url": best.get("url_for_pdf") if isinstance(best, dict) else None,
        "host_type": best.get("host_type") if isinstance(best, dict) else None,
        "version": best.get("version") if isinstance(best, dict) else None,
        "license": best.get("license") if isinstance(best, dict) else None,
        "n_oa_locations": len(locs) if isinstance(locs, list) else None,
        "journal_is_oa": js.get("journal_is_oa") if isinstance(js.get("journal_is_oa"), bool) else None,
        "title": js.get("title"),
        "year": js.get("year") if isinstance(js.get("year"), int) else None,
        "identifier_provenance": PROVENANCE["unpaywall"],
    }


def _throttle_block(host):
    if net_throttle is None:
        return None, None
    return net_throttle.get_throttle(host, DEFAULT_MIN_INTERVAL_S), {
        "host": host, "min_interval_s": DEFAULT_MIN_INTERVAL_S, "min_interval_source": "constant",
        "waited_s": 0.0}


def _fetch(source, doi_norm, timeout, cache_dir):
    """Shared engine for both sources: budget check -> contact -> same-day cache -> throttled GET with one
    429 retry -> parse. Returns the per-source envelope (never raises)."""
    t0 = time.monotonic()
    host = CROSSREF_HOST if source == "crossref" else UNPAYWALL_HOST
    base = {"source": source, "doi": doi_norm, "url_sent": None, "elapsed_s": 0.0, "n_http_gets": 0,
            "cache_hit": False, "cache_path": None, "cached_at": None, "contact": "unset",
            "contact_source": None, "throttle": None, "retries_429": 0,
            "retry_available": net_throttle is not None,
            "identifier_provenance": PROVENANCE[source], "evidence_kind": EVIDENCE_KIND[source]}

    def _done(status, **kw):
        base["elapsed_s"] = round(time.monotonic() - t0, 4)
        return dict(base, status=status, **kw)

    if timeout is not None and timeout <= 0:
        return _done("skipped-budget",
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    contact, contact_env = resolve_contact(source)
    if contact:
        base["contact"], base["contact_source"] = "declared", contact_env
    if source == "unpaywall" and not contact:
        return _done("tool-unavailable", reason="WITT_UNPAYWALL_EMAIL unset (Unpaywall requires an email; "
                                                "none is invented)")
    url_public = (CROSSREF_BASE if source == "crossref" else UNPAYWALL_BASE) + urllib.parse.quote(doi_norm, safe="/")
    base["url_sent"] = url_public
    if source == "crossref":
        url = url_public + (f"?mailto={urllib.parse.quote(contact)}" if contact else "")
    else:
        url = url_public + f"?email={urllib.parse.quote(contact)}"

    cdir = Path(cache_dir) if cache_dir else CACHE_DIR
    cpath = cdir / f"raw_{source}_{_slug(doi_norm)}_{_now_utc().strftime('%Y%m%d')}.json"
    base["cache_path"] = _rel(cpath)
    cached = _cache_read(cpath)
    if cached is not None:
        base["cache_hit"], base["cached_at"] = True, cached.get("fetched_at")
        if cached.get("http_status") == 404 or cached.get("response") is None:
            return _done("no-match", http_status=404, detail=f"{host} does not know this DOI (cached today)")
        js = cached["response"]
    else:
        thr, thr_info = _throttle_block(host)
        base["throttle"] = thr_info
        stats = {}

        def _once():
            if thr is not None:
                base["throttle"]["waited_s"] += thr.wait()
            base["n_http_gets"] += 1
            return _get(url, timeout=timeout, ua_suffix=contact)
        try:
            if net_throttle is not None:
                js = net_throttle.retry_once_on_429(_once, stats)
            else:
                js = _once()
        except urllib.error.HTTPError as e:
            base["retries_429"] += int(stats.get("retries_429") or 0)
            code = getattr(e, "code", None)
            if code == 404:
                _cache_write(cpath, url_public, None, http_status=404)
                return _done("no-match", http_status=404, detail=f"{host} does not know this DOI")
            return _done("error", http_status=code,
                         error=f"HTTPError: {code or '?'} {getattr(e, 'reason', '')}".strip())
        except Exception as e:
            base["retries_429"] += int(stats.get("retries_429") or 0)
            return _done("error", error=f"{type(e).__name__}: {e}")
        base["retries_429"] += int(stats.get("retries_429") or 0)
        _cache_write(cpath, url_public, js)

    try:
        if source == "crossref":
            if not isinstance(js, dict) or js.get("status") != "ok" or not isinstance(js.get("message"), dict):
                return _done("error", error="Crossref payload without status 'ok' / message")
            return _done("success", data=parse_crossref_work(js["message"], doi_norm))
        if not isinstance(js, dict) or "is_oa" not in js:
            return _done("error", error="Unpaywall payload without is_oa")
        return _done("success", data=parse_unpaywall(js))
    except Exception as e:
        return _done("error", error=f"{type(e).__name__}: {e}")


def query_crossref(doi, timeout=DEFAULT_TIMEOUT_S, cache_dir=None):
    """Crossref works lookup for ONE DOI. See module docstring. Never raises."""
    d = normalize_doi(doi)
    if not d:
        return {"source": "crossref", "status": "error", "doi": None, "query_sent": doi,
                "error": f"not a DOI: {doi!r}", "n_http_gets": 0, "elapsed_s": 0.0}
    return _fetch("crossref", d, timeout, cache_dir)


def query_unpaywall(doi, timeout=DEFAULT_TIMEOUT_S, cache_dir=None):
    """Unpaywall v2 lookup for ONE DOI (requires WITT_UNPAYWALL_EMAIL; else 'tool-unavailable'). Never raises."""
    d = normalize_doi(doi)
    if not d:
        return {"source": "unpaywall", "status": "error", "doi": None, "query_sent": doi,
                "error": f"not a DOI: {doi!r}", "n_http_gets": 0, "elapsed_s": 0.0}
    return _fetch("unpaywall", d, timeout, cache_dir)


def query_doi(doi, timeout=DEFAULT_TIMEOUT_S, cache_dir=None, sources=SOURCES):
    """Core logic (stdlib-only, importable for standalone testing): both sources over one DOI.

    Returns {status (= Crossref's row status, or Unpaywall's when Crossref was not requested), doi,
             query_sent (the DOI as received), elapsed_s, n_http_gets (sum), data: {doi, crossref: <row>,
             unpaywall: <row>}} — a source not in `sources` is a row {status:'not-requested'}.
    `timeout` is the socket timeout PER GET (at most one GET per source)."""
    t0 = time.monotonic()
    d = normalize_doi(doi)
    if not d:
        return {"status": "error", "doi": None, "query_sent": doi, "error": f"not a DOI: {doi!r}",
                "elapsed_s": round(time.monotonic() - t0, 4), "n_http_gets": 0,
                "data": {"doi": None, "crossref": None, "unpaywall": None}}
    rows = {}
    for src in SOURCES:
        rows[src] = (_fetch(src, d, timeout, cache_dir) if src in sources
                     else {"source": src, "status": "not-requested", "doi": d, "n_http_gets": 0})
    lead = rows["crossref"] if "crossref" in sources else rows["unpaywall"]
    out = {"status": lead["status"], "doi": d, "query_sent": doi,
           "elapsed_s": round(time.monotonic() - t0, 4),
           "n_http_gets": sum(int(r.get("n_http_gets") or 0) for r in rows.values()),
           "data": {"doi": d, "crossref": rows["crossref"], "unpaywall": rows["unpaywall"]}}
    if lead.get("error"):
        out["error"] = lead["error"]
    return out


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class DOI_resolve_crossref_unpaywall_workspace:
    name = "DOI_resolve_crossref_unpaywall_workspace"
    description = (
        "Resolve ONE DOI against Crossref (works metadata: title, journal, year, authors, abstract when "
        "deposited, citation count) and Unpaywall (open-access status and best OA location). Each source "
        "has its own status row: success | no-match (HTTP 404: the agency does not know the DOI) | error | "
        "tool-unavailable (Unpaywall without WITT_UNPAYWALL_EMAIL — no email is invented). Crossref "
        "mailto is sent only when a contact env is set and is declared, never echoed (ADR-0080)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI in any common form, e.g. '10.1242/dev.02071' or 'https://doi.org/10.1242/dev.02071'."},
            "sources": {"type": ["array", "null"], "items": {"type": "string", "enum": list(SOURCES)},
                        "description": "Subset of ['crossref','unpaywall'] (default both)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds per HTTP GET (default 30)."},
        },
        "required": ["doi"],
    }

    def run(self, doi, sources=None, timeout=DEFAULT_TIMEOUT_S):
        return query_doi(doi, timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout,
                         sources=tuple(sources) if sources else SOURCES)


if __name__ == "__main__":
    # Standalone smoke (real API; Unpaywall only with WITT_UNPAYWALL_EMAIL; writes the same-day raw cache).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = query_doi(sys.argv[1] if len(sys.argv) > 1 else "10.1242/dev.02071")
    print(json.dumps(out, ensure_ascii=False, indent=2))
