# 0017 — Corpus-classifier as an operational mode of `domain-knowledge-curator`

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel
- **Affects:** `domain-knowledge-curator`, `rag_index/`, Test 1/3

## Context

The RAG back-end needs an agent that, when a scientific document arrives, knows how to categorize it
into the index — and, because the categorization will change, can also AUDIT an existing categorization
and propose improvements (the user's two requirements).

## Decision

Add the corpus-classifier as an **operational mode of `domain-knowledge-curator`** (not a new agent —
"prueba pequeño"; the curator already owns the knowledge base). It PROPOSES a categorization
(`{data_niche, scientific_domain_niche, verified entities, source_db, relevance}`) and can AUDIT an
existing record and propose a re-categorization. It **never writes** to `rag_index/corpus_manifest.json`
— proposals route to a HUMAN GATE (CLAUDE.md §7; read-only / human-gated mutable store). Scaffold:
`analysis/scripts/lib/corpus_classifier.py` (NO-SPEND, deterministic extension+keyword routing v1; a
semantic/LLM + embedding layer is added with the RAG backend, ADR-0015). It is NOT exempt from
MCP/Tool Universe verification + completeness checks (GWT v1.1 §3.3). Split into a dedicated
`corpus-classifier` agent only when corpus volume justifies it (cap discipline).

## Alternatives considered

- A new dedicated agent now. Rejected: cap pressure + prueba-pequeño; the curator's scope already
  covers KB maintenance.
- Auto-commit categorizations. Rejected: the store is human-gated mutable; auto-commit would re-introduce
  the silent-mutation risk.

## Consequences

- Easier: incoming docs get a categorization proposal + an audit path immediately.
- Care: deterministic v1 is shallow (extension+keyword); the semantic layer waits for the backend.

## Evidence

`rag_index/README.md`; `analysis/scripts/lib/corpus_classifier.py`; ADR-0015; the Nat Witt biomedic
niche-overlap feedback; GWT v1.1 plan §3.1.
