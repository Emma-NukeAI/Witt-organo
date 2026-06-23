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
"""
import json
import urllib.request
import urllib.parse

_BASE = "https://www.alliancegenome.org/api"
_UA = {"User-Agent": "witt-organo/1.0 (zfin-tool)", "Accept": "application/json"}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _resolve_curie(symbol):
    """Zebrafish gene SYMBOL -> ZFIN curie (ZFIN:ZDB-GENE-...), live. Exact gene-name match preferred."""
    j = _get(f"{_BASE}/search_autocomplete?q={urllib.parse.quote(symbol)}")
    genes = [r for r in j.get("results", []) if r.get("category") == "gene_search_result"]
    for r in genes:                                   # exact symbol match first
        if str(r.get("name", "")).lower() == symbol.lower():
            return r.get("curie")
    return genes[0].get("curie") if genes else None   # else first gene hit


def query_zfin(symbol, anatomy=None, limit=50):
    """Core logic (stdlib-only, importable for standalone testing).
    Returns {status, data:{symbol, zfin_curie, taxon, n_phenotypes_total, n_matched, anatomy_filter,
    phenotypes:[{statement, references}]}}."""
    try:
        curie = _resolve_curie(symbol)
        if not curie:
            return {"status": "error", "error": f"no ZFIN zebrafish gene resolved for symbol {symbol!r}"}
        j = _get(f"{_BASE}/gene/{curie}/phenotypes?limit=300")
        phenos = []
        for r in j.get("results", []):
            stmt = r.get("phenotypeStatement", "") or ""
            if anatomy and anatomy.lower() not in stmt.lower():
                continue
            phenos.append({"statement": stmt, "references": (r.get("pubmedPubModIDs") or [])[:5]})
        return {"status": "success", "data": {
            "symbol": symbol,
            "zfin_curie": curie,
            "taxon": "NCBITaxon:7955",
            "n_phenotypes_total": j.get("total"),
            "n_matched": len(phenos),
            "anatomy_filter": anatomy,
            "phenotypes": phenos[:limit],
        }}
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
        "anatomy='pronephr' returns 'pronephric duct absent, abnormal' with PMIDs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'pax2a', 'wt1a', 'aldh1a2'."},
            "anatomy": {"type": ["string", "null"], "description": "Optional anatomy keyword to filter phenotype statements, e.g. 'pronephr', 'glomer', 'duct'."},
            "limit": {"type": ["integer", "null"], "description": "Max phenotype statements to return (default 50)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, anatomy=None, limit=50):
        return query_zfin(symbol, anatomy, limit)


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
        print(f"{sym}: curie={d.get('zfin_curie')} total={d.get('n_phenotypes_total')} pronephr-matched={d.get('n_matched')}")
        for p in d.get("phenotypes", []):
            print(f"    - {p['statement']}  PMIDs={p['references']}")
