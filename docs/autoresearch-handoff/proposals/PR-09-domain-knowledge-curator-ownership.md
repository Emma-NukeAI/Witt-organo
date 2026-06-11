# PR-09 — `domain-knowledge-curator` owns the source-of-truth + RAG index + corpus-classifier

- **Status:** PARTIALLY APPLIED (GWT v1.1 Cycle 4): the corpus-classifier operational mode + the
  `rag_index/` structure are in the catalog + repo. The RAG/graph BACKEND is OPEN (ADR-0015).
- **Target:** `domain-knowledge-curator` block in `agent-catalog.md`.
- **Depends on:** PR-01 (resolver consulted), Cycle-1 source-of-truth, ADR-0015/0017.
- **Closes (partial):** C.15 (Test-5 flag attachment owner = curator side-effect).

## Decision

`domain-knowledge-curator` owns: (1) the source-of-truth interface (`resolve()/lookup_prior()`), (2) the
RAG index structure (`rag_index/`: 13 niches + 9 databases + corpus_manifest), and (3) the
corpus-classifier operational mode (categorize + audit, human-gated). Phase-I minimal: flat JSON +
deterministic classifier; upgrade to a real RAG/graph backend ONLY on bottleneck evidence (Magraner),
via the spike (ADR-0015) + a governance-proposal. The curator attaches the `EXPLORATORY-NOT-TEST-5`
flag on any cross-corpus run (closes C.15).

## Cycle status

- Applied: corpus-classifier mode (catalog), `rag_index/`, `corpus_classifier.py`, ADR-0015/0017.
- Deferred: the vector/graph backend (spike), embeddings, the semantic classifier layer — all gated on
  the OPEN backend decision + a corpus to benchmark.
