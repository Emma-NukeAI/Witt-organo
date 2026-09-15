"""
UniProt_zebrafish_protein — Layer 0 workspace tool (ADR-0080, harness lote B, added 2026-09-15).

WHY THIS TOOL EXISTS (ADR-0080 §4 harness de busqueda):
The search harness needs a protein-level anchor for a zebrafish gene symbol (accession, reviewed vs
unreviewed status, protein name, sequence length, ZFIN/Ensembl cross-references) so that ortholog,
pathway and interaction sources can be tied to ONE resolvable identifier instead of a bare symbol.
UniProtKB REST is public, keyless, JSON, read-only GET — it fits Layer 0 (CLAUDE.md §6: stdlib-pure).

WHAT IT DOES:
ONE GET to https://rest.uniprot.org/uniprotkb/search?query=gene_exact:<sym> AND organism_id:7955
&format=json&size=<n>. Returns the entries as normalized items; every entry NOT on taxon 7955 is
dropped and COUNTED (`n_off_taxon`), never silently kept.

ADR-0080 doctrine honored here (same skeleton as zfin_zebrafish.py):
  * `_get(url, timeout)` is the ONLY network seam (the offline smoke monkeypatches it to serve the fixture).
  * Three states, never conflated: 'success' (>=1 zebrafish entry), 'no-match' (the search ran and
    returned zero entries — "UniProt has nothing under that exact gene name", not an error), 'error'
    (the lookup itself failed; the caller's ledger row stays 'error' and the run continues, §6 no-hang).
  * Every cut is DECLARED: `n_total` comes from the `X-Total-Results` header (source declared in
    `n_total_source`; None + 'not-available' when the header is absent), `truncated_by_size` when the
    header says more than the page holds.
  * Per-day READ cache under mcp_cache/uniprot_<slug>_<YYYYMMDD>.json (`cache_hit`, `cache_ref`
    declared): a second call the same day never touches the network. A cache failure never fails the
    call — it is declared in `cache_error`.
  * `timeout` propagates to the GET; timeout <= 0 short-circuits to status 'error' (BudgetExhausted)
    WITHOUT touching the network, so the harness round budget bounds the call in flight.
  * Identifiers travel with their provenance: `identifier_provenance` = 'uniprot-rest:gene_exact' and
    the ZFIN cross-reference is copied VERBATIM from the entry (never composed from memory).
  * label: None (a UniProt record is a curated/automatic annotation record, neither 'predictive' nor
    'inferred-by-orthology'); evidence_kind 'protein-record'.

Measured live 2026-09-15 (wt1a): HTTP 200, 5 entries returned, X-Total-Results 6 (truncated_by_size
True), all 5 UniProtKB unreviewed (TrEMBL), all taxon 7955, ZFIN xref ZDB-GENE-980526-558 present.
Fixture: rag_index/query_service/fixtures/uniprot_wt1a_20260915.json
Offline gate: rag_index/query_service/smoke_tools_b.py
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://rest.uniprot.org/uniprotkb/search"
_HOST = "rest.uniprot.org"
_UA = {"User-Agent": "witt-organo/1.0 (uniprot-tool)", "Accept": "application/json"}

TOOL_FAMILY = "uniprot"
EVIDENCE_KIND = "protein-record"
LABEL = None                      # ADR-0080: neither 'predictive' nor 'inferred-by-orthology'
IDENTIFIER_PROVENANCE = "uniprot-rest:gene_exact"
ZEBRAFISH_TAXON_ID = 7955
DEFAULT_SIZE = 5                  # `size=5` sent to the API; the cut is declared in truncated_by_size
DEFAULT_TIMEOUT_S = 30            # urllib socket timeout when the caller passes none
TOTAL_HEADER = "x-total-results"  # the ONLY source of n_total; declared in n_total_source

# repo root = .tooluniverse/tools/<this>.py -> parents[2]; per-day read cache lives in mcp_cache/.
_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "mcp_cache"


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module. Returns (payload_json, headers_lower) — the headers are
    needed because UniProt reports the total ONLY in `X-Total-Results`."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
        headers = {k.lower(): v for k, v in r.headers.items()}
    return payload, headers


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "symbol"


def _cache_path(symbol, size):
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    return CACHE_DIR / f"{TOOL_FAMILY}_{_slug(symbol)}_s{int(size)}_{date}.json"


def _cache_read(path):
    """Per-day read cache. Returns (payload, headers) or None; malformed cache = miss (declared by caller)."""
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return blob["response"], blob.get("headers") or {}
    except Exception:
        return None


def _cache_write(path, url, payload, headers):
    """Best effort; the caller declares failure in `cache_error`. Never raises."""
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        blob = {"_cache": {"tool": TOOL_FAMILY, "url": url,
                           "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                "headers": headers, "response": payload}
        path.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def build_url(symbol, size=DEFAULT_SIZE):
    """query=gene_exact:<sym> AND organism_id:7955, format json, size declared."""
    q = urllib.parse.quote(f"gene_exact:{symbol} AND organism_id:{ZEBRAFISH_TAXON_ID}")
    return f"{_BASE}?query={q}&format=json&size={int(size)}"


def _xrefs(entry, databases):
    out = {}
    for x in entry.get("uniProtKBCrossReferences") or []:
        db = x.get("database")
        if db in databases and x.get("id"):
            out.setdefault(db, []).append(x.get("id"))
    return out


def parse_entry(entry):
    """ONE UniProtKB entry -> normalized item. Every field is copied from the payload; missing = None."""
    acc = entry.get("primaryAccession")
    pd = entry.get("proteinDescription") or {}
    rec = (pd.get("recommendedName") or {}).get("fullName") or {}
    sub = ((pd.get("submissionNames") or [{}])[0].get("fullName") or {})
    protein_name = rec.get("value") or sub.get("value")
    genes = [(g.get("geneName") or {}).get("value") for g in (entry.get("genes") or [])]
    genes = [g for g in genes if g]
    org = entry.get("organism") or {}
    seq = entry.get("sequence") or {}
    xr = _xrefs(entry, {"ZFIN", "Ensembl", "GeneID", "RefSeq", "STRING"})
    entry_type = entry.get("entryType") or ""
    # ADR-0080: three states — True (Swiss-Prot 'reviewed'), False ('unreviewed'/TrEMBL), None (entryType
    # absent: NOT measured). 'unreviewed' contains 'reviewed', so the negative is tested first.
    if not entry_type:
        reviewed = None
    else:
        reviewed = False if "unreviewed" in entry_type.lower() else ("reviewed" in entry_type.lower())
    return {
        "evidence_id": f"uniprot:{acc}" if acc else None,
        "kind": EVIDENCE_KIND,
        "source_family": TOOL_FAMILY,
        "label": LABEL,
        "identifier_provenance": IDENTIFIER_PROVENANCE,
        "accession": acc,
        "uniprotkb_id": entry.get("uniProtkbId"),
        "entry_type": entry_type or None,
        "reviewed": reviewed,
        "protein_name": protein_name,
        "gene_names": genes,
        "organism_taxon_id": org.get("taxonId"),
        "organism": org.get("scientificName"),
        "sequence_length": seq.get("length"),
        "annotation_score": entry.get("annotationScore"),
        "last_annotation_update": (entry.get("entryAudit") or {}).get("lastAnnotationUpdateDate"),
        "xrefs": xr,
        "zfin_curie": (f"ZFIN:{xr['ZFIN'][0]}" if xr.get("ZFIN") else None),
        "url": f"https://www.uniprot.org/uniprotkb/{acc}/entry" if acc else None,
        "statement": (f"{protein_name} ({acc}; {entry_type})" if protein_name else None),
        "text": None,
    }


def _parse_total(headers):
    v = (headers or {}).get(TOTAL_HEADER)
    if v is None:
        return None, "not-available"
    try:
        return int(str(v).strip()), f"header:{TOTAL_HEADER}"
    except (TypeError, ValueError):
        return None, f"header:{TOTAL_HEADER}:unparseable"


def query_uniprot(symbol, size=DEFAULT_SIZE, timeout=DEFAULT_TIMEOUT_S, use_cache=True):
    """Core logic (stdlib-only, importable for standalone testing) — ADR-0080.

    Returns {status, query_sent, elapsed_s, cache_hit, cache_ref, n_http_gets, evidence_kind, label,
             data|error}
      status 'success'  — >=1 zebrafish entry
             'no-match' — the search ran, zero entries (declared; NOT an error)
             'error'    — the lookup failed ({error:'<Type>: <msg>'}); BudgetExhausted when timeout<=0
      data = {symbol, taxon, n_returned_by_api, n_total, n_total_source, truncated_by_size, size_sent,
              n_off_taxon, n_reviewed, n_unreviewed, cache_error, items:[parse_entry(...)]}
    """
    t0 = time.monotonic()
    sym = (symbol or "").strip()
    url = build_url(sym, size) if sym else None
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
        path = _cache_path(sym, size)
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

        results = payload.get("results") or []
        items, n_off = [], 0
        for e in results:
            it = parse_entry(e)
            if it["organism_taxon_id"] != ZEBRAFISH_TAXON_ID:
                n_off += 1
                continue
            items.append(it)
        n_total, n_total_source = _parse_total(headers)
        truncated = isinstance(n_total, int) and n_total > len(results)
        data = {
            "symbol": sym,
            "taxon": f"NCBITaxon:{ZEBRAFISH_TAXON_ID}",
            "n_returned_by_api": len(results),
            "n_total": n_total,
            "n_total_source": n_total_source,
            "truncated_by_size": bool(truncated),
            "size_sent": int(size),
            "n_off_taxon": n_off,
            "n_reviewed": sum(1 for i in items if i["reviewed"] is True),
            "n_unreviewed": sum(1 for i in items if i["reviewed"] is False),
            "cache_error": cache_error,
            "items": items,
        }
        return _done(status="success" if items else "no-match", data=data)
    except Exception as e:
        return _done(status="error", error=f"{type(e).__name__}: {e}")


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class UniProt_zebrafish_protein:
    name = "UniProt_zebrafish_protein"
    description = (
        "UniProtKB protein records for a zebrafish (Danio rerio, taxon 7955) gene symbol via the public "
        "UniProt REST search (gene_exact:<symbol> AND organism_id:7955). Returns accession, reviewed status, "
        "protein name, sequence length and ZFIN/Ensembl/GeneID cross-references. No API key. Status "
        "'no-match' means the search ran and found nothing (ADR-0080); n_total comes from X-Total-Results."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "size": {"type": ["integer", "null"], "description": "Entries requested (default 5); the cut is declared in truncated_by_size."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 30)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, size=DEFAULT_SIZE, timeout=DEFAULT_TIMEOUT_S):
        return query_uniprot(symbol, DEFAULT_SIZE if size is None else size,
                             timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = query_uniprot(sys.argv[1] if len(sys.argv) > 1 else "wt1a")
    print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1))
    for it in (r.get("data") or {}).get("items", []):
        print(f"  - {it['accession']} {it['entry_type']} {it['protein_name']} len={it['sequence_length']} zfin={it['zfin_curie']}")
