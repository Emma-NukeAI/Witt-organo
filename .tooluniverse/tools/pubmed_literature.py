"""
pubmed_literature — a custom ToolUniverse workspace tool (added 2026-08-20, tapón 1·B / ADR-0062;
identity + throttle + retmax + measured headers added 2026-09-14, ADR-0078).

WHY THIS TOOL EXISTS: `tool_universe_directive` names `PubMed_search_articles` as the first call an
agent should run when Path B fires — and the webapp pipeline could not run it. Installing the SDK in
the query-service container was MEASURED and rejected (ADR-0062): the pinned tooluniverse==1.2.6 does
not even resolve on Python 3.12 (its `fitz>=0.0.1.dev2` has no installable distribution), and the
latest resolves to 173 packages (playwright + browser binaries, faiss-cpu, onnxruntime, pandas,
azure-ai-*, three web frameworks) — into the container whose founding lesson (ADR-0039) is that a
contaminated interpreter degrades silently. So the tool's UNDERLYING source runs at Layer 0 instead:
stdlib-pure, importable by path, like its two siblings here.

WHAT IT DOES: PubMed search via NCBI E-utilities (esearch -> esummary). No API key required;
NCBI_API_KEY (already optional in .mcp.json) is honored when present and raises the rate limit.
Returns ranked records with PMID, title, year, journal. Full text is NOT fetched here — the caller
reuses fetch_paper.fetch_external("PMID:x") (one fetch pipeline, one cache discipline).

WHAT IT ADDS over europepmc_literature: Europe PMC indexes PubMed, so COVERAGE overlap is near-total —
the value is RANKING diversity (PubMed's relevance sort surfaces different top-k papers than EPMC's)
plus source independence (EPMC down/empty does not silence PubMed). Callers MUST dedup by PMID or the
same paper enters the evidence twice.

ADR-0078 HYGIENE (what the 2026-09-13 audit found and this file now fixes):
  * Identity. NCBI asks every E-utilities client to send `tool` and `email`. `tool=witt-organogenesis`
    is always sent; `email` is sent ONLY when WITT_NCBI_EMAIL is set. If it is missing we do NOT invent
    one — the output declares `ncbi_identity: 'missing'` so the ledger shows it (three states: the env
    is either declared or absent; an absent value is never filled with an optimistic default).
  * Throttle. The service runs WITT_RUN_WORKERS threads in ONE uvicorn process (ADR-0048); with no pacing
    two workers race the same host and NCBI (X-RateLimit-Limit: 3 without a key) answers 429 — which then
    looked like "no results". Every esearch/esummary now goes through the process-wide Throttle for
    `eutils.ncbi.nlm.nih.gov` (analysis/scripts/lib/net_throttle.py): 0.34 s between calls without
    NCBI_API_KEY, 0.10 s with it; WITT_NCBI_MIN_INTERVAL_S overrides the derived value. One retry on
    HTTP 429 (Retry-After or 1 s); a second 429 is a declared `status: 'error'` — never a loop.
  * retmax. Parametrizable: `retmax` argument, else WITT_PATH_B_RETMAX (default 20). The tool returns UP TO
    retmax records — top-n selection belongs to the integrator (answer_pipeline), not here. `limit` is
    kept as a legacy alias for existing callers.
  * Measurements out. `query_sent` (the literal term sent), `retmax_sent`, and `rate_limit_headers`
    (NCBI's X-RateLimit-* response headers, as measured; None when the response carried none).
    ADR-0078 corrector: the headers are those of ONE response — the LAST one that carried them — and
    `rate_limit_headers_from` names it ('esearch' | 'esummary' | None). They are never merged across the
    two calls (a Remaining from esummary next to a Limit from esearch is not a measurement of anything).
    On an HTTPError (429 included) the headers of the ERROR response are read — precisely the moment
    NCBI throttles is when the measurement matters.

OUTPUT CONTRACT — additive, nothing removed:
  {status: 'success', ncbi_identity, throttle, retries_429, rate_limit_headers, rate_limit_headers_from,
   data: {query, query_sent, retmax_sent, n_found_total, records: [{pmid, title, year, journal}]}}
  {status: 'error', error, ncbi_identity, throttle, retries_429, rate_limit_headers, rate_limit_headers_from,
   http_status?, data?: {query, query_sent, retmax_sent}}
  `throttle` = {host, min_interval_s, api_key_present, waited_s}  (waited_s is measured sleep, summed).

Read-only HTTP GET, pure stdlib (urllib) so the logic is importable + testable without the
tooluniverse package. PMIDs returned are EXTERNAL identifiers RETRIEVED with provenance (NCBI), not
verified-for-citation (CLAUDE.md §7 — verify_output still gates whatever gets cited).
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# net_throttle lives in analysis/scripts/lib (stdlib-pure, same repo, same COPY . /app). Loaded the way
# fetch_paper/answer_pipeline load `lib`: repo root = .tooluniverse/tools/<this>.py -> parents[2].
_ROOT = Path(__file__).resolve().parents[2]
_LIB_PARENT = str(_ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)
try:
    from lib import net_throttle  # noqa: E402
    _THROTTLE_IMPORT_ERROR = None
except Exception as _e:  # declared, not disguised: query_pubmed returns status 'error' naming it
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_EUTILS_HOST = "eutils.ncbi.nlm.nih.gov"
_UA = {"User-Agent": "witt-organo/1.0 (pubmed-tool)", "Accept": "application/json"}

NCBI_TOOL_NAME = "witt-organogenesis"                 # ADR-0078: identidad fija del cliente
DEFAULT_RETMAX = 20                                   # ADR-0078: WITT_PATH_B_RETMAX
DEFAULT_MIN_INTERVAL_NO_KEY_S = 0.34                  # ADR-0078: NCBI X-RateLimit-Limit: 3/s sin llave
DEFAULT_MIN_INTERVAL_WITH_KEY_S = 0.10                # ADR-0078: 10/s con NCBI_API_KEY
_RATE_HEADER_PREFIX = "x-ratelimit"


def _get_with_headers(url, timeout=30):
    """GET url; returns (parsed_json, rate_limit_headers_or_None). Rate-limit headers are a MEASUREMENT:
    None means the response carried none (declared absence, not an empty default)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        rl = None
        hdrs = getattr(r, "headers", None)
        if hdrs is not None:
            try:
                found = {k: v for k, v in hdrs.items() if str(k).lower().startswith(_RATE_HEADER_PREFIX)}
            except Exception:
                found = {}
            if found:
                rl = found
    return json.loads(body), rl


def _get(url, timeout=30):
    """Legacy shape (json only) kept for any external importer."""
    return _get_with_headers(url, timeout)[0]


def _key_param():
    k = os.environ.get("NCBI_API_KEY", "").strip()
    return f"&api_key={urllib.parse.quote(k)}" if k else ""


def _api_key_present():
    return bool(os.environ.get("NCBI_API_KEY", "").strip())


def _identity_params():
    """ADR-0078: (query-string fragment, ncbi_identity state). `tool` always; `email` only from
    WITT_NCBI_EMAIL. Missing env -> state 'missing' (declared in the output; no email is invented)."""
    frag = f"&tool={urllib.parse.quote(NCBI_TOOL_NAME)}"
    email = os.environ.get("WITT_NCBI_EMAIL", "").strip()
    if email:
        return frag + f"&email={urllib.parse.quote(email)}", "declared"
    return frag, "missing"


def resolve_min_interval_s():
    """ADR-0078: WITT_NCBI_MIN_INTERVAL_S if set, else derived from whether NCBI_API_KEY is present
    (0.34 s without, 0.10 s with). Returns (seconds, source) — source is 'env' or 'derived'."""
    raw = os.environ.get("WITT_NCBI_MIN_INTERVAL_S", "").strip()
    if raw:
        try:
            return max(0.0, float(raw)), "env"
        except ValueError:
            pass  # unparseable override -> fall through to the derived value (declared via source)
    if _api_key_present():
        return DEFAULT_MIN_INTERVAL_WITH_KEY_S, "derived"
    return DEFAULT_MIN_INTERVAL_NO_KEY_S, "derived"


def resolve_retmax(retmax=None, limit=None):
    """ADR-0078: explicit `retmax` > legacy `limit` > WITT_PATH_B_RETMAX > DEFAULT_RETMAX (20).
    Clamped to [1, 10000] (E-utilities ceiling)."""
    val = None
    for cand in (retmax, limit):
        if cand is not None:
            val = cand
            break
    if val is None:
        raw = os.environ.get("WITT_PATH_B_RETMAX", "").strip()
        val = raw if raw else DEFAULT_RETMAX
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = DEFAULT_RETMAX
    return max(1, min(n, 10000))


def query_pubmed(query, limit=None, retmax=None, timeout=None):
    """Core logic (stdlib-only, importable for standalone testing).

    Returns {status, ncbi_identity, throttle, retries_429, rate_limit_headers,
             data:{query, query_sent, retmax_sent, n_found_total, records:[{pmid, title, year, journal}]}}.
    `limit` is the legacy alias of `retmax`; with neither, WITT_PATH_B_RETMAX (default 20) applies.
    Records come back UP TO retmax in PubMed relevance order — the integrator picks its top-n.
    `timeout` (ADR-0080 corrector): socket timeout per GET (esearch, esummary); None = the module default
    (30 s). The search harness passes its family budget here so the round budget really bounds the call;
    declared in `timeout_s` / `timeout_s_source`."""
    ident_frag, ncbi_identity = _identity_params()
    n_retmax = resolve_retmax(retmax, limit)
    min_interval_s, interval_src = resolve_min_interval_s()
    throttle_info = {"host": _EUTILS_HOST, "min_interval_s": min_interval_s,
                     "min_interval_source": interval_src,
                     "api_key_present": _api_key_present(), "waited_s": 0.0}
    base = {"ncbi_identity": ncbi_identity, "throttle": throttle_info,
            "retries_429": 0, "rate_limit_headers": None, "rate_limit_headers_from": None,
            "timeout_s": 30 if timeout is None else timeout,
            "timeout_s_source": "module-default" if timeout is None else "caller"}
    term = (query or "").strip()
    if not term:
        return dict(base, status="error", error="empty query")
    data_head = {"query": query, "query_sent": term, "retmax_sent": n_retmax}
    if net_throttle is None:
        return dict(base, status="error", data=data_head,
                    error=f"net_throttle not importable: {_THROTTLE_IMPORT_ERROR}")

    thr = net_throttle.get_throttle(_EUTILS_HOST, min_interval_s)

    def _record_headers(rl, label):
        """ADR-0078 corrector: keep the headers of ONE response (the latest that carried them) and name
        it — never merge esearch's Limit with esummary's Remaining."""
        if rl:
            base["rate_limit_headers"], base["rate_limit_headers_from"] = dict(rl), label

    def _headers_of_error(e):
        hdrs = getattr(e, "headers", None)
        if hdrs is None:
            return None
        try:
            found = {k: v for k, v in hdrs.items() if str(k).lower().startswith(_RATE_HEADER_PREFIX)}
        except Exception:
            found = {}
        return found or None

    def _call(url, label):
        stats = {}
        def _once():
            throttle_info["waited_s"] += thr.wait()
            try:
                js, rl = _get_with_headers(url, **({} if timeout is None else {"timeout": timeout}))
            except urllib.error.HTTPError as e:   # the throttled response IS the measurement
                _record_headers(_headers_of_error(e), label)
                raise
            _record_headers(rl, label)
            return js
        try:
            return net_throttle.retry_once_on_429(_once, stats)
        finally:
            base["retries_429"] += int(stats.get("retries_429") or 0)

    try:
        q = urllib.parse.quote(term)
        js = _call(f"{_EUTILS}/esearch.fcgi?db=pubmed&term={q}&retmode=json"
                   f"&retmax={n_retmax}&sort=relevance{ident_frag}{_key_param()}", "esearch")
        res = js.get("esearchresult", {})
        ids = res.get("idlist", []) or []
        n_total = int(res.get("count", 0) or 0)
        if not ids:
            return dict(base, status="success",
                        data=dict(data_head, n_found_total=n_total, records=[]))
        js2 = _call(f"{_EUTILS}/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json"
                    f"{ident_frag}{_key_param()}", "esummary")
        summ = js2.get("result", {})
        records = []
        for pmid in ids:
            d = summ.get(pmid, {}) or {}
            records.append({
                "pmid": pmid,
                "title": d.get("title"),
                "year": (d.get("pubdate") or "")[:4] or None,
                "journal": d.get("fulljournalname") or d.get("source"),
            })
        return dict(base, status="success",
                    data=dict(data_head, n_found_total=n_total, records=records))
    except urllib.error.HTTPError as e:
        return dict(base, status="error", http_status=getattr(e, "code", None), data=data_head,
                    error=f"HTTPError: {getattr(e, 'code', '?')} {getattr(e, 'reason', '')}".strip())
    except Exception as e:
        return dict(base, status="error", data=data_head, error=f"{type(e).__name__}: {e}")


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class PubMed_search_articles_workspace:
    name = "PubMed_search_articles_workspace"
    description = (
        "PubMed literature search via NCBI E-utilities (esearch + esummary), relevance-ranked. "
        "Returns PMID, title, year, journal. No API key required; honors NCBI_API_KEY when set. "
        "Sends tool=witt-organogenesis and email=$WITT_NCBI_EMAIL (declares ncbi_identity 'missing' "
        "when the email env is absent); process-wide throttle on eutils.ncbi.nlm.nih.gov; one retry on "
        "HTTP 429. Returns up to retmax (WITT_PATH_B_RETMAX, default 20) — the caller picks its top-n. "
        "Coverage overlaps Europe PMC (which indexes PubMed) — the value is ranking diversity and "
        "source independence; DEDUP BY PMID against Europe PMC results before use."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "English keyword query, e.g. 'wt1a zebrafish pronephros'."},
            "retmax": {"type": ["integer", "null"],
                       "description": "Max records returned (default WITT_PATH_B_RETMAX, 20)."},
            "limit": {"type": ["integer", "null"], "description": "Legacy alias of retmax."},
        },
        "required": ["query"],
    }

    def run(self, query, limit=None, retmax=None):
        return query_pubmed(query, limit=limit, retmax=retmax)


if __name__ == "__main__":
    # Standalone smoke test (no key required, real API)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = query_pubmed(" ".join(sys.argv[1:]) or "wt1a zebrafish pronephros", retmax=5)
    print(json.dumps(out, ensure_ascii=False, indent=2))
