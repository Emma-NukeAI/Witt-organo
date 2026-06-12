"""
server.py — MCP server fronting the DATA INAMOVIBLE (hosted GraphRAG), per ADR-0020.

This is the single front door the project's agents (and anyone with the project) use to query the
shared DATA INAMOVIBLE. It exposes the TWO halves of the source-of-truth interface as MCP tools:
  - query_data_inamovible(query, k)  -> SEMANTIC GraphRAG retrieval (rag_backend; sparse v1 in dev,
                                        Neo4j GraphRAG on the rack via RAG_BACKEND=neo4j)
  - resolve_identifier(key)          -> DETERMINISTIC identifier resolve (resolve_id: symbol/ENSDARG/
                                        RefSeq/UniProt) against the verified store

Deploy: run this on the rack alongside Neo4j + the embedding service; point Claude/MCP clients here
(see rag_index/mcp_server/README.md + rag_index/deploy/README.md). Requires the MCP Python SDK
(`pip install mcp`). In dev it runs against the local sparse v1 (no Neo4j needed).

Run:  python rag_index/mcp_server/server.py
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))


def _load_local_secrets():
    """Single-host convenience: if NEO4J_URI is not already in the environment, load the deploy vars
    from the gitignored .secrets/deploy.env so the MCP client config carries NO secrets. A hosted /
    production deploy sets real env vars (NEO4J_URI, OPENAI_API_KEY, ...) and this becomes a no-op."""
    if os.environ.get("NEO4J_URI"):
        return
    env_path = ROOT / ".secrets" / "deploy.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
    os.environ.setdefault("RAG_BACKEND", "neo4j")   # secrets file present -> point at the hosted Neo4j


_load_local_secrets()
import json  # noqa: E402
from lib import rag_backend, resolve_id, raw_store  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # SDK not installed in dev — the tools below still importable/testable directly
    FastMCP = None


def _query(query: str, k: int = 5):
    """Semantic GraphRAG search over the DATA INAMOVIBLE. Returns ranked corpus docs with provenance."""
    return [{"doc_id": h.doc_id, "score": round(h.score, 4), "type": h.type,
             "text": h.text, "metadata": h.metadata} for h in rag_backend.query(query, k)]


def _resolve(key: str):
    """Deterministic verified-identifier resolve (symbol | ENSDARG | RefSeq NM_* | UniProt)."""
    r = resolve_id.resolve(key)
    if r is resolve_id.NOT_FOUND:
        return {"resolved": False, "key": key,
                "note": "NOT_FOUND — verify against Ensembl + raw-cache (CLAUDE.md §7.9) before use; never mint."}
    return {"resolved": True, "symbol": r.symbol, "ensdarg": r.ensdarg,
            "tier": "RAW" if r.is_raw_verified else "DERIVED", "raw_cache_ref": r.raw_cache_ref,
            "verified_on": r.verified_on}


def _fetch_raw(key: str, filename: str = None, expires_seconds: int = 3600):
    """Resolve a corpus record / accession to its RAW data location(s) — the drill-down path for when a
    chunk/embedding is NOT enough and the agent needs the raw data that composes the truth. Returns
    retrievable URLs: a presigned MinIO URL (mirrored private/derived) or the canonical source_url +
    sha256 (public source-pointer, hybrid policy)."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    k = str(key).strip().lower()

    def _match(r):
        if r.get("corpus_record_id", "").lower() == k:
            return True
        acc = str(r.get("source_document", {}).get("accession", "")).lower()
        return bool(acc) and k in acc

    rec = next((r for r in man.get("records", []) if _match(r)), None)
    if rec is None:
        return {"found": False, "key": key,
                "note": "no corpus record matches; pass a corpus_record_id (CORPUS-YYYY-NNNN) or an "
                        "accession (GSE.../STDS.../CNP...)"}
    prov = rec.get("raw_provenance", {})
    files = prov.get("files", [])
    if filename:
        files = [f for f in files if f.get("filename") == filename]
    out = [{"filename": f.get("filename"), **raw_store.fetch_url(f, expires_seconds)} for f in files]
    return {"found": True, "corpus_record_id": rec["corpus_record_id"],
            "accession": rec.get("source_document", {}).get("accession"),
            "policy": prov.get("policy"), "n_files": len(out), "files": out}


if FastMCP is not None:
    mcp = FastMCP("data-inamovible")

    @mcp.tool()
    def query_data_inamovible(query: str, k: int = 5):
        """Semantic GraphRAG search over the shared DATA INAMOVIBLE. Use to retrieve the best related
        information (niches, databases, datasets, curated knowledge) for a research question."""
        return _query(query, k)

    @mcp.tool()
    def resolve_identifier(key: str):
        """Resolve a gene symbol / ENSDARG / RefSeq NM_* / UniProt accession to the verified identifier
        (DATA INAMOVIBLE). Deterministic; never invents IDs."""
        return _resolve(key)

    @mcp.tool()
    def fetch_raw(key: str, filename: str = None):
        """Drill from the graph (the guide) to the RAW data that composes the truth, when a chunk or
        embedding is not enough. Pass a corpus_record_id (CORPUS-YYYY-NNNN) or an accession
        (GSE218068 / STDS0000057 / CNP0002220); optionally a filename. Returns retrievable URLs +
        sha256 (presigned MinIO for mirrored data; canonical source_url for public source-pointers)."""
        return _fetch_raw(key, filename)


if __name__ == "__main__":
    if FastMCP is None:
        # Dev smoke test without the SDK.
        import json
        print("MCP SDK not installed; dev smoke test of the tool backends:")
        print(json.dumps(_query("ocular cornea markers", 2), ensure_ascii=False)[:400])
        print(json.dumps(_resolve("foxc1b")))
        print(json.dumps(_resolve("NM_131729")))
        print(json.dumps(_fetch_raw("GSE218068"), ensure_ascii=False)[:500])
    else:
        mcp.run()
