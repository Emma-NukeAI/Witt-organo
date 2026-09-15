"""
STRING_zebrafish_interaction_partners — Layer 0 workspace tool (ADR-0080, harness lote B, added 2026-09-15).

WHY THIS TOOL EXISTS (ADR-0080 §4 harness de busqueda):
STRING is the interaction tier of the harness. Its zebrafish (7955) partner lists are mostly
text-mining / co-expression / transfer scores, i.e. PREDICTIONS, not observed zebrafish interactions.
The doctrine forces the label: every partner item carries label 'predictive' with the per-channel
scores copied verbatim so the synthesizer (and the panel) can see WHY the score is what it is. A
partner list is a hypothesis generator — never a measurement.

WHAT IT DOES:
ONE GET to https://version-12-0.string-db.org/api/json/interaction_partners?identifiers=<sym>
&species=7955&limit=<n>. Public, keyless, JSON, read-only. STRING asks clients to space calls 1 s
apart: the call goes through net_throttle (analysis/scripts/lib, stdlib-pure, same registry the
pubmed tool uses) with MIN_INTERVAL_S = 1.0 per host; the seconds actually waited are a MEASUREMENT
declared in `throttle.waited_s`. If net_throttle is not importable the tool returns status 'error'
naming it (declared, not disguised — same policy as pubmed_literature).

ADR-0080 doctrine (same skeleton as zfin_zebrafish.py):
  * `_get(url, timeout)` sole network seam; three states 'success' | 'no-match' | 'error'.
  * The API resolves the symbol itself: `preferredName_A` echoing the requested symbol
    (case-insensitive) is the RESOLUTION check (`symbol_resolved`); items whose A-side is a different
    protein are COUNTED in `n_partners_other_query` and excluded (a multi-identifier answer would
    otherwise be mixed into one gene's partners). stringId (7955.ENSDARP…) is copied verbatim,
    identifier_provenance 'string-db-v12:interaction_partners'.
  * Cut declared: `limit_sent`, `truncated_by_limit` (True when returned == limit — STRING sends no
    total, so this is the honest upper-bound signal, declared as such in `truncated_semantics`).
  * Per-day read cache mcp_cache/string_<slug>_l<limit>_<YYYYMMDD>.json (`cache_hit`, `cache_ref`);
    a cache hit does NOT wait on the throttle (no network call is made).
  * `timeout` propagated; timeout<=0 -> BudgetExhausted without network.

Measured live 2026-09-15 (wt1a): HTTP 200, 10 partners (tbx18 0.961 … tp53 0.773), every score
dominated by tscore (text mining) — the 'predictive' label is not theoretical.
Fixture: rag_index/query_service/fixtures/string_wt1a_20260915.json
Offline gate: rag_index/query_service/smoke_tools_b.py
"""
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# net_throttle lives in analysis/scripts/lib (stdlib-pure, same repo, same COPY . /app). Loaded the way
# pubmed_literature loads `lib`: repo root = .tooluniverse/tools/<this>.py -> parents[2].
_ROOT = Path(__file__).resolve().parents[2]
_LIB_PARENT = str(_ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)
try:
    from lib import net_throttle  # noqa: E402
    _THROTTLE_IMPORT_ERROR = None
except Exception as _e:  # declared, not disguised: query_string returns status 'error' naming it
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

_BASE = "https://version-12-0.string-db.org/api/json/interaction_partners"
_HOST = "version-12-0.string-db.org"
_UA = {"User-Agent": "witt-organo/1.0 (string-tool)", "Accept": "application/json"}

TOOL_FAMILY = "string"
EVIDENCE_KIND = "interaction-partner"
LABEL = "predictive"               # ADR-0080: STRING scores are predictions (text-mining/transfer/coexpr)
LABEL_NOTE = "STRING combined score is a prediction (channels declared per item); not an observed interaction"
IDENTIFIER_PROVENANCE = "string-db-v12:interaction_partners"
SPECIES = 7955
DEFAULT_LIMIT = 10                 # `limit=10` sent to the API; declared in truncated_by_limit
DEFAULT_TIMEOUT_S = 30
MIN_INTERVAL_S = 1.0               # STRING's requested spacing between calls (per host, process-wide)
TRUNCATED_SEMANTICS = "returned == limit (STRING sends no total; upper-bound signal, not a count)"
SCORE_CHANNELS = ("nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore")

CACHE_DIR = _ROOT / "mcp_cache"


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module. Returns (payload_json, headers_lower)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
        headers = {k.lower(): v for k, v in r.headers.items()}
    return payload, headers


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "symbol"


def _cache_path(symbol, limit):
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    return CACHE_DIR / f"{TOOL_FAMILY}_{_slug(symbol)}_l{int(limit)}_{date}.json"


def _cache_read(path):
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return blob["response"], blob.get("headers") or {}
    except Exception:
        return None


def _cache_write(path, url, payload, headers):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        blob = {"_cache": {"tool": TOOL_FAMILY, "url": url,
                           "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                "headers": headers, "response": payload}
        path.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def build_url(symbol, limit=DEFAULT_LIMIT):
    return f"{_BASE}?identifiers={urllib.parse.quote(symbol)}&species={SPECIES}&limit={int(limit)}"


def parse_partner(row):
    """ONE STRING row -> normalized item; scores copied verbatim, label 'predictive'."""
    sid_b = row.get("stringId_B")
    name_b = row.get("preferredName_B")
    channels = {c: row.get(c) for c in SCORE_CHANNELS if c in row}
    score = row.get("score")
    return {
        "evidence_id": f"string:{row.get('stringId_A')}--{sid_b}" if sid_b else None,
        "kind": EVIDENCE_KIND,
        "source_family": TOOL_FAMILY,
        "label": LABEL,
        "label_note": LABEL_NOTE,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
        "query_string_id": row.get("stringId_A"),
        "query_symbol": row.get("preferredName_A"),
        "partner_string_id": sid_b,
        "partner_symbol": name_b,
        "taxon_id": row.get("ncbiTaxonId"),
        "combined_score": score,
        "score_channels": channels,
        "dominant_channel": (max(channels, key=lambda c: channels[c] or 0) if channels else None),
        "statement": (f"{row.get('preferredName_A')} — {name_b} (STRING combined score {score}, predictive)"
                      if name_b else None),
        "text": None,
        "url": f"https://string-db.org/network/{sid_b}" if sid_b else None,
    }


def query_string(symbol, limit=DEFAULT_LIMIT, timeout=DEFAULT_TIMEOUT_S, use_cache=True):
    """Core logic (stdlib-only) — ADR-0080.

    Returns {status, query_sent, elapsed_s, cache_hit, cache_ref, n_http_gets, evidence_kind, label,
             throttle: {host, min_interval_s, waited_s}, data|error}
      status 'success' | 'no-match' (the API ran, zero partner rows for this symbol) | 'error'
             (BudgetExhausted when timeout<=0; 'net_throttle not importable' when the limiter is missing;
             no request sent in either case)
      data = {symbol, taxon, symbol_resolved, query_string_ids[], n_returned_by_api, n_partners,
              n_partners_other_query, limit_sent, truncated_by_limit, truncated_semantics,
              cache_error, items[]}
    """
    t0 = time.monotonic()
    sym = (symbol or "").strip()
    url = build_url(sym, limit) if sym else None
    base = {"query_sent": url, "cache_hit": False, "cache_ref": None, "n_http_gets": 0,
            "evidence_kind": EVIDENCE_KIND, "label": LABEL,
            "throttle": {"host": _HOST, "min_interval_s": MIN_INTERVAL_S, "waited_s": 0.0}}

    def _done(**kw):
        return dict(base, elapsed_s=round(time.monotonic() - t0, 3), **kw)

    if not sym:
        return _done(status="error", error="empty symbol")
    if timeout is not None and timeout <= 0:
        return _done(status="error",
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    if net_throttle is None:
        return _done(status="error", error=f"net_throttle not importable: {_THROTTLE_IMPORT_ERROR}")
    try:
        path = _cache_path(sym, limit)
        cached = _cache_read(path) if use_cache else None
        cache_error = None
        if cached is not None:
            payload, headers = cached
            base["cache_hit"] = True
        else:
            thr = net_throttle.get_throttle(_HOST, MIN_INTERVAL_S)
            base["throttle"]["waited_s"] = round(thr.wait(), 3)
            payload, headers = _get(url, timeout=timeout)
            base["n_http_gets"] = 1
            if use_cache:
                cache_error = _cache_write(path, url, payload, headers)
        if use_cache and cache_error is None and path.exists():
            try:
                base["cache_ref"] = str(path.relative_to(_ROOT))
            except ValueError:
                base["cache_ref"] = str(path)

        rows = payload if isinstance(payload, list) else []
        items, n_other = [], 0
        for r in rows:
            if str(r.get("preferredName_A") or "").lower() != sym.lower():
                n_other += 1
                continue
            items.append(parse_partner(r))
        data = {
            "symbol": sym,
            "taxon": f"NCBITaxon:{SPECIES}",
            "symbol_resolved": bool(items),
            "query_string_ids": sorted({it["query_string_id"] for it in items if it["query_string_id"]}),
            "n_returned_by_api": len(rows),
            "n_partners": len(items),
            "n_partners_other_query": n_other,
            "limit_sent": int(limit),
            "truncated_by_limit": len(rows) >= int(limit) and len(rows) > 0,
            "truncated_semantics": TRUNCATED_SEMANTICS,
            "cache_error": cache_error,
            "items": items,
        }
        return _done(status="success" if items else "no-match", data=data)
    except Exception as e:
        return _done(status="error", error=f"{type(e).__name__}: {e}")


try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class STRING_zebrafish_interaction_partners:
    name = "STRING_zebrafish_interaction_partners"
    description = (
        "Predicted interaction partners of a zebrafish (taxon 7955) gene from STRING v12 "
        "(interaction_partners). Every item is labeled 'predictive' with its per-channel scores (text "
        "mining, coexpression, experiments, databases…) copied verbatim (ADR-0080). Calls are paced 1 s "
        "apart per host through net_throttle. No API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "limit": {"type": ["integer", "null"], "description": "Partners requested (default 10); declared in truncated_by_limit."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 30)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, limit=DEFAULT_LIMIT, timeout=DEFAULT_TIMEOUT_S):
        return query_string(symbol, DEFAULT_LIMIT if limit is None else limit,
                            timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = query_string(sys.argv[1] if len(sys.argv) > 1 else "wt1a")
    print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
    for it in (r.get("data") or {}).get("items", []):
        print(f"  - {it['partner_symbol']} score={it['combined_score']} dominant={it['dominant_channel']} [{it['label']}]")
