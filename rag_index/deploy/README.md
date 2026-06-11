# Deploy the hosted GraphRAG DATA INAMOVIBLE on the rack (ADR-0020) — runbook

Self-hosted, NO paid services, confidential data under your control. The agents query it via the MCP
server (`rag_index/mcp_server/`). Everything below runs on **your rack**; this repo carries the code +
recipe (model downloads + the live DB happen on the rack, not in dev).

## Components

| Component | What | How |
|---|---|---|
| **Neo4j 5.x (Community)** | graph + native HNSW vector index — the GraphRAG store | `docker compose -f docker-compose.neo4j.yml up -d` |
| **Embedding service** | SPECTER2/BioBERT (papers) + general (bge/nomic) — self-hosted | Ollama (general) in the compose; SPECTER2/BioBERT via a transformers/ONNX batch at ingestion |
| **graphify** | builds the entity/relationship graph from docs → Neo4j | `pipx install graphify` (Ollama backend, offline); push Cypher/CSV to `./import` |
| **MCP server** | the agents' front door (`query_data_inamovible`, `resolve_identifier`) | `RAG_BACKEND=neo4j NEO4J_URI=bolt://localhost:7687 python rag_index/mcp_server/server.py` |

## Steps

1. **Bring up Neo4j + Ollama:** set a real password in `.env` (`NEO4J_AUTH=neo4j/<secret>`; never commit
   it), then `docker compose -f rag_index/deploy/docker-compose.neo4j.yml up -d`. Browser at `:7474`.
2. **Create the vector index** (once), e.g. dimension 768 for SPECTER2 / general bge:
   ```cypher
   CREATE VECTOR INDEX doc_embeddings IF NOT EXISTS
   FOR (d:Document) ON (d.embedding)
   OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } };
   ```
3. **Ingest the corpus (human-gated):** for each approved `rag_index/corpus_manifest.json` record + the
   niches/databases knowledge: parse → chunk (section-first) → embed (SPECTER2 for papers, general
   otherwise) → write `(:Document {id, text, embedding, data_niche, scientific_domain, source_db, …})`
   and relationships (gene→pathway→tissue→window; doc→entity; the RN10 interaction table) via graphify +
   Cypher. Entities bind to the verified store (resolve_id); UNVERIFIED IDs are quarantined, not minted.
4. **Pull a general embedding model:** `docker exec data-inamovible-ollama ollama pull nomic-embed-text`
   (or `bge-large`). Install SPECTER2/BioBERT in the ingestion env for paper embeddings.
5. **Run the MCP server** with `RAG_BACKEND=neo4j` + `NEO4J_URI/USER/PASSWORD` so the same tools front
   the GraphRAG (hybrid sparse+dense fusion → graph expansion → cross-encoder rerank, per ADR-0020).
6. **Point the agents at it:** register the MCP server in each project instance's client config
   (`rag_index/mcp_server/README.md`); add a CLAUDE.md pointer instructing agents to consult the
   DATA INAMOVIBLE for research questions.

## Discipline (carried over)

- **Read-only by default; human-gated writes.** Ingestion is the only writer; new corpus/categorization
  is approved (corpus-classifier proposes → human gate, ADR-0017).
- **Versioned + retraíble.** Snapshot the Neo4j volume on each corpus version; keep `documents.jsonl` +
  `manifest.json` as the human-readable, diffable source of the index.
- **Secrets never to git** (NEO4J_PASSWORD via env/.env). **No paid services** (NO-SPEND).
- **Dev/offline still works** without the rack: unset `RAG_BACKEND` → the local sparse v1 (TfidfRetriever).

## Eval (next)

RAGAS / DeepEval over `evaluation/held_out_set_v1.json` (run the queries through the MCP server, score
recall/faithfulness) — ties to the noise-probe / Test-3 discipline (RIL_PROGRAM §3).
