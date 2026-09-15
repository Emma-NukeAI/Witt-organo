"""
Ensembl_homology — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 rebanada C3).

WHY THIS TOOL EXISTS (ADR-0080, harness Layer 0 lote A):
A second, independent orthology bridge (Ensembl Compara) next to alliance_orthologs: two sources that
disagree are a finding; one source alone is a single point of silence. Ensembl REST is keyless and
read-only; its answers carry stable Ensembl IDs (ENSDARG..., ENSG...) plus %identity of the alignment.

WHAT IT DOES:
  GET https://rest.ensembl.org/homology/symbol/{species}/{symbol}?target_species={target};content-type=application/json
  (default species=danio_rerio, target=homo_sapiens; the ';' separator is the one Ensembl documents).
Returns one row per homology {type ('ortholog_one2one'|'ortholog_one2many'|...), source_id, source_species,
target_id, target_species, target_protein_id, target_perc_id, source_perc_id, taxonomy_level,
method_link_type, evidence_id, url}. `identifier_provenance: 'ensembl-api-payload'`.

DOCTRINE (ADR-0078/0079/0080):
  * THREE states: 'success' (>=1 homology), 'no-match' (HTTP 400 "No valid lookup found for symbol ..." —
    Ensembl's way of saying the symbol does not exist for that species — OR a 200 with zero homologies; the
    reason is declared in `no_match_reason`), 'error' (any other failure). 'skipped-budget' when timeout<=0
    BEFORE any GET.
  * Rate limit RESPECTED, MEASURED, never assumed: Ensembl answers X-RateLimit-Limit / -Remaining / -Reset /
    -Period; whatever the response carried is declared verbatim in `rate_limit_headers` (None when absent).
    On HTTP 429 the tool honours `Retry-After` ONCE (net_throttle.retry_once_on_429, capped at 60 s) and a
    second 429 is a declared 'error' — never a loop. `retries_429` counts what happened.
  * Pacing between calls from this process: net_throttle.get_throttle('rest.ensembl.org', 0.07 s) — Ensembl's
    documented ceiling is 15 req/s; the interval is env-tunable (WITT_ENSEMBL_MIN_INTERVAL_S, default 0.07)
    and declared in `throttle`. When lib/net_throttle is not importable the call still goes out, and the
    absence is DECLARED (`throttle.available: false`), not disguised.
  * Per-day READ cache (ADR-0080): <cache_dir>/ensembl_homology_<species>_<symbol>_<target>_<YYYYMMDD>.json;
    cache_dir = WITT_MCP_CACHE_DIR or <repo>/mcp_cache. `cache_hit`, `cached_at`, `cache_path` declared.
  * Declared measurements: `query_sent` (literal URL), `elapsed_s`, `n_http_gets`, `http_status`.

REAL SCHEMA OBSERVED 2026-09-15 (fixture rag_index/query_service/fixtures/ensembl_homology_wt1a_20260915.json,
GET .../homology/symbol/danio_rerio/wt1a?target_species=homo_sapiens;content-type=application/json -> HTTP 200,
X-RateLimit-Limit: 55000, X-RateLimit-Period: 3600, X-RateLimit-Remaining: 54999, X-RateLimit-Reset: 1151):
  payload = {data: [{id: 'ENSDARG00000031420', homologies: [{type: 'ortholog_one2one', taxonomy_level: 'Euteleostomi',
             method_link_type: 'ENSEMBL_ORTHOLOGUES', dn_ds: null,
             source: {id: 'ENSDARG00000031420', species: 'danio_rerio', taxon_id: 7955, protein_id: 'ENSDARP00000029174',
                      perc_id: 76.13, perc_pos: 83.77, cigar_line, align_seq},
             target: {id: 'ENSG00000184937', species: 'homo_sapiens', taxon_id: 9606, protein_id: 'ENSP00000415516',
                      perc_id: 61.11, perc_pos: 67.24, cigar_line, align_seq}}]}]}
  The parser drops `align_seq`/`cigar_line` (bulk alignment strings, also replaced by a marker in the fixture — cut
  declared in the fixture's `cut`) and declares `schema_observed` (keys of the first homology).
Offline gate: rag_index/query_service/smoke_tools_a.py
"""
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

_BASE = "https://rest.ensembl.org"
_HOST = "rest.ensembl.org"
_UA = {"User-Agent": "witt-organo/1.0 (ensembl-homology-tool)", "Accept": "application/json"}
_RATE_HEADER_PREFIX = "x-ratelimit"

DEFAULT_TIMEOUT_S = 30
DEFAULT_SPECIES = "danio_rerio"
DEFAULT_TARGET = "homo_sapiens"
DEFAULT_MIN_INTERVAL_S = 0.07          # ADR-0080: Ensembl documents 15 req/s; WITT_ENSEMBL_MIN_INTERVAL_S overrides
IDENTIFIER_PROVENANCE = "ensembl-api-payload"
TOOL_NAME = "ensembl_homology"
NO_MATCH_400_PATTERN = re.compile(r"no valid lookup|not found|could not find", re.I)


def _rate_headers(hdrs):
    if hdrs is None:
        return None
    try:
        found = {k: v for k, v in hdrs.items() if str(k).lower().startswith(_RATE_HEADER_PREFIX)}
    except Exception:
        found = {}
    return found or None


def _get_with_headers(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module (the smoke monkeypatches it). Returns
    (parsed_json, http_status, rate_limit_headers_or_None). HTTPError propagates to the caller, which reads
    the error body + headers (a 429's Retry-After and X-RateLimit-* live on the ERROR response)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        return json.loads(body), getattr(r, "status", 200), _rate_headers(getattr(r, "headers", None))


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """Legacy shape (json only), same seam."""
    return _get_with_headers(url, timeout)[0]


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


def resolve_min_interval_s():
    """WITT_ENSEMBL_MIN_INTERVAL_S if parseable, else DEFAULT_MIN_INTERVAL_S. Returns (seconds, source)."""
    raw = os.environ.get("WITT_ENSEMBL_MIN_INTERVAL_S", "").strip()
    if raw:
        try:
            return max(0.0, float(raw)), "env"
        except ValueError:
            pass
    return DEFAULT_MIN_INTERVAL_S, "default"


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))


def homology_url(symbol, species=DEFAULT_SPECIES, target_species=DEFAULT_TARGET):
    return (f"{_BASE}/homology/symbol/{urllib.parse.quote(species)}/{urllib.parse.quote(symbol)}"
            f"?target_species={urllib.parse.quote(target_species)};content-type=application/json")


def _read_error_body(e):
    try:
        raw = e.read().decode("utf-8", "replace")
    except Exception:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw[:500] if raw else None


def parse_homologies(payload):
    """Rows from payload.data[*].homologies[*]; alignment bulk (cigar_line/align_seq) is dropped."""
    rows = []
    for d in payload.get("data") or []:
        for h in d.get("homologies") or []:
            src, tgt = h.get("source") or {}, h.get("target") or {}
            sid, tid = src.get("id"), tgt.get("id")
            rows.append({
                "type": h.get("type"),
                "taxonomy_level": h.get("taxonomy_level"),
                "method_link_type": h.get("method_link_type"),
                "source_id": sid, "source_species": src.get("species"),
                "source_protein_id": src.get("protein_id"), "source_perc_id": src.get("perc_id"),
                "target_id": tid, "target_species": tgt.get("species"),
                "target_protein_id": tgt.get("protein_id"), "target_perc_id": tgt.get("perc_id"),
                "target_perc_pos": tgt.get("perc_pos"), "target_taxon_id": tgt.get("taxon_id"),
                "source_taxon_id": src.get("taxon_id"), "dn_ds": h.get("dn_ds"),
                "evidence_id": f"ensembl-homology:{sid}->{tid}" if sid and tid else None,
                "url": f"https://www.ensembl.org/id/{tid}" if tid else None,
                "identifier_provenance": IDENTIFIER_PROVENANCE,
            })
    return rows


def query_homology(symbol, species=DEFAULT_SPECIES, target_species=DEFAULT_TARGET, timeout=DEFAULT_TIMEOUT_S,
                   use_cache=True, cache_dir=None):
    """Core logic (stdlib-only, importable for standalone testing) — ADR-0080.

    Returns {status, query_sent, elapsed_s, n_http_gets, http_status, cache_hit, cached_at, cache_path,
             rate_limit_headers, retries_429, throttle, data|error, no_match_reason?}
      status ∈ 'success' | 'no-match' | 'error' | 'skipped-budget'
      data = {symbol, species, target_species, source_gene_id, n_homologies, types: {type: n},
              identifier_provenance, schema_observed, homologies: [rows]}.
    timeout <= 0 -> 'skipped-budget' with zero network calls (§6 no-hang).
    """
    t0 = time.monotonic()
    min_interval_s, interval_src = resolve_min_interval_s()
    out = {"query_sent": None, "n_http_gets": 0, "http_status": None, "cache_hit": None, "cached_at": None,
           "cache_path": None, "rate_limit_headers": None, "retries_429": 0,
           "throttle": {"host": _HOST, "min_interval_s": min_interval_s, "min_interval_source": interval_src,
                        "available": net_throttle is not None, "waited_s": 0.0,
                        "import_error": _THROTTLE_IMPORT_ERROR}}

    def _finish(status, **extra):
        out["elapsed_s"] = round(time.monotonic() - t0, 3)
        out["status"] = status
        out.update(extra)
        return out

    if timeout is not None and timeout <= 0:
        return _finish("skipped-budget",
                       error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    sym = (symbol or "").strip()
    if not sym:
        return _finish("error", error="ValueError: empty symbol")
    url = homology_url(sym, species, target_species)
    out["query_sent"] = url
    cdir = resolve_cache_dir(cache_dir)
    path = cdir / f"{TOOL_NAME}_{_safe(species)}_{_safe(sym)}_{_safe(target_species)}_{_today()}.json"
    out["cache_path"] = str(path)

    payload = None
    if use_cache and path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                env = json.load(f)
            payload = env.get("payload")
            out["cache_hit"], out["cached_at"] = True, env.get("cached_at")
            out["http_status"] = env.get("http_status")
            out["rate_limit_headers"] = env.get("rate_limit_headers")
        except Exception:
            payload = None
    if payload is None:
        out["cache_hit"] = False
        stats = {}

        def _call():
            if net_throttle is not None:
                out["throttle"]["waited_s"] += net_throttle.get_throttle(_HOST, min_interval_s).wait()
            out["n_http_gets"] += 1
            return _get_with_headers(url, timeout=timeout)

        try:
            if net_throttle is not None and hasattr(net_throttle, "retry_once_on_429"):
                payload, status, rl = net_throttle.retry_once_on_429(_call, stats)
                out["retries_429"] = int(stats.get("retries_429", 0) or 0)
                out["retry_after_s"], out["retry_after_src"] = stats.get("retry_after_s"), stats.get("retry_after_src")
            else:
                payload, status, rl = _call()
            out["http_status"], out["rate_limit_headers"] = status, rl
        except urllib.error.HTTPError as e:
            out["retries_429"] = int(stats.get("retries_429", 0) or 0)
            out["retry_after_s"], out["retry_after_src"] = stats.get("retry_after_s"), stats.get("retry_after_src")
            out["http_status"] = e.code
            out["rate_limit_headers"] = _rate_headers(getattr(e, "headers", None))
            body = _read_error_body(e)
            msg = body.get("error") if isinstance(body, dict) else (body or "")
            if e.code == 400 and NO_MATCH_400_PATTERN.search(str(msg or "")):
                return _finish("no-match", no_match_reason="ensembl-400-no-valid-lookup", error_body=msg,
                               data={"symbol": sym, "species": species, "target_species": target_species,
                                     "source_gene_id": None, "n_homologies": 0, "types": {},
                                     "identifier_provenance": IDENTIFIER_PROVENANCE, "schema_observed": None,
                                     "homologies": []})
            return _finish("error", error=f"HTTPError: {e.code} {e.reason}", error_body=msg)
        except Exception as e:
            out["retries_429"] = int(stats.get("retries_429", 0) or 0)
            return _finish("error", error=f"{type(e).__name__}: {e}")
        if use_cache:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"tool": TOOL_NAME, "url": url, "cached_at": _now_iso(), "http_status": out["http_status"],
                               "rate_limit_headers": out["rate_limit_headers"], "payload": payload},
                              f, ensure_ascii=False)
            except Exception:
                pass   # a cache write failure never fails the source (§6)

    try:
        rows = parse_homologies(payload or {})
    except Exception as e:
        return _finish("error", error=f"ParseError: {type(e).__name__}: {e}")
    data0 = ((payload or {}).get("data") or [{}])[0]
    types = {}
    for r in rows:
        types[r["type"]] = types.get(r["type"], 0) + 1
    first_h = ((data0.get("homologies") or [{}])[0]) if isinstance(data0, dict) else {}
    data = {"symbol": sym, "species": species, "target_species": target_species,
            "source_gene_id": data0.get("id") if isinstance(data0, dict) else None,
            "n_homologies": len(rows), "types": types,
            "identifier_provenance": IDENTIFIER_PROVENANCE,
            "schema_observed": sorted(first_h.keys()) if isinstance(first_h, dict) and first_h else None,
            "homologies": rows}
    if not rows:
        return _finish("no-match", no_match_reason="zero-homologies-in-payload", data=data)
    return _finish("success", data=data)


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class Ensembl_homology:
    name = "Ensembl_homology"
    description = (
        "Ensembl Compara homologies for a zebrafish (danio_rerio) gene symbol against a target species "
        "(default homo_sapiens): type (one2one/one2many), Ensembl gene/protein IDs and % identity. "
        "Keyless REST; rate-limit headers are measured and declared. Evidence derived through this bridge "
        "is 'inferred-by-orthology' (ADR-0080)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "species": {"type": ["string", "null"], "description": "Source species (default danio_rerio)."},
            "target_species": {"type": ["string", "null"], "description": "Target species (default homo_sapiens)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds (default 30)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, species=None, target_species=None, timeout=None):
        return query_homology(symbol, species or DEFAULT_SPECIES, target_species or DEFAULT_TARGET,
                              DEFAULT_TIMEOUT_S if timeout is None else timeout)


def _record_fixture(out_path, symbol="wt1a"):
    """ONE real GET (ADR-0080 rule) to freeze the live payload + measured rate-limit headers as a fixture."""
    url = homology_url(symbol)
    t0 = time.monotonic()
    payload, status, rl = _get_with_headers(url, timeout=60)
    # drop alignment bulk from the fixture (declared): the parser never reads it
    n_dropped = 0
    for d in payload.get("data") or []:
        for h in d.get("homologies") or []:
            for side in ("source", "target"):
                for k in ("align_seq", "cigar_line"):
                    if isinstance(h.get(side), dict) and k in h[side]:
                        h[side][k] = f"<dropped-from-fixture:{k}>"
                        n_dropped += 1
    env = {"tool": TOOL_NAME, "recorded_at": _now_iso(), "url": url, "symbol": symbol, "http_status": status,
           "rate_limit_headers": rl, "elapsed_s": round(time.monotonic() - t0, 3),
           "cut": {"alignment_fields_dropped": n_dropped, "fields": ["align_seq", "cigar_line"]},
           "payload": payload}
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
        print(f"recorded {sys.argv[2]}: http={env['http_status']} rate_limit={env['rate_limit_headers']} "
              f"top_keys={sorted(p.keys())} n_data={len(p.get('data') or [])}")
        for d in p.get("data") or []:
            print("data.id=", d.get("id"), "n_homologies=", len(d.get("homologies") or []))
            if d.get("homologies"):
                h = d["homologies"][0]
                print("homology keys:", sorted(h.keys()))
                print("target keys:", sorted((h.get("target") or {}).keys()))
                print(json.dumps(h, ensure_ascii=False)[:1200])
    else:
        r = query_homology("wt1a")
        print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
        for h in (r.get("data") or {}).get("homologies", []):
            print(f"  {h['type']}  {h['source_id']} -> {h['target_id']} ({h['target_species']}) perc_id={h['target_perc_id']}")
