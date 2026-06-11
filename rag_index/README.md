# `rag_index/` — the RAG back-end index (GWT v1.1 Cycle 4, structure-first)

This is the **initial structure** of the zebrafish-biomedicine RAG back-end the project will grow.
Per the user's direction (2026-06-11): start by **categorizing and indexing** from the reference
material; the categorization will change as sample/test documents arrive, so this is two things at
once — (1) an initial **structure**, and (2) an **agent** that, on receiving a document, knows how to
categorize it OR can **audit** an existing categorization and propose improvements.

**The backend technology is OPEN** (flat JSON now; FAISS / Neo4j / graphify / hybrid later — plan §A,
ADR-0015). What is built now is the **index structure + the classifier contract**, behind the stable
`resolve()/lookup_prior()` interface so the backend can change without touching callers.

## What lives here

- `niches.json` — the **13 RAG data-niches** (from `Indices_nichos.pdf`): the kind of DATA/ARTIFACT,
  with file types + purpose. This is an artifact-type axis, **distinct** from PROJECT_SCOPE's 6
  scientific-domain niches. A corpus item is tagged on BOTH axes.
- `databases.json` — the **9 authoritative sources** (from `Bases de datos.pdf`: ZFIN, DanioCODE,
  Reactome, GEO, UCSC Cell Browser, STRING, IntAct, BioGRID, Ensembl), each mapped to the niches it feeds.
- `corpus_manifest.json` — the catalog of corpus records + the cataloged-record schema (2 approved:
  ZESTA + GSE218068). The `corpus-classifier` proposes entries; a **human gate** approves before commit.
- `niche_database_crosswalk.json` — 10 DBs × 13 niches feed map (declared + proposed, provenance-tagged).
- `interaction_table.json` — RN10 master interaction table (Source→Target→Signal→Window), first-class.
- `index/` — the **RAG retrieval index** (`documents.jsonl` + `manifest.json`), built by
  `analysis/scripts/lib/rag_backend.py` (ADR-0019).

## The retrieval backend (ADR-0019)

The source-of-truth interface has two halves:
- **Deterministic** — `analysis/scripts/lib/resolve_id.py` `resolve(symbol|ENSDARG|RefSeq|UniProt)` →
  exact verified identifier. IDs never pass through a fuzzy/vector path.
- **Semantic** — `analysis/scripts/lib/rag_backend.py` `query(text, k)` → ranked corpus documents
  (v1 = flat, versioned, human-gated **sparse** TF-IDF/BM25, sklearn, NO-SPEND; the permanent sparse
  half of the recommended hybrid). A **dense** backend (Chroma/LanceDB + local embeddings) plugs in
  behind the same `Retriever` interface — gated on a bottleneck + an install decision (ADR-0015 open).

Build/query:  `python analysis/scripts/lib/rag_backend.py build` · `… query "<text>"`.

## How the three stores relate (kept separate — the user's requirement)

| Store | What | Where |
|---|---|---|
| **DATA INAMOVIBLE** (identifiers) | verified gene IDs / accessions, deterministic | `analysis/outputs/verified_identifiers.json` |
| **RAG corpus index** (this) | scientific corpus categorized into 13 niches × 9 sources | `rag_index/` |
| **Outputs / theses** | results/theses agents produce | `SIMULATION_OUTPUTS_DB/`, `reports/` |

## The classifier (corpus-classifier — extends `domain-knowledge-curator`)

On a new document it proposes `{data_niche, scientific_domain_niche, entities (verified IDs),
source_db, relevance}` and routes to a **human gate** before writing to `corpus_manifest.json`. It can
also **audit** an existing categorization and propose a re-categorization (the taxonomy is revisable —
e.g., the team biomedic argued ocular should not be separate from biophysics; see
`evaluation/held_out_set_v1.json` Q30). Scaffold: `analysis/scripts/lib/corpus_classifier.py`
(NO-SPEND, deterministic file-type + keyword routing; an LLM/semantic layer is added with the backend).

## Discipline

- **Read-only by default; human-gated mutable** (like the DATA INAMOVIBLE): the classifier proposes,
  a human approves, changes are versioned (bump `index_version` / `manifest_version`).
- **Agents are NOT exempt from MCP/Tool Universe** even when this index has data (GWT v1.1 §3.3):
  verify + complement + check completeness; a hole → `gap_flag`.
- **Provenance tagged:** STRING (predictive) vs IntAct/BioGRID (physical/genetic) — prefer physical.
