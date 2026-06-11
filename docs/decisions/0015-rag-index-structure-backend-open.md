# 0015 — RAG index structure-first; backend OPEN

- **Date:** 2026-06-11
- **Status:** accepted (structure); backend deferred to a spike
- **Decided by:** Emmanuel
- **Affects:** the RAG back-end (DATA INAMOVIBLE corpus layer), `domain-knowledge-curator`, Cycle 4

## Context

The RAG back-end serves a scientific corpus that must be analyzed, categorized, and indexed. The user
provided the reference material to START the categorization (`Indices_nichos.pdf` = 13 data-niches;
`Bases de datos.pdf` = 9 authoritative sources) and asked to build the **initial structure** now, with
the understanding that the categorization will change as sample documents arrive. The backend
technology (FAISS / Neo4j / graphify / hybrid) was explicitly left OPEN ("seguir explorando").

## Decision

Build the **index structure now, decide the backend later**. `rag_index/` holds: `niches.json` (the 13
RAG data-niches with file types + purpose), `databases.json` (the 9 sources mapped to the niches they
feed), and `corpus_manifest.json` (the cataloged-record schema + an empty seed). The structure is
**read-only by default, human-gated mutable, and revisable** (the taxonomy is expected to change). The
backend remains a flat-JSON index now, behind the stable `resolve()/lookup_prior()` interface, so
FAISS/Neo4j/graphify/hybrid can plug in later (the spike, deferred) without changing callers.

The RAG data-niche axis (13) is **distinct** from PROJECT_SCOPE's scientific-domain niches (6); a
corpus item is tagged on both.

## Alternatives considered

- Pick a backend now (Chroma/LanceDB) and build the real vector store. Rejected: the user chose to keep
  the backend open; a corpus to benchmark on does not exist yet.
- Wait for the backend before any index. Rejected: the user explicitly wanted the categorization/index
  started now from the reference material.

## Consequences

- Easier: incoming sample docs can be categorized immediately against a real index; the backend choice
  is decoupled and reversible.
- Care: the 13-niche taxonomy is provisional (biomedic feedback that ocular ⊄ biophysics); the classifier
  can audit + propose re-categorization, human-gated.

## Evidence

`docs/autoresearch-handoff/` (Indices_nichos.pdf, Bases de datos.pdf); `rag_index/`; plan §A; the
biomedic interaction (Nat Witt P2 niche-overlap feedback); GWT v1.1 plan §3-bis.
