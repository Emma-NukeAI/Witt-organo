# `rag_index/graphrag/` — build the DATA INAMOVIBLE GraphRAG from scratch (ADR-0020)

The real, runnable build of the shared DATA INAMOVIBLE (RAG + graph + hybrid). Self-hosted on a
Docker-capable Linux server; NO paid services. Identifiers stay deterministic (`resolve_id`); this is
the semantic + graph layer. Dev/offline still works without any of this (the local sparse v1).

## Pieces

| File | What |
|---|---|
| `requirements.txt` | server deps: `neo4j` driver, `fastembed` (default 768-dim bge, ONNX, no torch); biomedical = `sentence-transformers` |
| `embeddings.py` | pluggable 768-dim embedder: `EMBED_MODEL=bge` (default) \| `biobert` \| `specter2` |
| `bootstrap.py` | create Neo4j constraints + the HNSW vector index (run once) |
| `ingest.py` | docs → embeddings → `(:Document)` + `(:Niche)/(:Database)/(:Entity)` + relationships (human-gated write) |
| `../mcp_server/server.py` | the agents' front door (`query_data_inamovible` + `resolve_identifier`); `RAG_BACKEND=neo4j` |
| `../deploy/` | docker-compose (Neo4j + Ollama) + the full runbook |

## Build sequence (on the server)

```bash
# 1. Neo4j up (Docker) — see ../deploy/
docker compose -f rag_index/deploy/docker-compose.neo4j.yml up -d

# 2. Python env + deps
python -m venv .venv && . .venv/bin/activate
pip install -r rag_index/graphrag/requirements.txt

# 3. Point at Neo4j (never commit the password)
export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD='<secret>'
export EMBED_MODEL=bge        # or biobert / specter2 for paper-heavy corpora

# 4. Schema + vector index (once)
python rag_index/graphrag/bootstrap.py

# 5. Ingest the curated corpus (human-gated; idempotent MERGE)
python rag_index/graphrag/ingest.py

# 6. Query — sanity check (sparse+dense hybrid via the same interface)
RAG_BACKEND=neo4j python analysis/scripts/lib/rag_backend.py query "ocular anterior segment markers"

# 7. Serve the MCP front door (agents consult this)
RAG_BACKEND=neo4j python rag_index/mcp_server/server.py      # needs `pip install mcp`
```

## Validation status

The non-Neo4j parts are dev-validated (sparse retrieval, graceful fallback, module syntax). The
Neo4j-dependent parts (bootstrap, ingest, the vector + graph query) get their **first-run validation on
the server** — run steps 4-6 and paste the output; we debug together. As the corpus grows (more
datasets/papers via the corpus-classifier, human-gated), re-run ingest (idempotent) + bump the version.

## Discipline (carried over)

Read-only by default; ingest is the only writer; categorization is human-gated (ADR-0017). Versioned +
retraíble (snapshot the Neo4j volume per corpus version). Entities bind to the verified store; unverified
IDs are quarantined, never minted. Secrets via env (CLAUDE.md §7). NO-SPEND.
