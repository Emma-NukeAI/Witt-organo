"""
Alliance_orthologs — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 rebanada C3).

WHY THIS TOOL EXISTS (ADR-0080, harness Layer 0 lote A):
The search harness needs an orthology bridge from a zebrafish gene to its human/mouse counterparts so
the human-centric sources (Reactome, STRING, UniProt human entries) can be queried WITH the label
'inferred-by-orthology' instead of being silently treated as zebrafish evidence. The Alliance of
Genome Resources serves the DIOPT-derived orthology table used by ZFIN itself; no key, read-only GET.

WHAT IT DOES:
Resolves a zebrafish gene SYMBOL -> ZFIN curie (the SAME `search_autocomplete` resolver zfin_zebrafish
uses; a curie may also be passed directly to skip that GET), then GETs
  {_BASE}/gene/{curie}/orthologs?filter.stringency=<stringent|moderate|all>&limit=<n>
and returns one row per ortholog {species, taxon_id, symbol, id, stringency, strict_filter, moderate_filter,
best, best_reverse, confidence, methods_matched[], methods_matched_n, evidence_id, url}. Every identifier comes from the API payload
(`identifier_provenance: 'alliance-api-payload'`), never from memory (CLAUDE.md §7).

DOCTRINE (ADR-0078/0079/0080):
  * THREE states, never conflated: 'success' (>=1 ortholog), 'no-match' (the API answered with zero rows
    for this gene — a MEASUREMENT of the table, not an error — OR the resolver answered and NO zebrafish gene
    carries that symbol: `no_match_reason 'symbol-unresolved'`, ADR-0080 corrector), 'error' (transport or
    parse failed; `error: '<Type>: <msg>'`). 'skipped-budget' when timeout <= 0 BEFORE any GET (zero network calls).
  * Pacing (ADR-0080 corrector): every GET to www.alliancegenome.org goes through lib/net_throttle
    (`get_throttle(host, 0.2 s)`, shared with zfin_zebrafish in the same process); the seconds actually slept
    are declared in `throttle {host, min_interval_s, waited_s, available}`. A missing net_throttle is declared,
    never disguised.
  * Per-day READ cache (ADR-0080): the raw payload of each GET is stored at
    <cache_dir>/alliance_orthologs_<curie-safe>_<stringency>_<YYYYMMDD>.json and reused for the rest of
    the day (`cache_hit`, `cached_at`, `cache_path` DECLARED). cache_dir = WITT_MCP_CACHE_DIR or
    <repo>/mcp_cache (git-ignored). `use_cache=False` bypasses read+write (tests / forced refresh).
  * Every cap is declared: `limit_sent` (the `limit=` asked of the API, default ORTHOLOGS_API_LIMIT=200),
    `n_total_api` (the `total` the API declared, None when absent), `orthologs_capped` (total > returned or
    returned >= limit), `n_returned`, `n_http_gets`, `elapsed_s`, `query_sent` (the literal URL).
  * §6 no-hang: `timeout` bounds EACH GET (resolve + orthologs); the caller passes its remaining budget.

REAL SCHEMA OBSERVED 2026-09-15 (fixture rag_index/query_service/fixtures/alliance_orthologs_wt1a_20260915.json,
GET .../gene/ZFIN:ZDB-GENE-980526-558/orthologs?filter.stringency=stringent&limit=200 -> total=4, returnedRecords=4):
  payload = {total, returnedRecords, requestDate, results: [{
      category: 'gene_to_gene_orthology', searchable, stringencyFilter: 'stringent',
      geneAnnotations: [{geneIdentifier, hasDiseaseAnnotations, hasExpressionAnnotations}], geneAnnotationsMap: {...},
      geneToGeneOrthologyGenerated: {
          subjectGene: {primaryExternalId: 'ZFIN:ZDB-GENE-980526-558', taxon: {curie, name, species:{...}}, geneSymbol: {displayText}},
          objectGene:  {primaryExternalId: 'HGNC:12796', taxon: {curie: 'NCBITaxon:9606', name: 'Homo sapiens'}, geneSymbol: {displayText: 'WT1'}},
          isBestScore: {name: 'Yes'|'No'}, isBestScoreReverse: {name}, confidence: {name: 'high'|...},
          strictFilter: bool, moderateFilter: bool,
          predictionMethodsMatched: [{name}], predictionMethodsNotCalled: [{name}], predictionMethodsNotMatched?: [{name}]}}]}
  NOTE: there is NO flat `homologGene`/`best`/`methodCount` (the shape a pre-2026 UI used); the parser reads
  `geneToGeneOrthologyGenerated` and declares `schema_observed` (top-level keys of the first row) so a future
  drift is visible in the ledger instead of surfacing as an empty 'no-match'.
Offline gate: rag_index/query_service/smoke_tools_a.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIB_PARENT = str(_ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)
try:
    from lib import net_throttle  # noqa: E402
    _THROTTLE_IMPORT_ERROR = None
except Exception as _e:  # declared in the output, never disguised
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

_BASE = "https://www.alliancegenome.org/api"
_HOST = "www.alliancegenome.org"
MIN_INTERVAL_S = 0.2                       # ADR-0080 corrector: pacing shared with zfin_zebrafish (same host)
_UA = {"User-Agent": "witt-organo/1.0 (alliance-orthologs-tool)", "Accept": "application/json"}

ORTHOLOGS_API_LIMIT = 200      # `?limit=` sent to the API; more than that is NOT fetched (declared)
DEFAULT_TIMEOUT_S = 30         # urllib socket timeout per GET when the caller passes none
DEFAULT_STRINGENCY = "stringent"
STRINGENCIES = ("stringent", "moderate", "all")
IDENTIFIER_PROVENANCE = "alliance-api-payload"
TOOL_NAME = "alliance_orthologs"


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module (the offline smoke monkeypatches it to serve fixtures)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def resolve_cache_dir(cache_dir=None):
    """ADR-0080: WITT_MCP_CACHE_DIR (env, default declared) > <repo>/mcp_cache; `cache_dir` wins for tests."""
    if cache_dir is not None:
        return Path(cache_dir)
    raw = os.environ.get("WITT_MCP_CACHE_DIR", "").strip()
    return Path(raw) if raw else _ROOT / "mcp_cache"


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))


def _cache_path(cache_dir, key):
    return Path(cache_dir) / f"{TOOL_NAME}_{_safe(key)}_{_today()}.json"


def _cached_get(url, key, timeout, use_cache, cache_dir, counters):
    """GET through the per-day read cache. Returns the parsed payload; updates `counters`
    (n_http_gets, cache_hit, cached_at, cache_path). A cache file that cannot be parsed is IGNORED
    (declared as a miss) — never a silent None."""
    path = _cache_path(cache_dir, key)
    counters["cache_path"] = str(path)
    if use_cache and path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                env = json.load(f)
            counters["cache_hit"] = True
            counters["cached_at"] = env.get("cached_at")
            return env.get("payload")
        except Exception:
            pass
    if net_throttle is not None:   # a cache hit never waits; a real GET is paced per host
        counters["throttle_waited_s"] = round(counters.get("throttle_waited_s", 0.0)
                                              + net_throttle.get_throttle(_HOST, MIN_INTERVAL_S).wait(), 3)
    payload = _get(url, timeout=timeout)
    counters["n_http_gets"] += 1
    counters["cache_hit"] = False
    counters["cached_at"] = None
    if use_cache:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"tool": TOOL_NAME, "url": url, "cached_at": _now_iso(), "payload": payload},
                          f, ensure_ascii=False)
        except Exception:
            pass   # a cache write failure never fails the source (§6)
    return payload


def _resolve_curie(symbol, timeout, use_cache, cache_dir, counters):
    """Zebrafish gene SYMBOL -> ZFIN curie (ZFIN:ZDB-GENE-...), live (same resolver as zfin_zebrafish).
    Exact symbol match preferred; else the first gene hit; None when nothing resolves."""
    url = f"{_BASE}/search_autocomplete?q={urllib.parse.quote(symbol)}"
    j = _cached_get(url, f"resolve_{symbol}", timeout, use_cache, cache_dir, counters) or {}
    genes = [r for r in j.get("results", []) if r.get("category") == "gene_search_result"]
    for r in genes:
        if str(r.get("name", "")).lower() == symbol.lower():
            return r.get("curie")
    return genes[0].get("curie") if genes else None


def orthologs_url(curie, stringency=DEFAULT_STRINGENCY, limit=ORTHOLOGS_API_LIMIT):
    return f"{_BASE}/gene/{curie}/orthologs?filter.stringency={urllib.parse.quote(stringency)}&limit={int(limit)}"


def _name(x):
    """Alliance wraps enumerations as {name: 'Yes'} and symbols as {displayText: 'WT1'}; unwrap either."""
    if isinstance(x, dict):
        return x.get("name", x.get("displayText"))
    return x


def parse_orthologs(payload, curie):
    """One normalized row per API result, read from `geneToGeneOrthologyGenerated` (schema observed
    2026-09-15). Defensive: a row missing the block yields None fields + `schema_observed` exposes the drift;
    it never raises and never invents an identifier."""
    rows = []
    for r in payload.get("results") or []:
        g = r.get("geneToGeneOrthologyGenerated") or {}
        og = g.get("objectGene") or {}
        taxon = og.get("taxon") or {}
        matched = [_name(m) for m in (g.get("predictionMethodsMatched") or [])]
        not_matched = [_name(m) for m in (g.get("predictionMethodsNotMatched") or [])]
        not_called = [_name(m) for m in (g.get("predictionMethodsNotCalled") or [])]
        hid = og.get("primaryExternalId")
        rows.append({
            "species": taxon.get("name"),
            "taxon_id": taxon.get("curie"),
            "symbol": _name(og.get("geneSymbol")),
            "id": hid,
            "stringency": r.get("stringencyFilter"),
            "strict_filter": g.get("strictFilter"),
            "moderate_filter": g.get("moderateFilter"),
            "best": _name(g.get("isBestScore")),
            "best_reverse": _name(g.get("isBestScoreReverse")),
            "confidence": _name(g.get("confidence")),
            "methods_matched": matched,
            "methods_matched_n": len(matched),
            "methods_not_matched_n": len(not_matched),
            "methods_not_called_n": len(not_called),
            "evidence_id": f"alliance-ortholog:{curie}->{hid}" if hid else None,
            "url": f"https://www.alliancegenome.org/gene/{hid}" if hid else None,
            "identifier_provenance": IDENTIFIER_PROVENANCE,
        })
    return rows


def query_orthologs(symbol=None, curie=None, stringency=DEFAULT_STRINGENCY, limit=ORTHOLOGS_API_LIMIT,
                    timeout=DEFAULT_TIMEOUT_S, use_cache=True, cache_dir=None, target_taxa=None):
    """Core logic (stdlib-only, importable for standalone testing) — ADR-0080.

    Args:
      symbol       — zebrafish gene symbol (resolved LIVE to its ZFIN curie unless `curie` is given).
      curie        — ZFIN curie (skips the resolve GET).
      stringency   — 'stringent' (default) | 'moderate' | 'all' -> `filter.stringency=`.
      limit        — `limit=` asked of the API (default ORTHOLOGS_API_LIMIT=200); the cut is DECLARED.
      timeout      — socket timeout per GET; <= 0 -> status 'skipped-budget' WITHOUT touching the network.
      use_cache    — per-day read cache under cache_dir (default True).
      cache_dir    — override of WITT_MCP_CACHE_DIR / <repo>/mcp_cache (tests).
      target_taxa  — optional iterable of taxon curies (e.g. {'NCBITaxon:9606'}) to keep; the rest are
                     counted in `n_filtered_out` (declared), never silently dropped.

    Returns {status, query_sent, elapsed_s, n_http_gets, cache_hit, cached_at, cache_path, data|error}
      status ∈ 'success' | 'no-match' | 'error' | 'skipped-budget'
      data = {symbol, zfin_curie, taxon, stringency_sent, limit_sent, n_total_api, n_returned,
              orthologs_capped, n_filtered_out, target_taxa, identifier_provenance, schema_observed,
              orthologs: [rows]}.
    """
    t0 = time.monotonic()
    counters = {"n_http_gets": 0, "cache_hit": None, "cached_at": None, "cache_path": None, "throttle_waited_s": 0.0}
    out = {"query_sent": None, "n_http_gets": 0, "cache_hit": None, "cached_at": None, "cache_path": None}

    def _finish(status, **extra):
        out.update({k: v for k, v in counters.items() if k != "throttle_waited_s"})
        out["throttle"] = {"host": _HOST, "min_interval_s": MIN_INTERVAL_S, "available": net_throttle is not None,
                           "waited_s": counters.get("throttle_waited_s", 0.0),
                           **({"import_error": _THROTTLE_IMPORT_ERROR} if net_throttle is None else {})}
        out["elapsed_s"] = round(time.monotonic() - t0, 3)
        out["status"] = status
        out.update(extra)
        return out

    if timeout is not None and timeout <= 0:
        return _finish("skipped-budget",
                       error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    if stringency not in STRINGENCIES:
        return _finish("error", error=f"ValueError: stringency {stringency!r} not in {STRINGENCIES}")
    if not symbol and not curie:
        return _finish("error", error="ValueError: symbol or curie required")
    cdir = resolve_cache_dir(cache_dir)
    try:
        if not curie:
            curie = _resolve_curie(symbol, timeout, use_cache, cdir, counters)
            if not curie:
                # ADR-0080 corrector: the API ANSWERED and no zebrafish gene carries this symbol — a measurement
                # ('no-match', reason declared), not a transport failure; the curie is never invented
                return _finish("no-match", no_match_reason="symbol-unresolved",
                               data={"symbol": symbol, "zfin_curie": None, "taxon": "NCBITaxon:7955",
                                     "stringency_sent": stringency, "limit_sent": int(limit),
                                     "n_total_api": None, "n_returned": 0, "orthologs_capped": False,
                                     "n_filtered_out": 0, "target_taxa": sorted(set(target_taxa)) if target_taxa else None,
                                     "identifier_provenance": IDENTIFIER_PROVENANCE, "schema_observed": None,
                                     "orthologs": []})
        url = orthologs_url(curie, stringency, limit)
        out["query_sent"] = url
        payload = _cached_get(url, f"{curie}_{stringency}", timeout, use_cache, cdir, counters) or {}
        rows = parse_orthologs(payload, curie)
        n_returned = len(rows)
        total = payload.get("total")
        keep = set(target_taxa) if target_taxa else None
        n_filtered = 0
        if keep is not None:
            kept = [r for r in rows if r.get("taxon_id") in keep]
            n_filtered = len(rows) - len(kept)
            rows = kept
        first = (payload.get("results") or [{}])[0]
        data = {
            "symbol": symbol, "zfin_curie": curie, "taxon": "NCBITaxon:7955",
            "stringency_sent": stringency, "limit_sent": int(limit),
            "n_total_api": total, "n_returned": n_returned,
            "orthologs_capped": bool((isinstance(total, int) and total > n_returned) or n_returned >= int(limit)),
            "n_filtered_out": n_filtered, "target_taxa": sorted(keep) if keep else None,
            "identifier_provenance": IDENTIFIER_PROVENANCE,
            "schema_observed": sorted(first.keys()) if isinstance(first, dict) else None,
            "orthologs": rows,
        }
        return _finish("success" if rows else "no-match", data=data)
    except Exception as e:
        return _finish("error", error=f"{type(e).__name__}: {e}")


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class Alliance_orthologs:
    name = "Alliance_orthologs"
    description = (
        "Orthologs of a zebrafish (Danio rerio) gene from the Alliance of Genome Resources (DIOPT-based "
        "table, ZFIN provider). Resolves a symbol to its ZFIN curie and returns {species, symbol, id, "
        "stringency, best} per ortholog. Use to bridge zebrafish genes to human/mouse identifiers before "
        "querying human-centric sources; anything derived that way is 'inferred-by-orthology' (ADR-0080)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": ["string", "null"], "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "curie": {"type": ["string", "null"], "description": "ZFIN curie, e.g. 'ZFIN:ZDB-GENE-980526-558' (skips resolve)."},
            "stringency": {"type": ["string", "null"], "description": "'stringent' (default) | 'moderate' | 'all'."},
            "limit": {"type": ["integer", "null"], "description": "limit= sent to the API (default 200; cut declared)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds per HTTP GET (default 30)."},
        },
    }

    def run(self, symbol=None, curie=None, stringency=None, limit=None, timeout=None):
        return query_orthologs(symbol, curie, stringency or DEFAULT_STRINGENCY,
                               ORTHOLOGS_API_LIMIT if limit is None else limit,
                               DEFAULT_TIMEOUT_S if timeout is None else timeout)


def _record_fixture(out_path, curie="ZFIN:ZDB-GENE-980526-558", symbol="wt1a"):
    """ONE real GET (ADR-0080 rule) to freeze the live payload as an offline fixture. Uses the curie
    directly so the resolve GET is not spent (the resolver is the one zfin_zebrafish already proved)."""
    url = orthologs_url(curie, DEFAULT_STRINGENCY, ORTHOLOGS_API_LIMIT)
    t0 = time.monotonic()
    payload = _get(url, timeout=60)
    env = {"tool": TOOL_NAME, "recorded_at": _now_iso(), "url": url, "symbol": symbol, "curie": curie,
           "elapsed_s": round(time.monotonic() - t0, 3), "payload": payload}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=1)
    return env


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) >= 3 and sys.argv[1] == "--record-fixture":
        env = _record_fixture(sys.argv[2])
        p = env["payload"]
        print(f"recorded {sys.argv[2]}: total={p.get('total')} returned={len(p.get('results') or [])} "
              f"top_keys={sorted(p.keys())}")
        if p.get("results"):
            print("first-row keys:", sorted(p["results"][0].keys()))
            print(json.dumps(p["results"][0], ensure_ascii=False)[:1500])
    else:
        r = query_orthologs(symbol="wt1a", timeout=30)
        print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
        for o in (r.get("data") or {}).get("orthologs", [])[:10]:
            print(f"  {o['species']}  {o['symbol']}  {o['id']}  {o['stringency']}  best={o['best']}")
