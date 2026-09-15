"""
Reactome_zebrafish_pathways — Layer 0 workspace tool (ADR-0080, harness lote B, added 2026-09-15).

WHY THIS TOOL EXISTS (ADR-0080 §4 harness de busqueda):
Reactome is the pathway tier the harness lacked. Its Danio rerio pathways (R-DRE-*) are NOT curated on
zebrafish: Reactome projects the human curation onto other species by orthology (electronic inference).
That is exactly the class of evidence the doctrine forces us to LABEL: every pathway item this tool
returns carries label 'inferred-by-orthology' — the synthesizer may cite it as a hypothesis anchor, never
as a zebrafish measurement.

WHAT IT DOES:
ONE GET to https://reactome.org/ContentService/search/query?query=<sym>&species=Danio%20rerio
&types=Pathway. Public, keyless, JSON, read-only.

MEASURED LIVE 2026-09-15 (wt1a) — what the measurement changed in this parser:
  * The `types=Pathway` filter was NOT honored: the API answered numberOfMatches=1 with ONE entry of
    type 'Protein' (exactType 'ReferenceGeneProduct', stId R-DRE-452420, referenceIdentifier Q9PUT7) and
    ZERO pathways. A parser that trusted the filter would have presented a protein record as a pathway.
    This parser classifies every entry by its own `type`/`exactType`: only entries typed 'Pathway'
    become pathway items; every other entry is COUNTED and listed in `non_pathway_entries` (id, type,
    referenceIdentifier), and `types_filter_honored` declares whether the server respected the filter.
  * With zero pathways the status is 'no-match' even when a protein entry exists ("Reactome knows the
    protein but lists no zebrafish pathway under this query") — the protein hit is declared in
    `entity_hits`, which a future tool may use for /data/pathways/low/entity/<dbId> (NOT done here:
    one GET per call, declared).
  * `name` arrives with Reactome's <span class="highlighting"> markup; the tags are stripped (declared
    `name_markup_stripped: True`), the text itself is verbatim.

ADR-0080 doctrine (same skeleton as zfin_zebrafish.py): `_get(url, timeout)` sole network seam; three
states 'success' | 'no-match' | 'error'; per-day read cache mcp_cache/reactome_<slug>_<YYYYMMDD>.json
(`cache_hit`, `cache_ref`); `timeout` propagated, timeout<=0 -> BudgetExhausted without network;
identifier_provenance 'reactome-content-service:search'; evidence_kind 'pathway'.

Fixture: rag_index/query_service/fixtures/reactome_wt1a_20260915.json
Offline gate: rag_index/query_service/smoke_tools_b.py
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://reactome.org/ContentService/search/query"
_HOST = "reactome.org"
_UA = {"User-Agent": "witt-organo/1.0 (reactome-tool)", "Accept": "application/json"}

TOOL_FAMILY = "reactome"
EVIDENCE_KIND = "pathway"
LABEL = "inferred-by-orthology"    # ADR-0080: R-DRE pathways are electronically inferred from human
LABEL_NOTE = ("Reactome Danio rerio pathways are computationally projected from the human curation by "
              "orthology; not a zebrafish measurement")
IDENTIFIER_PROVENANCE = "reactome-content-service:search"
SPECIES = "Danio rerio"
TYPES_REQUESTED = "Pathway"
DEFAULT_TIMEOUT_S = 30
_TAG_RE = re.compile(r"<[^>]+>")

_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "mcp_cache"


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module. Returns (payload_json, headers_lower)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
        headers = {k.lower(): v for k, v in r.headers.items()}
    return payload, headers


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "query"


def _cache_path(symbol):
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    return CACHE_DIR / f"{TOOL_FAMILY}_{_slug(symbol)}_{date}.json"


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


def build_url(symbol):
    return (f"{_BASE}?query={urllib.parse.quote(symbol)}&species={urllib.parse.quote(SPECIES)}"
            f"&types={TYPES_REQUESTED}")


def strip_markup(name):
    """Reactome highlights the hit with <span class="highlighting">…</span>; the text stays verbatim."""
    return _TAG_RE.sub("", name or "").strip()


def _entries(payload):
    """Flatten results[].entries[] (Reactome groups entries by typeName)."""
    out = []
    for grp in payload.get("results") or []:
        for e in grp.get("entries") or []:
            out.append(e)
    return out


def parse_pathway(e):
    st = e.get("stId") or e.get("id")
    name = strip_markup(e.get("name"))
    return {
        "evidence_id": f"reactome:{st}" if st else None,
        "kind": EVIDENCE_KIND,
        "source_family": TOOL_FAMILY,
        "label": LABEL,
        "label_note": LABEL_NOTE,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
        "st_id": st,
        "db_id": e.get("dbId"),
        "name": name,
        "statement": name or None,
        "text": strip_markup(e.get("summation")) or None,
        "type": e.get("type"),
        "exact_type": e.get("exactType"),
        "species": e.get("species"),
        "is_disease": e.get("isDisease"),
        "name_markup_stripped": True,
        "url": f"https://reactome.org/content/detail/{st}" if st else None,
    }


def query_reactome(symbol, timeout=DEFAULT_TIMEOUT_S, use_cache=True):
    """Core logic (stdlib-only) — ADR-0080.

    Returns {status, query_sent, elapsed_s, cache_hit, cache_ref, n_http_gets, evidence_kind, label,
             data|error}
      status 'success'  — >=1 entry typed 'Pathway'
             'no-match' — the search ran, zero pathway entries (a Protein/other hit may still be declared)
             'error'    — the lookup failed; BudgetExhausted when timeout<=0 (no request sent)
      data = {symbol, species, types_requested, types_filter_honored, n_matches_declared_by_api,
              n_entries, n_pathways, n_non_pathway_entries, non_pathway_entries[], entity_hits[],
              cache_error, items[]}
    """
    t0 = time.monotonic()
    sym = (symbol or "").strip()
    url = build_url(sym) if sym else None
    base = {"query_sent": url, "cache_hit": False, "cache_ref": None, "n_http_gets": 0,
            "evidence_kind": EVIDENCE_KIND, "label": LABEL}

    def _done(**kw):
        return dict(base, elapsed_s=round(time.monotonic() - t0, 3), **kw)

    if not sym:
        return _done(status="error", error="empty symbol")
    if timeout is not None and timeout <= 0:
        return _done(status="error",
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    try:
        path = _cache_path(sym)
        cached = _cache_read(path) if use_cache else None
        cache_error = None
        if cached is not None:
            payload, headers = cached
            base["cache_hit"] = True
        else:
            payload, headers = _get(url, timeout=timeout)
            base["n_http_gets"] = 1
            if use_cache:
                cache_error = _cache_write(path, url, payload, headers)
        if use_cache and cache_error is None and path.exists():
            try:
                base["cache_ref"] = str(path.relative_to(_ROOT))
            except ValueError:
                base["cache_ref"] = str(path)

        entries = _entries(payload)
        items, others = [], []
        for e in entries:
            if str(e.get("type") or "").lower() == "pathway" or str(e.get("exactType") or "").lower() == "pathway":
                items.append(parse_pathway(e))
            else:
                others.append({"id": e.get("stId") or e.get("id"), "db_id": e.get("dbId"),
                               "type": e.get("type"), "exact_type": e.get("exactType"),
                               "name": strip_markup(e.get("name")),
                               "reference_identifier": e.get("referenceIdentifier"),
                               "reference_database": e.get("databaseName")})
        n_matches = payload.get("numberOfMatches")
        data = {
            "symbol": sym,
            "species": SPECIES,
            "types_requested": TYPES_REQUESTED,
            # measured 2026-09-15: False on wt1a (a Protein entry came back under types=Pathway)
            "types_filter_honored": (len(others) == 0) if entries else None,
            "n_matches_declared_by_api": n_matches if isinstance(n_matches, int) else None,
            "n_entries": len(entries),
            "n_pathways": len(items),
            "n_non_pathway_entries": len(others),
            "non_pathway_entries": others,
            "entity_hits": [o for o in others if o["reference_identifier"]],
            "one_get_per_call": True,   # pathways-by-entity (/data/pathways/low/entity) NOT fetched here
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
class Reactome_zebrafish_pathways:
    name = "Reactome_zebrafish_pathways"
    description = (
        "Reactome pathways for a zebrafish (Danio rerio) gene symbol via the public ContentService search "
        "(types=Pathway). Every pathway item is labeled 'inferred-by-orthology' — Reactome projects human "
        "curation onto zebrafish (ADR-0080). Entries of other types the server returns anyway (measured: a "
        "Protein record under types=Pathway) are declared in non_pathway_entries, never presented as pathways. "
        "No API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 30)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, timeout=DEFAULT_TIMEOUT_S):
        return query_reactome(symbol, timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = query_reactome(sys.argv[1] if len(sys.argv) > 1 else "wt1a")
    print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
    d = r.get("data") or {}
    print(f"pathways={d.get('n_pathways')} non_pathway={d.get('n_non_pathway_entries')} honored={d.get('types_filter_honored')}")
    for it in d.get("items", []):
        print(f"  - {it['st_id']} {it['name']} [{it['label']}]")
