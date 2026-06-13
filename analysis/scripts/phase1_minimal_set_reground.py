"""
phase1_minimal_set_reground.py — re-ground the 2026-05-14 pronephros minimal-set
hypothesis through the LIVE DATA INAMOVIBLE (GWT v1.1 POC, Phase 1).

This does NOT recompute biology. It takes the EXISTING 9-protein sufficiency hypothesis
(claim_20260514_143000_pronephros-minimal-set) and re-anchors it through the live
source-of-truth, exercising the deployed stack end-to-end:
  (a) resolve EVERY candidate ID against the verified store (anti-fabrication gate, §7);
  (b) semantic-query the live Neo4j GraphRAG to ground the question to corpus assets,
      INCLUDING a negated query for contradictory evidence (closes gp-2026-06-10).

Spend (authorized 2026-06-13): resolve = free/local; queries + the embedder probe call
OpenAI text-embedding-3-small (~5 embeds, fractions of a cent). Each query response is
cached raw to mcp_cache/ per CLAUDE.md §6 cache discipline.

Run: ./.venv/Scripts/python.exe analysis/scripts/phase1_minimal_set_reground.py
"""
import os
import sys
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "graphrag"))

# load secrets + point the backend at the hosted Neo4j (same convenience as the MCP server)
_env = ROOT / ".secrets" / "deploy.env"
if not os.environ.get("NEO4J_URI") and _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("RAG_BACKEND", "neo4j")

from lib import resolve_id, rag_backend  # noqa: E402

CACHE = ROOT / "mcp_cache"
DATE = "20260613"  # stamped explicitly (no Date.now in-script)

# --- the 2026-05-14 hypothesis, verbatim by window (claim_20260514_143000) ---
H1 = {
    "W2_specification": ["osr1", "pax2a", "lhx1a", "wt1a"],
    "W3_polarity_adhesion": ["prkci", "cdh17", "myh9a"],
    "W4_differentiation": ["mafba", "podxl"],
}
# H0 missing-factor candidates the prior claim itself named (expected_outcome_if_h0)
H0_CANDIDATES = ["wnt2ba", "slc20a1a", "slc4a4a"]
# identity-confirmation markers (gates: Specificity / Identity)
MARKERS = ["nphs1", "nphs2", "slc12a1", "gata3", "hnf1ba", "sim1a", "irx3b"]


def sweep(symbols):
    out = {}
    for s in symbols:
        r = resolve_id.resolve(s)
        if r is resolve_id.NOT_FOUND:
            out[s] = {"resolved": False, "action": "FLAG: verify externally + cache raw (§7.9) before use"}
        else:
            out[s] = {"resolved": True, "ensdarg": r.ensdarg,
                      "tier": "RAW" if r.is_raw_verified else "DERIVED", "verified_on": r.verified_on}
    return out


report = {"phase": "1 — minimal-set re-grounding", "store_version": resolve_id.store_version(),
          "resolve_sweep": {}, "semantic_queries": {}}

# (a) anti-fabrication resolve sweep — FREE, local, deterministic
report["resolve_sweep"]["H1_minimal_set"] = sweep([g for win in H1.values() for g in win])
report["resolve_sweep"]["H0_candidates"] = sweep(H0_CANDIDATES)
report["resolve_sweep"]["markers"] = sweep(MARKERS)
resolved = {g: v for grp in report["resolve_sweep"].values() for g, v in grp.items() if v["resolved"]}
notfound = {g: v for grp in report["resolve_sweep"].values() for g, v in grp.items() if not v["resolved"]}
report["resolve_summary"] = {"resolved_n": len(resolved), "not_found_n": len(notfound),
                             "not_found": sorted(notfound.keys())}

# probe the embedder once (confirms the paid OpenAI path + vector dim before the queries)
try:
    from embeddings import get_embedder
    _emb = get_embedder()
    _v = _emb(["pronephros embedder probe"])[0]
    report["embedder_probe"] = {"ok": True, "dim": len(_v)}
except Exception as e:
    report["embedder_probe"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

# (b) semantic grounding queries — PAID (OpenAI embeddings, authorized). Includes a NEGATED query.
QUERIES = {
    "ground_specification": "zebrafish pronephros podocyte and tubule segment identity specification transcription factors",
    "ground_minimal_set": "minimal regulatory set sufficient to induce pronephric kidney tissue identity reconstitution",
    "contradiction_negated": "evidence that pax2a wt1a lhx1a alone are NOT sufficient for pronephros; additional upstream fgf wnt retinoic-acid signals required",
    "ground_maturation": "podocyte slit diaphragm maturation podxl nphs1 mafba pronephros differentiation",
}
for key, q in QUERIES.items():
    try:
        hits = rag_backend.query(q, k=5)
        serial = [{"doc_id": h.doc_id, "score": round(h.score, 4), "type": h.type,
                   "text": (h.text or "")[:220], "meta": h.metadata} for h in hits]
        entry = {"query": q, "n_hits": len(serial), "hits": serial}
    except Exception as e:
        entry = {"query": q, "error": f"{type(e).__name__}: {e}"}
    report["semantic_queries"][key] = entry
    # cache raw per §6 (≥3 query calls in this workflow)
    (CACHE / f"raw_query_{key}_{DATE}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report, ensure_ascii=False, indent=2))
