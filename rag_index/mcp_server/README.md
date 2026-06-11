# DATA INAMOVIBLE — MCP server (the agents' front door)

`server.py` is the single MCP front door to the shared DATA INAMOVIBLE GraphRAG (ADR-0020). The
project's agents (and anyone with the project) query it via two MCP tools:

- **`query_data_inamovible(query, k)`** — semantic GraphRAG retrieval (the best related info for a question).
- **`resolve_identifier(key)`** — deterministic verified-identifier resolve (symbol / ENSDARG / RefSeq / UniProt).

## Run

- **Dev / offline (now):** `python rag_index/mcp_server/server.py` — runs against the local sparse v1
  (`rag_backend` TfidfRetriever); no Neo4j needed. Without the MCP SDK it runs a smoke test of the tool
  backends. With the SDK (`pip install mcp`) it serves over stdio.
- **Rack / production:** set `RAG_BACKEND=neo4j` + `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` so the
  same tools front the hosted Neo4j GraphRAG (hybrid + rerank). See `rag_index/deploy/README.md`.

## Register it in a Claude/MCP client (so agents go consult it)

Add to the client's MCP config (alongside Tool Universe). stdio example:

```json
{
  "mcpServers": {
    "data-inamovible": {
      "command": "python",
      "args": ["rag_index/mcp_server/server.py"],
      "env": { "RAG_BACKEND": "neo4j", "NEO4J_URI": "bolt://<rack-host>:7687",
               "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "<secret>" }
    }
  }
}
```

For a shared/hosted deployment, run the server on the rack and expose it (stdio over SSH, or an HTTP/SSE
MCP transport); other people's project instances point their client at the rack endpoint. The repo
carries this instruction so every agent is told to consult the DATA INAMOVIBLE (a CLAUDE.md pointer +
this config). Secrets (NEO4J_PASSWORD) never go to git — use env/placeholders (CLAUDE.md §7).

## Why MCP

Matches the project's existing Tool Universe / MCP pattern: agents get a tool, not a bespoke client.
The two tools mirror the source-of-truth interface (semantic + deterministic), so an agent answering a
question first `resolve_identifier`s its gene IDs (no fabrication) and `query_data_inamovible`s for the
best related corpus — exactly the multi-agent access model in ADR-0020.
