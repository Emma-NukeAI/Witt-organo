"""
liveness.py — NO-SPEND liveness probe for the hosted DATA INAMOVIBLE (GWT v1.1).

Verifies the live infra is reachable + populated WITHOUT spending. It runs only FREE operations:
  - a Neo4j count / vector-index Cypher  (no embedding)
  - the deterministic resolve_id          (local file read, zero network)
  - fetch_raw URL resolution              (source-pointer / presign; no OpenAI)

It deliberately does NOT call query_data_inamovible — that embeds the query via OpenAI (paid).
(The repo's documented smoke `python rag_index/mcp_server/server.py` DOES embed when secrets are
present, i.e. it spends; this probe is the no-spend alternative.)

Run:  ./.venv/Scripts/python.exe rag_index/graphrag/liveness.py
      (self-loads .secrets/deploy.env if NEO4J_URI is not already in the environment)
"""
import os
import sys
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "mcp_server"))

# single-host convenience: load deploy vars from the gitignored secrets file if not already set
_env = ROOT / ".secrets" / "deploy.env"
if not os.environ.get("NEO4J_URI") and _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import server as mcp  # the MCP backends: _resolve / _fetch_raw (free); _query NOT called here


def neo4j_liveness():
    """Free Cypher: node/relationship counts by label/type + vector index state. No embedding."""
    from neo4j import GraphDatabase
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ["NEO4J_PASSWORD"]
    drv = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=15)
    out = {"uri_host": uri.split("@")[-1]}
    try:
        drv.verify_connectivity()
        with drv.session() as s:
            out["nodes_total"] = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            out["by_label"] = [{"label": r["label"], "count": r["c"]} for r in s.run(
                "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS c ORDER BY c DESC")]
            out["rels_total"] = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            out["rel_types"] = [{"type": r["t"], "count": r["c"]} for r in s.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC")]
            idx = []
            for r in s.run("SHOW INDEXES YIELD name, type, state, entityType, labelsOrTypes, properties"):
                if str(r["type"]).upper().startswith("VECTOR"):
                    idx.append({"name": r["name"], "state": r["state"],
                                "on": r["labelsOrTypes"], "props": r["properties"]})
            out["vector_indexes"] = idx
        out["reachable"] = True
    finally:
        drv.close()
    return out


def main():
    report = {"probe": "DATA INAMOVIBLE liveness (NO-SPEND)", "store_version": None}

    # 1) Neo4j — the real liveness signal (the graph lives on the rack)
    try:
        report["neo4j"] = neo4j_liveness()
    except Exception as e:
        report["neo4j"] = {"reachable": False, "error": f"{type(e).__name__}: {e}"}

    # 2) deterministic resolve (anti-fabrication) — local, free
    from lib import resolve_id
    report["store_version"] = resolve_id.store_version()
    report["resolve"] = {k: mcp._resolve(k) for k in
                         ("wt1a", "pax2a", "ENSDARG00000031420", "clcnkb", "made_up_gene")}

    # 3) fetch_raw drill-down — free (source-pointer URL + sha256)
    report["fetch_raw"] = {k: mcp._fetch_raw(k) for k in ("GSE218068", "CORPUS-2026-0001")}

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
