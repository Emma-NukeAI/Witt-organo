# 0019 — RAG backend v1: flat, versioned, human-gated SPARSE retriever (dense/hybrid gated)

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel ("ya vayamos construyendo el rag backend")
- **Affects:** the DATA INAMOVIBLE corpus layer, `rag_index/`, the source-of-truth interface

## Context

The RAG backend was deliberately left OPEN (ADR-0015) pending a benchmark/corpus. Emmanuel directed
building it now so storage + classification of the incoming data (ZESTA, GSE218068, …) can proceed as
DATA INAMOVIBLE. The spike (§A) + the composite-audit (data-engineering lens) recommended a HYBRID
BM25+dense retriever, with the data-niche/modality axis as the routing key. NO-SPEND + "prueba pequeño"
constrain the first build (no paid services; minimize installs/model downloads on the user's machine).

## Decision

Build **v1 = a flat, versioned, human-gated SPARSE retriever** (`analysis/scripts/lib/rag_backend.py`,
TF-IDF/BM25-style via sklearn — already installed; zero new dependency, no model download). This is the
**permanent sparse half** of the recommended hybrid, not a throwaway. It is the SEMANTIC half of the
source-of-truth interface; `resolve_id.py` remains the DETERMINISTIC identifier resolver (the two are
deliberately separate — identifiers must never pass through a fuzzy/LLM/vector path).

**Storage (DATA INAMOVIBLE discipline):** the indexed corpus is `rag_index/index/documents.jsonl`
(human-readable, diffable, versioned, committed) + `manifest.json`. The TF-IDF matrix is built
in-memory at query time at this scale; persisting vectors is the dense-era optimization. Read-only by
default; only `build_index()` writes, only from already-curated sources (niches, databases,
corpus_manifest). v1 indexes 25 documents (13 niches + 10 databases + 2 datasets) and grows as the
corpus-classifier ingests more (human-gated).

**Dense / hybrid is the next gated step** (ADR-0015 stays open for it): a dense backend
(Chroma or LanceDB + a local embedding model — sentence-transformers/torch, or fastembed/ONNX ~150MB,
or Ollama) plugs in behind the same `Retriever` interface (`TfidfRetriever` now; `DenseRetriever`
later). Triggered by a bottleneck (sparse recall insufficient) + an explicit install decision.

## Alternatives considered

- **Dense vector store now (Chroma/LanceDB + embeddings).** Deferred: requires a heavier install +
  model download on the user's machine and a corpus large enough to benefit; the sparse layer is
  needed anyway (it's the hybrid's sparse half) and is buildable with zero install.
- **Pure substring (the prior lookup_prior).** Insufficient: no ranking, no multi-term relevance.
- **A 14th-niche / new structure.** N/A — this is the retrieval layer, not a taxonomy change.

## Consequences

- Easier: a working, queryable, versioned, committed knowledge index over the DATA INAMOVIBLE — usable
  immediately; corpus-classifier feeds it; the dense upgrade is a drop-in behind the interface.
- Care: sparse retrieval is keyword-driven; semantic paraphrase recall is limited until the dense half
  lands. Index is rebuilt (not incrementally updated) at this scale.

## Evidence

GWT v1.1 plan §A (architecture spike); ADR-0015 (backend OPEN); the composite-audit data-engineering
lens (hybrid BM25+dense); `analysis/scripts/lib/rag_backend.py`; `rag_index/index/`.
