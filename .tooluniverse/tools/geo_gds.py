"""
geo_gds — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 lote C / rebanada C5).

WHY THIS TOOL EXISTS: the search harness of ADR-0080 dispatches a `geo` family (evidence_kind 'dataset')
so a question about a zebrafish gene can surface the PUBLIC EXPRESSION DATASETS that mention it — an
evidence tier the literature indexes and ZFIN do not serve. Until now GEO was reachable only through the
Tool Universe MCP (Layer 2, `GEO_search_rnaseq_datasets`), which the webapp pipeline cannot call
(ADR-0062: the SDK does not install in the query-service container). So the source runs at Layer 0:
stdlib-pure, importable by path, like its siblings in this directory.

WHAT IT DOES: NCBI E-utilities esearch (db=gds) -> esummary (db=gds). Returns dataset records
{uid, accession, entry_type, title, summary, taxon, n_samples, pdat, pubmedids, gse, gpl, ftplink, url}.
NO API key required; NCBI_API_KEY is honored when present and raises the rate limit.

IDENTITY AND PACING ARE BORROWED, NOT RE-IMPLEMENTED (ADR-0080 spec D): this module imports
`pubmed_literature.py` BY PATH (same directory) and reuses its `_identity_params()` (tool=witt-organogenesis
always, email=$WITT_NCBI_EMAIL only when set — `ncbi_identity` 'declared' | 'missing', never invented),
`_key_param()` / `_api_key_present()` (NCBI_API_KEY), `resolve_min_interval_s()` (0.34 s without key,
0.10 s with, WITT_NCBI_MIN_INTERVAL_S overrides) and its `net_throttle` handle: the process-wide Throttle
for `eutils.ncbi.nlm.nih.gov` is the SAME object PubMed uses, so a GEO call and a PubMed call from two
worker threads never race the host (ADR-0078 §6). One retry on HTTP 429 (Retry-After or 1 s); a second
429 is a declared 'error' — never a loop. If pubmed_literature cannot be imported the tool returns
status 'error' NAMING the import failure (declared, not disguised).

THREE STATES, NEVER CONFLATED (ADR-0043 / ADR-0080):
  'success'        — esearch count > 0 and >= 1 record parsed from esummary
  'no-match'       — esearch answered count 0 (searched, nothing found; NOT an error, NOT hidden as success)
  'error'          — a call failed ({status:'error', error:'<Type>: <msg>', http_status?})
  'skipped-budget' — timeout <= 0 before the call: the caller's wall clock is spent; NO request is sent
Every cap is declared: `retmax_sent` (WITT_GEO_RETMAX, default 10), `summary_chars_cap` (SUMMARY_CAP),
`summary_truncated` per record, `records_truncated` when esummary served fewer uids than esearch listed.

READ CACHE PER DAY (CLAUDE.md §6 cache discipline): the two RAW responses are persisted together at
mcp_cache/raw_geo_gds_<slug>_<sha8>_<YYYYMMDD>.json as {fetched_at, esearch:{url,response}, esummary:
{url,response}}; a same-day file is served instead of the network (`cache_hit: True`, `cached_at`), and the
path travels in `cache_path` (relative to the repo root). `cache_dir` overrides the directory — for tests.
The raw file carries the `raw_` prefix because it IS the untouched parsed body of each response.

ENV VARS (all with a declared default):
  WITT_GEO_RETMAX            default 10     — max dataset uids asked of esearch (clamped to [1, 500])
  WITT_GEO_ORGANISM          default 'Danio rerio' — appended as `AND "<organism>"[Organism]`; set to '' to
                                             send the caller's term alone (declared in `organism_sent`)
  NCBI_API_KEY, WITT_NCBI_EMAIL, WITT_NCBI_MIN_INTERVAL_S — read by pubmed_literature (ADR-0078)

OUTPUT CONTRACT:
  {status, query_sent, url_sent: [..], elapsed_s, n_http_gets, cache_hit, cache_path, cached_at,
   ncbi_identity, throttle, retries_429, rate_limit_headers, rate_limit_headers_from,
   identifier_provenance: 'ncbi-geo-esummary', evidence_kind: 'dataset',
   data: {query, query_sent, organism_sent, retmax_sent, n_found_total, n_uids, n_records,
          records_truncated, summary_chars_cap, records: [...]}}
Accessions returned are EXTERNAL identifiers RETRIEVED with provenance (NCBI GEO), not verified-for-
citation (CLAUDE.md §7 — the integrator resolves or gap_flags them; nothing here decides).
Fixture recorded from the live API: rag_index/query_service/fixtures/geo_gds_wt1a_20260915.json
Offline gate: rag_index/query_service/smoke_tools_c.py
"""
import datetime
import hashlib
import importlib.util
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "mcp_cache"                        # ADR-0080: declared cache root (gitignored)
_PL_PATH = Path(__file__).resolve().parent / "pubmed_literature.py"
_UA = {"User-Agent": "witt-organo/1.0 (geo-gds-tool)", "Accept": "application/json"}

DEFAULT_TIMEOUT_S = 30        # urllib socket timeout per GET when the caller passes none
DEFAULT_RETMAX = 10           # ADR-0080: WITT_GEO_RETMAX
DEFAULT_ORGANISM = "Danio rerio"   # ADR-0080: WITT_GEO_ORGANISM ('' disables the block)
SUMMARY_CAP = 1200            # chars of `summary` kept per record; the cut is declared per record
RETMAX_CEILING = 500          # esummary db=gds accepts a comma list; kept far under the URL limit
_RATE_HEADER_PREFIX = "x-ratelimit"
IDENTIFIER_PROVENANCE = "ncbi-geo-esummary"
EVIDENCE_KIND = "dataset"
_GEO_ACC_URL = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="


def _load_pubmed_literature():
    """pubmed_literature.py loaded BY PATH (the directory starts with a dot: not a package). Returns
    (module | None, error | None) — a failed import is declared by the caller, never silently absent."""
    try:
        spec = importlib.util.spec_from_file_location("_witt_ws_pubmed_literature_for_geo", _PL_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


_PL, _PL_IMPORT_ERROR = _load_pubmed_literature()


def _get(url, timeout=DEFAULT_TIMEOUT_S, with_headers=False):
    """The ONLY network seam of this module (the offline smoke monkeypatches it to serve fixtures).
    Returns parsed JSON; with `with_headers=True` returns (json, rate_limit_headers_or_None) — the
    X-RateLimit-* headers are a MEASUREMENT: None means the response carried none."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        js = json.loads(body)
        if not with_headers:
            return js
        rl = None
        hdrs = getattr(r, "headers", None)
        if hdrs is not None:
            try:
                found = {k: v for k, v in hdrs.items() if str(k).lower().startswith(_RATE_HEADER_PREFIX)}
            except Exception:
                found = {}
            rl = found or None
        return js, rl


def resolve_retmax(retmax=None):
    """ADR-0080: explicit `retmax` > WITT_GEO_RETMAX > DEFAULT_RETMAX (10). Clamped to [1, RETMAX_CEILING]."""
    val = retmax
    if val is None:
        raw = os.environ.get("WITT_GEO_RETMAX", "").strip()
        val = raw if raw else DEFAULT_RETMAX
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = DEFAULT_RETMAX
    return max(1, min(n, RETMAX_CEILING))


def resolve_organism(organism=None):
    """ADR-0080: explicit `organism` (None = use env) > WITT_GEO_ORGANISM > 'Danio rerio'. The empty
    string (argument or env) DISABLES the organism block — declared in `organism_sent: None`."""
    if organism is not None:
        return organism.strip() or None
    if "WITT_GEO_ORGANISM" in os.environ:
        return os.environ.get("WITT_GEO_ORGANISM", "").strip() or None
    return DEFAULT_ORGANISM


def build_gds_term(query, organism):
    """Deterministic term for esearch db=gds: `(<query>) AND "<organism>"[Organism]` when an organism
    applies, else the caller's term alone. Never adds anatomy or defaults beyond the organism block."""
    q = (query or "").strip()
    if not q:
        return ""
    if organism:
        return f'({q}) AND "{organism}"[Organism]'
    return q


def _slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:n].strip("-") or "query")


def _cache_path(cache_dir, term, date):
    sha8 = hashlib.sha256(term.encode("utf-8")).hexdigest()[:8]
    return Path(cache_dir) / f"raw_geo_gds_{_slug(term)}_{sha8}_{date}.json"


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _cap(text, cap):
    """(text[:cap], truncated) — the cut is declared, never silent."""
    t = text or ""
    return (t[:cap], len(t) > cap) if t else (None, False)


def parse_gds_summary(uid, rec):
    """ONE esummary db=gds record -> the tool's record. Deterministic transform; nothing inferred."""
    rec = rec or {}
    summary, trunc = _cap(rec.get("summary"), SUMMARY_CAP)
    acc = rec.get("accession") or None
    pmids = rec.get("pubmedids") or []
    return {
        "uid": str(uid),
        "accession": acc,
        "entry_type": rec.get("entrytype") or None,
        "gds_type": rec.get("gdstype") or None,
        "title": rec.get("title") or None,
        "summary": summary,
        "summary_truncated": trunc,
        "taxon": rec.get("taxon") or None,
        "n_samples": rec.get("n_samples") if isinstance(rec.get("n_samples"), int) else None,
        "pdat": rec.get("pdat") or None,
        "pubmedids": [str(p) for p in pmids] if isinstance(pmids, list) else [],
        "gse": rec.get("gse") or None,
        "gpl": rec.get("gpl") or None,
        "ftplink": rec.get("ftplink") or None,
        "url": (_GEO_ACC_URL + acc) if acc else None,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
    }


def _headers_of_error(e):
    hdrs = getattr(e, "headers", None)
    if hdrs is None:
        return None
    try:
        found = {k: v for k, v in hdrs.items() if str(k).lower().startswith(_RATE_HEADER_PREFIX)}
    except Exception:
        found = {}
    return found or None


def query_gds(query, retmax=None, organism=None, timeout=DEFAULT_TIMEOUT_S, cache_dir=None):
    """Core logic (stdlib-only, importable for standalone testing). See the module docstring for the
    contract. `cache_dir` overrides mcp_cache (tests only); `timeout` is the socket timeout PER GET
    (esearch + esummary = 2 GETs) — the integrator passes its remaining budget; <= 0 sends nothing."""
    t0 = time.monotonic()
    organism_sent = resolve_organism(organism)
    n_retmax = resolve_retmax(retmax)
    term = build_gds_term(query, organism_sent)
    base = {
        "query_sent": term or None, "url_sent": [], "elapsed_s": 0.0, "n_http_gets": 0,
        "cache_hit": False, "cache_path": None, "cached_at": None,
        "ncbi_identity": None, "throttle": None, "retries_429": 0,
        "rate_limit_headers": None, "rate_limit_headers_from": None,
        "identifier_provenance": IDENTIFIER_PROVENANCE, "evidence_kind": EVIDENCE_KIND,
    }
    data_head = {"query": query, "query_sent": term or None, "organism_sent": organism_sent,
                 "retmax_sent": n_retmax}

    def _done(status, **kw):
        base["elapsed_s"] = round(time.monotonic() - t0, 4)
        return dict(base, status=status, **kw)

    if not term:
        return _done("error", error="empty query", data=data_head)
    if timeout is not None and timeout <= 0:
        return _done("skipped-budget", data=data_head,
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    if _PL is None:
        return _done("error", data=data_head,
                     error=f"pubmed_literature not importable by path: {_PL_IMPORT_ERROR}")
    if getattr(_PL, "net_throttle", None) is None:
        return _done("error", data=data_head,
                     error=f"net_throttle not importable: {getattr(_PL, '_THROTTLE_IMPORT_ERROR', None)}")

    ident_frag, ncbi_identity = _PL._identity_params()
    min_interval_s, interval_src = _PL.resolve_min_interval_s()
    base["ncbi_identity"] = ncbi_identity
    base["throttle"] = {"host": _PL._EUTILS_HOST, "min_interval_s": min_interval_s,
                        "min_interval_source": interval_src, "shared_with": "pubmed_literature",
                        "api_key_present": _PL._api_key_present(), "waited_s": 0.0}
    q = urllib.parse.quote(term)
    key_frag = _PL._key_param()
    url_search = (f"{_PL._EUTILS}/esearch.fcgi?db=gds&term={q}&retmode=json&retmax={n_retmax}"
                  f"{ident_frag}{key_frag}")

    # ---- read cache (same day) --------------------------------------------------------------------------
    cdir = Path(cache_dir) if cache_dir else CACHE_DIR
    date = _now_utc().strftime("%Y%m%d")
    cpath = _cache_path(cdir, term, date)
    base["cache_path"] = _rel(cpath)
    cached = None
    if cpath.exists():
        try:
            cached = json.loads(cpath.read_text(encoding="utf-8"))
            if not (isinstance(cached, dict) and "esearch" in cached):
                cached = None
        except Exception:
            cached = None   # corrupt cache: the network path re-creates it (declared as a miss)

    thr = _PL.net_throttle.get_throttle(_PL._EUTILS_HOST, min_interval_s)

    def _record_headers(rl, label):
        if rl:
            base["rate_limit_headers"], base["rate_limit_headers_from"] = dict(rl), label

    def _call(url, label):
        stats = {}

        def _once():
            base["throttle"]["waited_s"] += thr.wait()
            base["n_http_gets"] += 1
            base["url_sent"].append(url)
            try:
                js, rl = _get(url, timeout=timeout, with_headers=True)
            except urllib.error.HTTPError as e:
                _record_headers(_headers_of_error(e), label)
                raise
            _record_headers(rl, label)
            return js
        try:
            return _PL.net_throttle.retry_once_on_429(_once, stats)
        finally:
            base["retries_429"] += int(stats.get("retries_429") or 0)

    try:
        if cached is not None:
            base["cache_hit"], base["cached_at"] = True, cached.get("fetched_at")
            js = cached["esearch"]["response"]
            js2 = (cached.get("esummary") or {}).get("response")
            base["url_sent"] = [cached["esearch"].get("url")] + ([cached["esummary"]["url"]] if js2 else [])
        else:
            js = _call(url_search, "esearch")
            js2 = None
        res = js.get("esearchresult", {}) or {}
        ids = [str(x) for x in (res.get("idlist") or [])]
        n_total = int(res.get("count", 0) or 0)
        if not ids:
            if cached is None:
                _cache_write(cpath, url_search, js, None, None)
            return _done("no-match", data=dict(data_head, n_found_total=n_total, n_uids=0, n_records=0,
                                               records_truncated=False, summary_chars_cap=SUMMARY_CAP,
                                               records=[]))
        url_summ = (f"{_PL._EUTILS}/esummary.fcgi?db=gds&id={','.join(ids)}&retmode=json"
                    f"{ident_frag}{key_frag}")
        if js2 is None:
            js2 = _call(url_summ, "esummary")
            _cache_write(cpath, url_search, js, url_summ, js2)
        summ = js2.get("result", {}) or {}
        records = [parse_gds_summary(uid, summ.get(uid)) for uid in ids if isinstance(summ.get(uid), dict)]
        status = "success" if records else "no-match"
        return _done(status, data=dict(data_head, n_found_total=n_total, n_uids=len(ids),
                                       n_records=len(records), records_truncated=len(records) < len(ids),
                                       summary_chars_cap=SUMMARY_CAP, records=records))
    except urllib.error.HTTPError as e:
        return _done("error", http_status=getattr(e, "code", None), data=data_head,
                     error=f"HTTPError: {getattr(e, 'code', '?')} {getattr(e, 'reason', '')}".strip())
    except Exception as e:
        return _done("error", data=data_head, error=f"{type(e).__name__}: {e}")


def _cache_write(path, url_search, js_search, url_summ, js_summ):
    """Persist the RAW responses (untouched parsed bodies) for the same-day read cache. Best effort:
    a cache that cannot be written never fails the call (the result declares cache_hit False)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        env = {"fetched_at": _now_utc().isoformat(timespec="seconds"),
               "esearch": {"url": url_search, "response": js_search}}
        if js_summ is not None:
            env["esummary"] = {"url": url_summ, "response": js_summ}
        path.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class GEO_gds_search_workspace:
    name = "GEO_gds_search_workspace"
    description = (
        "GEO DataSets search via NCBI E-utilities (esearch + esummary, db=gds). Returns dataset records "
        "{accession, entry_type, title, summary, taxon, n_samples, pdat, pubmedids, gse, gpl, url}. The "
        "term is wrapped as `(<query>) AND \"Danio rerio\"[Organism]` (WITT_GEO_ORGANISM). No API key; "
        "honors NCBI_API_KEY; borrows identity (tool=witt-organogenesis, email=$WITT_NCBI_EMAIL) and the "
        "process-wide eutils throttle from pubmed_literature. Status 'no-match' = searched, nothing "
        "found (ADR-0080). Accessions are retrieved identifiers, not verified-for-citation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term, e.g. 'wt1a' or 'pronephros single cell'."},
            "retmax": {"type": ["integer", "null"], "description": "Max dataset uids (default WITT_GEO_RETMAX, 10)."},
            "organism": {"type": ["string", "null"],
                         "description": "Organism block (default WITT_GEO_ORGANISM = 'Danio rerio'; '' disables)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds per HTTP GET (default 30)."},
        },
        "required": ["query"],
    }

    def run(self, query, retmax=None, organism=None, timeout=DEFAULT_TIMEOUT_S):
        return query_gds(query, retmax=retmax, organism=organism,
                         timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    # Standalone smoke (no key required, real API; writes the same-day raw cache under mcp_cache/).
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = query_gds(" ".join(sys.argv[1:]) or "wt1a", retmax=5)
    print(json.dumps(out, ensure_ascii=False, indent=2))
