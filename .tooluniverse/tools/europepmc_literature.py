"""
europepmc_literature — a custom ToolUniverse workspace tool (added 2026-06-23).

WHY: the standard ToolUniverse kit lacked a friction-free literature lens for developmental-biology
claims (the 2026-06-22 E2E test could not capture the experimental consensus — e.g. retinoic-acid /
wnt8 / fgf8 -> pronephros — from any human-centric pathway/PPI tool). This wraps Europe PMC
(europepmc.org), which indexes PubMed + PMC + preprints, returns clean JSON, and needs NO API key.

WHAT IT DOES: full-text-aware literature search; returns ranked hits with PMID/PMCID, title, year,
journal, authorString, citationCount, and an abstract snippet. Use it as the LITERATURE evidence lens
(tier: literature — weaker than native loss-of-function, stronger than ortholog PPI for an organism-level
mechanistic consensus). Pair query terms with the species ("zebrafish"/"Danio rerio") for native claims.

Read-only HTTP GET, pure stdlib (urllib) so the logic is importable + testable without tooluniverse.
PMIDs returned are EXTERNAL identifiers — verify before using in evidence_cited (CLAUDE.md §7); this tool
RETRIEVES them with provenance (Europe PMC), it does not mint them.
"""
import json
import urllib.request
import urllib.parse

_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_UA = {"User-Agent": "witt-organo/1.0 (europepmc-tool)", "Accept": "application/json"}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def query_europepmc(query, limit=8, open_access_only=False):
    """Core logic (stdlib-only). Returns {status, data:{query, hit_count, n_returned, results:[...]}}.
    Each result: {pmid, pmcid, doi, title, year, journal, authors, cited_by, is_oa, snippet}."""
    try:
        q = query if not open_access_only else f"({query}) AND OPEN_ACCESS:Y"
        params = urllib.parse.urlencode({
            "query": q, "format": "json", "pageSize": max(1, min(int(limit), 25)),
            "resultType": "core", "sort": "CITED desc",
        })
        j = _get(f"{_BASE}?{params}")
        out = []
        for r in j.get("resultList", {}).get("result", []):
            abstract = r.get("abstractText", "") or ""
            out.append({
                "pmid": r.get("pmid"), "pmcid": r.get("pmcid"), "doi": r.get("doi"),
                "title": r.get("title"), "year": r.get("pubYear"),
                "journal": (r.get("journalInfo", {}) or {}).get("journal", {}).get("title")
                           or r.get("source"),
                "authors": r.get("authorString"),
                "cited_by": r.get("citedByCount"),
                "is_oa": r.get("isOpenAccess") == "Y",
                "snippet": (abstract[:300] + "…") if len(abstract) > 300 else abstract,
            })
        return {"status": "success", "data": {
            "query": q, "hit_count": j.get("hitCount"), "n_returned": len(out), "results": out,
        }}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class europepmc_literature:
    name = "europepmc_literature"
    description = (
        "Literature evidence lens via Europe PMC (PubMed + PMC + preprints; no API key). Returns ranked "
        "papers (by citations) with PMID/PMCID/DOI, title, year, journal, authors, citation count, and an "
        "abstract snippet. Use to capture the experimental/mechanistic CONSENSUS for a biological claim — "
        "especially organism-native results (pair the query with 'zebrafish'/'Danio rerio'). Example: "
        "query='wnt8a fgf8 pronephros induction zebrafish'. PMIDs are retrieved with provenance; verify "
        "any external identifier before citing (CLAUDE.md §7)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text / field query, e.g. 'retinoic acid pronephros zebrafish' or 'wnt8a AND kidney'."},
            "limit": {"type": ["integer", "null"], "description": "Max papers (default 8, max 25)."},
            "open_access_only": {"type": ["boolean", "null"], "description": "Restrict to open-access (default false)."},
        },
        "required": ["query"],
    }

    def run(self, query, limit=8, open_access_only=False):
        return query_europepmc(query, limit, open_access_only)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for q in ("wnt8 pronephros zebrafish kidney induction",
              "fgf8 intermediate mesoderm pronephros zebrafish",
              "retinoic acid pronephros segment zebrafish wingert"):
        r = query_europepmc(q, limit=3)
        d = r.get("data", {})
        print(f"\nQUERY: {q}  (hits={d.get('hit_count')})")
        for p in d.get("results", []):
            print(f"  - PMID:{p['pmid']} ({p['year']}, cited {p['cited_by']}) {str(p['title'])[:88]}")
