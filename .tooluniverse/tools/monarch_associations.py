"""
Monarch_gene_phenotype_associations — Layer 0 workspace tool (ADR-0080, harness lote B, added 2026-09-15).

WHY THIS TOOL EXISTS (ADR-0080 §4 harness de busqueda):
Monarch Initiative v3 serves the SAME ZFIN gene->phenotype assertions the zfin_zebrafish tool reads
through the Alliance, but keyed by ZP (Zebrafish Phenotype ontology) terms with ontology closures and an
explicit knowledge level / primary knowledge source per association. It is a second, independent index
of the phenotype tier — useful when the Alliance is down (§6: a failing source leaves an 'error' row and
the run continues) and for ZP-term ids the Alliance payload does not carry.

WHAT IT DOES:
ONE GET to https://api.monarchinitiative.org/v3/api/association?subject=<curie>
&category=biolink:GeneToPhenotypicFeatureAssociation&limit=<n>. The SUBJECT MUST BE A CURIE (e.g.
ZFIN:ZDB-GENE-980526-558) already resolved by the caller (zfin_zebrafish._resolve_curie or the
Alliance autocomplete): this tool does NOT resolve symbols — an input that is not a curie is returned
as status 'error' ('not-a-curie'), never guessed (identifiers only if they resolve, else gap_flag).

ADR-0080 doctrine honored here (same skeleton as zfin_zebrafish.py):
  * `_get(url, timeout)` is the ONLY network seam (offline smoke monkeypatches it to serve the fixture).
  * Three states: 'success' (>=1 association), 'no-match' (the query ran, zero items), 'error'.
  * PUBLICATIONS ARE ZFIN CURIES (measured live 2026-09-15 on wt1a: 20/20 items carry only
    'ZFIN:ZDB-PUB-…' publications, zero PMIDs). They are copied verbatim and declared
    `publications_resolution: 'unresolved-zfin-curie'` per item and at result level; a PMID, when one
    ever appears, is declared 'pmid'; a mixed item is 'mixed'. Nothing here turns a ZDB-PUB id into a
    PMID — that resolution is a different tool's job and until it exists the gap is DECLARED.
  * Every cut declared: `n_total` (API `total`) vs `n_returned_by_api`, `truncated_by_limit`.
  * `subject_resolved`: True only when the API echoes the requested curie as `subject` of >=1 item
    (the identifier RESOLVED); False with zero items is a no-match on an unverified curie — declared.
  * Per-day READ cache mcp_cache/monarch_<slug>_l<limit>_<YYYYMMDD>.json (`cache_hit`, `cache_ref`).
  * `timeout` propagates; timeout <= 0 -> status 'error' BudgetExhausted without touching the network.
  * label: None (knowledge_level is copied per item, e.g. 'knowledge_assertion'); evidence_kind
    'phenotype-association'.

Fixture (live 2026-09-15, wt1a): rag_index/query_service/fixtures/monarch_wt1a_20260915.json
  total 66, 20 returned (truncated_by_limit True), primary_knowledge_source infores:zfin.
Offline gate: rag_index/query_service/smoke_tools_b.py
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://api.monarchinitiative.org/v3/api/association"
_HOST = "api.monarchinitiative.org"
_UA = {"User-Agent": "witt-organo/1.0 (monarch-tool)", "Accept": "application/json"}

TOOL_FAMILY = "monarch"
EVIDENCE_KIND = "phenotype-association"
LABEL = None
IDENTIFIER_PROVENANCE = "monarch-v3:association.subject"
CATEGORY = "biolink:GeneToPhenotypicFeatureAssociation"
DEFAULT_LIMIT = 20                # `limit=20` sent to the API; the cut is declared in truncated_by_limit
DEFAULT_TIMEOUT_S = 30
PUBS_UNRESOLVED_ZFIN = "unresolved-zfin-curie"
PUBS_PMID = "pmid"
PUBS_MIXED = "mixed"
PUBS_NONE = "none"
_CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*:\S+$")

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
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "curie"


def _cache_path(curie, limit):
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    return CACHE_DIR / f"{TOOL_FAMILY}_{_slug(curie)}_l{int(limit)}_{date}.json"


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


def build_url(curie, limit=DEFAULT_LIMIT):
    return (f"{_BASE}?subject={urllib.parse.quote(curie, safe=':')}"
            f"&category={urllib.parse.quote(CATEGORY, safe=':')}&limit={int(limit)}")


def publications_resolution(pubs):
    """ADR-0080: what KIND of publication identifiers an association carries — declared, never converted."""
    pubs = [str(p) for p in (pubs or []) if p]
    if not pubs:
        return PUBS_NONE
    kinds = set()
    for p in pubs:
        if p.startswith("PMID:"):
            kinds.add(PUBS_PMID)
        elif p.startswith("ZFIN:ZDB-PUB-"):
            kinds.add(PUBS_UNRESOLVED_ZFIN)
        else:
            kinds.add("unresolved-other")
    return next(iter(kinds)) if len(kinds) == 1 else PUBS_MIXED


def parse_item(a):
    """ONE Monarch association -> normalized item; publications copied VERBATIM with their resolution."""
    pubs = [str(p) for p in (a.get("publications") or []) if p]
    obj, label = a.get("object"), a.get("object_label")
    return {
        "evidence_id": f"monarch:{a.get('id')}" if a.get("id") else None,
        "kind": EVIDENCE_KIND,
        "source_family": TOOL_FAMILY,
        "label": LABEL,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
        "association_id": a.get("id"),
        "subject": a.get("subject"),
        "subject_label": a.get("subject_label"),
        "subject_taxon": a.get("subject_taxon"),
        "predicate": a.get("predicate"),
        "phenotype_id": obj,
        "phenotype_label": label,
        "statement": label,
        "text": None,
        "evidence_count": a.get("evidence_count"),
        "knowledge_level": a.get("knowledge_level"),
        "primary_knowledge_source": a.get("primary_knowledge_source"),
        "publications": pubs,
        "publications_resolution": publications_resolution(pubs),
        "url": f"https://monarchinitiative.org/{obj}" if obj else None,
    }


def query_monarch(curie, limit=DEFAULT_LIMIT, timeout=DEFAULT_TIMEOUT_S, use_cache=True):
    """Core logic (stdlib-only) — ADR-0080.

    Returns {status, query_sent, elapsed_s, cache_hit, cache_ref, n_http_gets, evidence_kind, label,
             data|error}
      status 'success' | 'no-match' | 'error' ('not-a-curie' when the subject is not CURIE-shaped;
             BudgetExhausted when timeout<=0 — no request sent in either case).
      data = {curie, category, subject_resolved, n_total, n_returned_by_api, truncated_by_limit,
              limit_sent, publications_resolution (result level), n_publications_total,
              publications_unique[], primary_knowledge_sources[], cache_error, items[]}
    """
    t0 = time.monotonic()
    cur = (curie or "").strip()
    url = build_url(cur, limit) if cur else None
    base = {"query_sent": url, "cache_hit": False, "cache_ref": None, "n_http_gets": 0,
            "evidence_kind": EVIDENCE_KIND, "label": LABEL}

    def _done(**kw):
        return dict(base, elapsed_s=round(time.monotonic() - t0, 3), **kw)

    if not cur or not _CURIE_RE.match(cur):
        return _done(status="error", query_sent=None,
                     error=f"not-a-curie: subject {curie!r} must be a resolved curie (e.g. ZFIN:ZDB-GENE-...); "
                           f"symbol resolution belongs to zfin_zebrafish._resolve_curie (no request sent)")
    if timeout is not None and timeout <= 0:
        return _done(status="error",
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    try:
        path = _cache_path(cur, limit)
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

        raw_items = payload.get("items") or []
        items = [parse_item(a) for a in raw_items]
        total = payload.get("total")
        pubs_all = [p for it in items for p in it["publications"]]
        resolutions = {it["publications_resolution"] for it in items if it["publications"]}
        if not resolutions:
            res_level = PUBS_NONE
        elif len(resolutions) == 1:
            res_level = next(iter(resolutions))
        else:
            res_level = PUBS_MIXED
        data = {
            "curie": cur,
            "category": CATEGORY,
            "subject_resolved": any(it["subject"] == cur for it in items),
            "n_total": total if isinstance(total, int) else None,
            "n_returned_by_api": len(raw_items),
            "truncated_by_limit": bool(isinstance(total, int) and total > len(raw_items)),
            "limit_sent": int(limit),
            "publications_resolution": res_level,
            "n_publications_total": len(pubs_all),
            "publications_unique": sorted(set(pubs_all)),
            "primary_knowledge_sources": sorted({it["primary_knowledge_source"] for it in items
                                                 if it["primary_knowledge_source"]}),
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
class Monarch_gene_phenotype_associations:
    name = "Monarch_gene_phenotype_associations"
    description = (
        "Gene-to-phenotype associations from the Monarch Initiative v3 API for an ALREADY RESOLVED gene "
        "curie (e.g. ZFIN:ZDB-GENE-980526-558): ZP phenotype terms with labels, evidence counts, knowledge "
        "level and primary knowledge source. Publications come back as ZFIN publication curies and are "
        "declared 'unresolved-zfin-curie' (ADR-0080) — never converted to PMIDs here. No API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "curie": {"type": "string", "description": "Resolved gene curie, e.g. 'ZFIN:ZDB-GENE-980526-558'."},
            "limit": {"type": ["integer", "null"], "description": "Associations requested (default 20); the cut is declared in truncated_by_limit."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 30)."},
        },
        "required": ["curie"],
    }

    def run(self, curie, limit=DEFAULT_LIMIT, timeout=DEFAULT_TIMEOUT_S):
        return query_monarch(curie, DEFAULT_LIMIT if limit is None else limit,
                             timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = query_monarch(sys.argv[1] if len(sys.argv) > 1 else "ZFIN:ZDB-GENE-980526-558")
    print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
    d = r.get("data") or {}
    print(f"total={d.get('n_total')} returned={d.get('n_returned_by_api')} pubs={d.get('publications_resolution')}")
    for it in d.get("items", [])[:8]:
        print(f"  - {it['phenotype_id']} {it['phenotype_label']} pubs={it['publications']}")
