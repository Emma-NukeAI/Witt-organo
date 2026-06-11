# 0020 — Hosted GraphRAG architecture for the DATA INAMOVIBLE (self-host, Neo4j + graphify, MCP)

- **Date:** 2026-06-11
- **Status:** accepted (architecture); deployment to the rack is the next execution step
- **Decided by:** Emmanuel
- **Affects:** the DATA INAMOVIBLE corpus layer, the source-of-truth interface, agent access, `rag_index/`
- **Supersedes the "OPEN" backend of ADR-0015 for the SEMANTIC layer; identifiers stay flat JSON (resolve_id).**

## Context

The DATA INAMOVIBLE must become **shared/hosted (not local)**: consumable by anyone who has the
project, and queried by the project's agents to retrieve the best related information for their
questions — anticipating a large corpus. Emmanuel chose: **self-host on the project's own rack**
(NO-SPEND, data under control, fits confidential Witt data); **embedding-RAG + graph (GraphRAG)**;
**biomedical embeddings**; **MCP access**. A review of `NirDiamant/RAG_Techniques` (42+ techniques)
informed the retrieval pipeline.

## Decision

**Topology — self-hosted GraphRAG on the rack.** The DATA INAMOVIBLE runs on the project's own
hardware; agents/people query it over the network. No paid cloud (NO-SPEND; confidential data stays in
your control). Interface-stable so a future cloud migration needs no caller changes (ADR-0015 spirit).

**Engine — Neo4j (graph + native vector index) populated by graphify.** One engine for BOTH embeddings
(HNSW vector index, Neo4j 5.x) and relationships (Cypher, multi-hop). `graphify` (tree-sitter + Ollama,
offline) builds the entity/relationship graph from documents and loads Neo4j. This is "embedding RAG +
graph" in one place — the user's first choice, confirmed by the review.

**Embeddings — biomedical + general, self-hosted.** SPECTER2 / BioBERT-style for papers/literature
(domain recall) + a general model (bge-large / nomic) for metadata/structure. Served self-hosted
(Ollama or a small embedding service on the rack). No paid embedding API; confidential text never leaves.

**Access — an MCP server fronting the GraphRAG.** Agents get an MCP tool (e.g. `query_data_inamovible`);
the repo carries the instruction to point there (mcp-config + a CLAUDE.md pointer). Fits the project's
existing Tool Universe / MCP pattern. People can also hit it; the MCP server is the single front door.

**Retrieval pipeline (informed by `RAG_Techniques`).** For "many agents, much info, best related info":
1. **Hybrid fusion** — sparse (TF-IDF/BM25, the v1 already built, ADR-0019) + dense (Neo4j vector) fused.
2. **Graph expansion** — multi-hop over relationships (Cypher) to pull related entities/claims.
3. **Reranking** — a cross-encoder (biomedical) re-scores the fused candidates for precision.
4. **Query transformation / routing** — rewrite / step-back / sub-query + niche-routing (corpus-classifier).
5. **Corrective / Self-RAG relevance check** — verify retrieved context is on-topic; fall back / flag if
   not (ties to the anti-fabrication gate + RIL discipline).
6. **RAPTOR / hierarchical summaries** — added when the corpus is large (recursive clustering + summaries).
7. **Eval** — RAGAS / DeepEval on a held-out query set (ties to the noise-probe / Test-3 discipline).

**Identifiers stay deterministic.** `resolve_id` (flat JSON: symbol/ENSDARG/RefSeq/UniProt) remains the
exact identifier resolver; the GraphRAG is the semantic layer. The two compose; IDs never pass through
the vector/LLM path.

**Dev/offline fallback.** The local sparse retriever (`rag_backend.py` TfidfRetriever, ADR-0019) stays
as the dev/offline path behind the same `Retriever` interface, so development works without the rack.

## Alternatives considered

- **Managed cloud (Aura/Qdrant Cloud).** Rejected: paid (NO-SPEND) + confidential data leaves control.
- **Qdrant (vectors) + Neo4j (graph) as two engines.** Deferred: more pieces to operate; Neo4j's native
  vector index gives one-engine GraphRAG now; revisit if vector-query concurrency becomes a bottleneck.
- **Microsoft GraphRAG framework.** Considered (community summaries are strong for global queries) — fold
  its community-summary idea into the RAPTOR/hierarchical step rather than adopting the whole framework.
- **General-only embeddings.** Rejected: a biomedical corpus benefits from SPECTER2/BioBERT recall.

## Consequences

- Easier: a shared, queryable GraphRAG the agents consult via one MCP tool; relationships + semantics in
  one engine; everything self-hosted + NO-SPEND.
- Care/ownership: the rack must run Neo4j + the embedding service + the MCP server (backups, uptime are
  yours). Deployment recipe + runbook provided (`rag_index/deploy/`). Heavy model downloads happen on
  the rack, not in dev.

## Evidence

GWT v1.1 plan §A; ADR-0015 (backend open) / ADR-0019 (sparse v1); the user's 4 architecture decisions
(2026-06-11); `NirDiamant/RAG_Techniques` review (hybrid, reranking, query-transform, corrective-RAG,
RAPTOR, RAGAS); `rag_index/deploy/` (recipe), `rag_index/mcp_server/` (front door).
