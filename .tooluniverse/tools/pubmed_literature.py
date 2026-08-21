"""
pubmed_literature — a custom ToolUniverse workspace tool (added 2026-08-20, tapón 1·B / ADR-0062).

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

Read-only HTTP GET, pure stdlib (urllib) so the logic is importable + testable without the
tooluniverse package. PMIDs returned are EXTERNAL identifiers RETRIEVED with provenance (NCBI), not
verified-for-citation (CLAUDE.md §7 — verify_output still gates whatever gets cited).
"""
import json
import os
import urllib.parse
import urllib.request

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_UA = {"User-Agent": "witt-organo/1.0 (pubmed-tool)", "Accept": "application/json"}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _key_param():
    k = os.environ.get("NCBI_API_KEY", "").strip()
    return f"&api_key={urllib.parse.quote(k)}" if k else ""


def query_pubmed(query, limit=8):
    """Core logic (stdlib-only, importable for standalone testing).
    Returns {status, data:{query, n_found_total, records:[{pmid, title, year, journal}]}}."""
    try:
        q = urllib.parse.quote((query or "").strip())
        if not q:
            return {"status": "error", "error": "empty query"}
        js = _get(f"{_EUTILS}/esearch.fcgi?db=pubmed&term={q}&retmode=json"
                  f"&retmax={int(limit)}&sort=relevance{_key_param()}")
        res = js.get("esearchresult", {})
        ids = res.get("idlist", []) or []
        n_total = int(res.get("count", 0) or 0)
        if not ids:
            return {"status": "success",
                    "data": {"query": query, "n_found_total": n_total, "records": []}}
        js2 = _get(f"{_EUTILS}/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json{_key_param()}")
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
        return {"status": "success",
                "data": {"query": query, "n_found_total": n_total, "records": records}}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


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
        "Coverage overlaps Europe PMC (which indexes PubMed) — the value is ranking diversity and "
        "source independence; DEDUP BY PMID against Europe PMC results before use."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "English keyword query, e.g. 'wt1a zebrafish pronephros'."},
            "limit": {"type": ["integer", "null"], "description": "Max records (default 8)."},
        },
        "required": ["query"],
    }

    def run(self, query, limit=8):
        return query_pubmed(query, limit)


if __name__ == "__main__":
    # Standalone smoke test (no key required, real API)
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = query_pubmed(" ".join(sys.argv[1:]) or "wt1a zebrafish pronephros", limit=5)
    print(json.dumps(out, ensure_ascii=False, indent=2))
