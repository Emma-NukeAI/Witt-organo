# ADR-0042 — First RN3 corpus record (CORPUS-2026-0004, human-gated ingest) + relational genotype-phenotype data places under RN11

- **Status:** Accepted — **human gate AUTHORIZED by Emmanuel, 2026-07-21** (ingest: "adelante", after the exact node/edge write-spec was stated before any write; taxonomy: "RN11 primario") per founder directive 2026-06-13 + CLAUDE.md §7 / ADR-0022.
- **Relates:** ADR-0020 (hosted Neo4j GraphRAG), ADR-0021 (ingest service + contributor workflow), ADR-0018 (niche taxonomy KEEP-AS-IS, human-gated mutable), ADR-0029/0035/0041 (prior human-gated DI adds/re-ingests), ADR-0026 (cp1252 hardening sweep — extended here to the CLI). Motivated by processing MITAD_B's A1 stress bank (ZF-S1..S12) and the founder request to test the ingest / grow the corpus / validate MITAD_A end-to-end.
- **Affects:** the hosted Neo4j graph (embedding + index layers) + `rag_index/corpus_manifest.json` + `rag_index/index/documents.jsonl`. **MUTATION (ADD-only, MERGE — never deletes)** for the ingest; a **taxonomy-INTERPRETATION ruling** (no `niches.json` change) for the placement.

## Context

Processing B's stress bank as MITAD_A (scope-gate + grounding + acquisition ranking) passed a 3-auditor composite gate (1 CONFIRMED, 2 REVISE, 0 REFUTED; corrections in `analysis/outputs/S-bank_composite_audit_outcome_20260721.json`). Two DI-governance decisions followed:

1. **Test the ingest / grow the corpus.** The most ready, lowest-risk growth candidate was the ZF-G8 RN3 record: **measured** Nodal/BMP trajectories from ZESTA (P1) + a **verified** differential-diffusivity citation (Müller 2012, PMID 22499809, §7.9 raw-cached, P2). The fitted `.bngl` kinetic model (P3) is MITAD_B's generation deliverable and is **not** part of this record — it will enter later as a MERGE update. The record therefore does **not** claim a validated model.

2. **Where does S4's relational data live?** ZF-S4 (penetrance variance decomposition) needs a relational substrate — mutant→phenotype (ZFIN) + genetic-interaction (BioGRID) + isogenic variance. MITAD_B mis-mapped this to RN10/11/12 (the recurring "reverse-engineer niche from feeder-DB name" error, cf. ZF-G12). The authoritative `niches.json` (deliberately frozen since ADR-0018, after a composite-audit rejected a niche merge) has no clean home for relational genotype-phenotype data.

## Decision

**(a) Ingest CORPUS-2026-0004 (RN3, first signaling-niche record).** Human-gated `add_dataset`→`pending_review`→`approve_dataset.py CORPUS-2026-0004 --by Emmanuel`→`ingest.py` (single canonical writer, `EMBED_MODEL=openai`/1536-dim — same model, no halt). 15/15 markers bound via `resolve_id` (0 NOT_FOUND, 0 minted). `data_niche: RN3` primary (+RN1 secondary), `scientific_domain: N4` (+N3).

**(b) Relational genotype-phenotype data places under RN11, NO new niche.** Per the founder principle ("prueba pequeño antes de armar bien") and the deliberately-frozen taxonomy: a ZFIN mutant→phenotype table IS a set of **curated claims** (each row = "genotype G → phenotype P, penetrance %"), which is exactly RN11 ("Claims curados de literatura biológica"). Genetic-interaction edges (BioGRID, an already-registered feeder of RN3/RN12) are corroborating edges/entities, not a separate niche. Isogenic variance → RN1/RN9. **RN12 explicitly does NOT apply** (it holds *generated* perturbation designs via causal-pruner, not observed ZFIN data). Opening a first-class relational niche (RN14) is **deferred** until S4 is selected and the relational structure proves load-bearing — at which point it requires its own ADR + composite-audit (the ADR-0018 bar).

**(c) cp1252 hardening of the CLI.** `rag_index/mcp_server/cli.py` crashed AFTER a successful retrieval when printing the "✓" glyph on a Windows cp1252 console. Fixed at the root (`sys.stdout/stderr.reconfigure(encoding="utf-8")`), extending the ADR-0026 sweep.

## Consequences

- **Graph delta (live, verified):** `Entity` 44 → **59** (+15 Nodal/BMP markers not previously in the graph), `MENTIONS` 88 → **103** (+15), RN3 dataset docs 0 → **1**, `+1 Document` CORPUS-2026-0004 (openai/1536-dim embedding). `Niche` 13 unchanged. ADD-only; no deletion. Sparse `documents.jsonl` rebuilt in sync (4 datasets).
- **Retrievable & non-degraded:** a dense GraphRAG query for "Nodal Lefty BMP reaction-diffusion kinetics" returns CORPUS-2026-0004 as **hit #1, score 0.848** (not sparse-degraded). MITAD_A validated end-to-end: propose → human gate → ingest → retrievable.
- **RN11 gains a precedent:** future relational curated-claim tables (mutant→phenotype, phenotype ontologies) route to RN11 with the relational-structure limitation carried as a `gap_flag`. The `PROPOSAL_S4_acquisition_path_DRAFT` taxonomy question is RESOLVED (RN11 primary).
- **Deferred:** the fitted `.bngl` (MITAD_B) enters CORPUS-2026-0004 as a MERGE update; a first-class relational niche remains an open, evidence-gated future proposal.
- **Doc ripple:** corpus count 3 → **4** records; first RN3-niche coverage. CLAUDE.md §12 to sync on next docs pass.
- **Reversible** only via a *gated prune proposal*, never automatic (ADR-0022).

## Verification (read-only, post-ingest, live)

- `node_counts` Entity 59 (44→59), Document contains `CORPUS-2026-0004`; `rel_counts` MENTIONS 103 (88→103); RN3 dataset docs 1.
- `ndr1` Entity bound to `ENSDARG00000057096` (concordant with store).
- CLI query exit 0 (no cp1252 crash) with `PYTHONUTF8` unset; top hit CORPUS-2026-0004 @ 0.848, semantic (not degraded).
