"""
ZFIN_zebrafish_phenotypes — a custom ToolUniverse workspace tool (added 2026-06-22).

WHY THIS TOOL EXISTS (ADR-0027 follow-on / E2E test gate):
ToolUniverse's signaling/pathway/TF tools are human-centric (KEGG hsa:, OmniPath/PANTHER/ReMap
default taxon 9606; PANTHER does not even list 7955). For zebrafish (Danio rerio) developmental
biology — and especially retinoic-acid / nuclear-receptor signaling, which is invisible to
protein-protein-interaction databases — there was NO native zebrafish source. This closes that gap.

WHAT IT DOES:
Resolves a zebrafish gene SYMBOL -> its ZFIN curie (via the Alliance of Genome Resources
search_autocomplete), then returns observed mutant/knockdown phenotype STATEMENTS from ZFIN
(served through the Alliance REST API), optionally filtered by an anatomy keyword (e.g. 'pronephr',
'glomer', 'duct', 'tubul'), each with backing PMIDs. taxon NCBITaxon:7955.

Data source: Alliance of Genome Resources (https://www.alliancegenome.org/api), ZFIN data provider.
NO API key required. Read-only HTTP GET. Pure stdlib (urllib) so the logic is importable + testable
without the tooluniverse package installed.

IDs are RESOLVED LIVE from the symbol (never hardcoded from memory) — consistent with CLAUDE.md §7.

ADR-0078 (2026-09-14) — hygiene of the reference parser and honest declaration of every cut:
  * The Alliance phenotype payload no longer carries `pubmedPubModIDs` (verified 2026-09-13 on
    wt1a, 53/53 statements): PMIDs now live in `pubmedPublications[].referencedCurie`. The old
    parser read the dead key and returned references=[] under status 'success' — a silent loss.
    The parser now reads the new key first and FALLS BACK to the old one; which schema fed each
    statement is DECLARED in `references_schema`.
  * Three states, never conflated: 'success' (statements with PMIDs), 'success-no-references'
    (statements exist but ZERO PMIDs could be parsed — the caller must not read that as "ZFIN has
    no literature"), 'error' (the search itself failed).
  * Every cap is declared: the API is asked with limit=300 (`phenotypes_capped_at_300`), the
    per-statement PMID list is capped at 5 (`references_truncated`, `n_references_total`), and the
    caller's `limit` on statements (`statements_truncated`).
  * Optional SERVER-SIDE anatomy filter (`filter.termName=<term>`, ONE GET PER TERM, union in the
    client) with the client-side filter kept as the backstop, plus a propagable `timeout` so the
    caller's wall-clock budget bounds the request in flight (§6 no-hang).

ADR-0078 corrector (2026-09-14) — what the live measurement changed:
  * `filter.termName=pronephr|glomer` (raw '|', the OR the first cut ASSUMED) was sent ONCE to the live
    API (GET …/gene/ZFIN:ZDB-GENE-980526-558/phenotypes?limit=300&filter.termName=pronephr|glomer) and
    Alliance answered **HTTP 400 Bad Request**. '|' is not an OR separator; a multi-root question would
    have turned every symbol into status 'error'. The tool no longer joins terms: with server_filter=True
    it issues one GET per term and unions the statements client-side (deduplicated by statement).
  * The single-term form `filter.termName=<term>` is still UNMEASURED live, so `server_filter` now
    defaults to False (client filter over the unfiltered payload — the path the 53/53 fixture proves).
    The integrator opts in via WITT_ZFIN_SERVER_FILTER=1 once the single-term GET is measured.
  * The client backstop matches WORD-PREFIX (`\\bpronephr`, `\\bduct`), not raw substring: 'duct' no
    longer matches 'reduction'/'induction'/'conduction'. Same semantics as search_queries.ANATOMY_GROUPS
    (the detector that produced the terms). Declared in `anatomy_filter_semantics`.
  * `n_phenotypes_total` is the GENE total only when the payload was unfiltered; with the server filter
    it is None (not measured) and `server_filter_totals` carries the per-term totals. The scope travels
    in `n_phenotypes_total_scope: 'gene' | 'server-filtered'`. `n_http_gets` counts the GETs made.
Fixture recorded from the live API: rag_index/query_service/fixtures/alliance_phenotypes_wt1a_20260913.json
Offline gate: rag_index/query_service/smoke_zfin_tool.py
"""
import json
import re
import urllib.request
import urllib.parse

_BASE = "https://www.alliancegenome.org/api"
_UA = {"User-Agent": "witt-organo/1.0 (zfin-tool)", "Accept": "application/json"}

# ADR-0078: both caps are constants so the smoke can assert their DECLARATION, not their value.
PHENOTYPES_API_LIMIT = 300   # `?limit=300` sent to the Alliance API; more than that is NOT fetched
REFERENCES_CAP = 5           # PMIDs kept per statement; the cut is declared per statement + per result
DEFAULT_TIMEOUT_S = 30       # urllib socket timeout when the caller passes none

# ADR-0078: the reference schemas this parser understands, in the order they are tried.
REFERENCES_SCHEMA_NEW = "pubmedPublications"    # 2026-09 Alliance payload: [{referencedCurie:'PMID:..'}]
REFERENCES_SCHEMA_OLD = "pubmedPubModIDs"       # pre-2026-09 payload: ['PMID:..'] (golden zfin_sweep_20260822)
REFERENCES_SCHEMA_NONE = "none"                 # neither key yielded a PMID
REFERENCES_SCHEMA_MIXED = "mixed"               # result-level only: statements disagree on schema


def _get(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module (the offline smoke monkeypatches it to serve fixtures)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _resolve_curie(symbol, timeout=DEFAULT_TIMEOUT_S):
    """Zebrafish gene SYMBOL -> ZFIN curie (ZFIN:ZDB-GENE-...), live. Exact gene-name match preferred."""
    j = _get(f"{_BASE}/search_autocomplete?q={urllib.parse.quote(symbol)}", timeout=timeout)
    genes = [r for r in j.get("results", []) if r.get("category") == "gene_search_result"]
    for r in genes:                                   # exact symbol match first
        if str(r.get("name", "")).lower() == symbol.lower():
            return r.get("curie")
    return genes[0].get("curie") if genes else None   # else first gene hit


def parse_references(result):
    """ADR-0078 — PMIDs of ONE phenotype statement, with the schema that produced them DECLARED.

    Returns (refs, schema):
      refs   — full list of 'PMID:...' curies, UNCAPPED (the caller caps and declares the cut)
      schema — 'pubmedPublications' (new payload) | 'pubmedPubModIDs' (old payload, fallback) | 'none'
    Order of preference: new key first; the old key only when the new one yields nothing. A statement
    whose keys are both absent/empty is 'none' — declared, never defaulted to [] under a happy schema.
    """
    pubs = result.get("pubmedPublications") or []
    refs = [p.get("referencedCurie") for p in pubs
            if isinstance(p, dict) and str(p.get("referencedCurie", "")).startswith("PMID:")]
    if refs:
        return refs, REFERENCES_SCHEMA_NEW
    old = [str(x) for x in (result.get("pubmedPubModIDs") or []) if str(x).startswith("PMID:")]
    if old:
        return old, REFERENCES_SCHEMA_OLD
    return [], REFERENCES_SCHEMA_NONE


def _anatomy_terms(anatomy, anatomy_terms):
    """Deduplicated, non-empty, lower-cased list of anatomy keywords (single `anatomy` + extra terms)."""
    out = []
    for t in [anatomy] + list(anatomy_terms or []):
        t = (t or "").strip().lower()
        if t and t not in out:
            out.append(t)
    return out


def _phenotypes_url(curie, term=None):
    """URL of the phenotypes endpoint; with `term`, ONE server-side `filter.termName=<term>`.
    ADR-0078 corrector: terms are never joined with '|' — measured live 2026-09-14 as HTTP 400."""
    url = f"{_BASE}/gene/{curie}/phenotypes?limit={PHENOTYPES_API_LIMIT}"
    if term:
        url += "&filter.termName=" + urllib.parse.quote(term)
    return url


ANATOMY_FILTER_SEMANTICS = "word-prefix (client backstop, \\b<term>) over per-term filter.termName (server)"


def _matches_anatomy(statement, terms):
    """Client backstop: True when ANY term matches at a WORD START of the statement (case-insensitive).
    'duct' matches 'pronephric duct' but not 'reduction'; 'pronephr' matches 'pronephric'/'pronephros'."""
    low = (statement or "").lower()
    return any(re.search(r"\b" + re.escape(t), low) for t in terms)


def _statement_key(result):
    """Identity of one phenotype statement for the per-term union (same statement served by two
    term-filtered GETs must count once)."""
    return json.dumps(result, sort_keys=True, ensure_ascii=False, default=str)


def query_zfin(symbol, anatomy=None, limit=50, anatomy_terms=None, server_filter=False,
               timeout=DEFAULT_TIMEOUT_S):
    """Core logic (stdlib-only, importable for standalone testing).

    Args:
      symbol         — zebrafish gene symbol, resolved LIVE to its ZFIN curie.
      anatomy        — optional anatomy keyword (case-insensitive substring of the statement).
      limit          — max phenotype statements returned (default 50); the cut is DECLARED.
      anatomy_terms  — ADR-0078: optional extra anatomy keywords, OR-ed with `anatomy` (server + client).
      server_filter  — ADR-0078 corrector: default False (client filter over the unfiltered payload).
                       When True and there is at least one term, the API is asked ONCE PER TERM with
                       `&filter.termName=<term>` (never '|'-joined: measured HTTP 400) and the results
                       are unioned; the client-side word-prefix filter is ALWAYS applied as the backstop,
                       so a permissive server never widens the match.
      timeout        — ADR-0078: urllib socket timeout in seconds for EACH GET (resolve + 1 phenotypes
                       GET, or 1 per term with server_filter); default DEFAULT_TIMEOUT_S=30. The
                       integrator passes min(10, remaining budget / 2) so the caller's wall clock bounds
                       the calls in flight. timeout <= 0 short-circuits to status 'error' WITHOUT
                       touching the network.

    Returns {status, data} where status is one of
      'success'                — >=1 statement returned and >=1 PMID parsed across them
      'success-no-references'  — statements returned but ZERO PMIDs parsed (declared, not hidden as 'success')
      'error'                  — the lookup itself failed ({status:'error', error:'<Type>: <msg>'})
    and data = {symbol, zfin_curie, taxon, n_phenotypes_total, n_phenotypes_total_scope, n_returned_by_api,
                n_http_gets, phenotypes_capped_at_300, n_matched, statements_truncated, anatomy_filter,
                anatomy_terms, anatomy_filter_mode, anatomy_filter_semantics, server_filter_totals?,
                references_schema, references_cap, references_truncated, n_statements_with_references,
                n_statements_without_references,
                phenotypes: [{statement, references, references_schema, n_references_total,
                              references_truncated}]}.
    n_matched == 0 with status 'success' is "searched, nothing on this anatomy" (no-match), not an error.
    """
    try:
        if timeout is not None and timeout <= 0:
            return {"status": "error",
                    "error": f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)"}
        curie = _resolve_curie(symbol, timeout=timeout)
        if not curie:
            return {"status": "error", "error": f"no ZFIN zebrafish gene resolved for symbol {symbol!r}"}
        terms = _anatomy_terms(anatomy, anatomy_terms)
        n_gets = 1   # the resolve GET
        server_totals = None
        if server_filter and terms:
            # ADR-0078 corrector: ONE GET per term (raw '|' measured HTTP 400), union deduplicated by
            # statement; the gene total is NOT measured on this path (every payload is filtered).
            results, seen, server_totals, per_term_n = [], set(), {}, {}
            for term in terms:
                jt = _get(_phenotypes_url(curie, term), timeout=timeout)
                n_gets += 1
                server_totals[term] = jt.get("total")
                per_term_n[term] = len(jt.get("results") or [])
                for r in (jt.get("results") or []):
                    k = _statement_key(r)
                    if k not in seen:
                        seen.add(k)
                        results.append(r)
            total, total_scope = None, "server-filtered"
        else:
            j = _get(_phenotypes_url(curie), timeout=timeout)
            n_gets += 1
            results = j.get("results") or []
            total, total_scope = j.get("total"), "gene"

        phenos, schemas = [], set()
        n_with_refs = n_without_refs = 0
        any_ref_truncated = False
        for r in results:
            stmt = r.get("phenotypeStatement", "") or ""
            if terms and not _matches_anatomy(stmt, terms):   # client-side word-prefix backstop, always on
                continue
            refs, schema = parse_references(r)
            schemas.add(schema)
            truncated = len(refs) > REFERENCES_CAP
            any_ref_truncated = any_ref_truncated or truncated
            if refs:
                n_with_refs += 1
            else:
                n_without_refs += 1
            phenos.append({"statement": stmt,
                           "references": refs[:REFERENCES_CAP],
                           "references_schema": schema,
                           "n_references_total": len(refs),
                           "references_truncated": truncated})

        if not schemas:
            result_schema = REFERENCES_SCHEMA_NONE
        elif len(schemas) == 1:
            result_schema = next(iter(schemas))
        else:
            result_schema = REFERENCES_SCHEMA_MIXED

        n_returned_by_api = len(results)
        if total_scope == "gene":
            capped = ((isinstance(total, int) and total > n_returned_by_api)
                      or n_returned_by_api >= PHENOTYPES_API_LIMIT)
        else:   # per-term payloads: capped if ANY term-GET declared more than it returned or hit the API limit
            capped = any((isinstance(server_totals[t], int) and server_totals[t] > per_term_n[t])
                         or per_term_n[t] >= PHENOTYPES_API_LIMIT for t in per_term_n)
        status = "success-no-references" if (phenos and n_with_refs == 0) else "success"
        if terms:
            mode = "server+client" if server_filter else "client"
        else:
            mode = "none"
        data = {
            "symbol": symbol,
            "zfin_curie": curie,
            "taxon": "NCBITaxon:7955",
            "n_phenotypes_total": total,
            "n_phenotypes_total_scope": total_scope,   # ADR-0078 corrector: 'gene' | 'server-filtered'
            "n_returned_by_api": n_returned_by_api,
            "n_http_gets": n_gets,
            "phenotypes_capped_at_300": bool(capped),
            "n_matched": len(phenos),
            "statements_truncated": len(phenos) > limit if limit is not None else False,
            "anatomy_filter": anatomy,
            "anatomy_terms": terms,
            "anatomy_filter_mode": mode,
            "anatomy_filter_semantics": ANATOMY_FILTER_SEMANTICS if terms else None,
            "references_schema": result_schema,
            "references_cap": REFERENCES_CAP,
            "references_truncated": any_ref_truncated,
            "n_statements_with_references": n_with_refs,
            "n_statements_without_references": n_without_refs,
            "phenotypes": phenos[:limit] if limit is not None else phenos,
        }
        if server_totals is not None:
            data["server_filter_totals"] = server_totals   # per-term `total` as the API declared it
        return {"status": status, "data": data}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class ZFIN_zebrafish_phenotypes:
    name = "ZFIN_zebrafish_phenotypes"
    description = (
        "Zebrafish (Danio rerio, taxon 7955) gene phenotypes from ZFIN via the Alliance of Genome "
        "Resources API. Resolves a zebrafish gene SYMBOL to its ZFIN curie and returns observed "
        "mutant/knockdown phenotype statements, optionally filtered by an anatomy keyword (e.g. "
        "'pronephr', 'glomer', 'duct', 'tubul'), each with backing PMIDs. Use for native zebrafish "
        "developmental phenotypes — including retinoic-acid-axis genes (aldh1a2, cyp26a1) — that the "
        "human-centric pathway/PPI tools cannot provide. No API key. Example: symbol='pax2a', "
        "anatomy='pronephr' returns 'pronephric duct absent, abnormal' with PMIDs. Status "
        "'success-no-references' means statements exist but no PMID could be parsed (ADR-0078)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'pax2a', 'wt1a', 'aldh1a2'."},
            "anatomy": {"type": ["string", "null"], "description": "Optional anatomy keyword to filter phenotype statements, e.g. 'pronephr', 'glomer', 'duct'."},
            "limit": {"type": ["integer", "null"], "description": "Max phenotype statements to return (default 50); the cut is declared in statements_truncated."},
            "anatomy_terms": {"type": ["array", "null"], "items": {"type": "string"},
                              "description": "Optional extra anatomy keywords OR-ed with `anatomy` (ADR-0078)."},
            "server_filter": {"type": ["boolean", "null"], "description": "Send each anatomy term as its own `filter.termName` GET (default false — the single-term filter is unmeasured live; '|'-joining measured HTTP 400); the client filter stays as backstop."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds per HTTP GET (default 30)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, anatomy=None, limit=50, anatomy_terms=None, server_filter=False, timeout=DEFAULT_TIMEOUT_S):
        return query_zfin(symbol, anatomy, 50 if limit is None else limit, anatomy_terms=anatomy_terms,
                          server_filter=False if server_filter is None else server_filter,
                          timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


if __name__ == "__main__":
    # Standalone smoke test (NO key, real API): pronephros phenotypes for the TF set + RA-axis genes.
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for sym in ("pax2a", "wt1a", "aldh1a2", "cyp26a1"):
        r = query_zfin(sym, anatomy="pronephr", limit=4)
        d = r.get("data", {})
        print(f"{sym}: status={r.get('status')} curie={d.get('zfin_curie')} total={d.get('n_phenotypes_total')} "
              f"pronephr-matched={d.get('n_matched')} schema={d.get('references_schema')}")
        for p in d.get("phenotypes", []):
            print(f"    - {p['statement']}  PMIDs={p['references']}")
