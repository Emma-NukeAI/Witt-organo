# Finding — Corpus feasibility test ("la prueba"): ZESTA + GSE218068

- **Date:** 2026-06-11
- **Status:** Feasibility CONFIRMED. First two real corpus records cataloged (proposals, human-gated). Three actionable findings surfaced. NO-SPEND (153 KB download; the 4.8 GB ZESTA NOT downloaded — gated).
- **Method:** Web investigation (5 sources) + `corpus-classifier` categorization + `resolve_id` entity gate on real dataset features.

## The two sources (open access)

| | ZESTA | GSE218068 |
|---|---|---|
| What | Zebrafish Embryogenesis **Spatiotemporal** Transcriptomic Atlas (Stereo-seq spatial + scRNA) | Temporal scRNA atlas of zebrafish **anterior segment** (trabecular meshwork / annular ligament) |
| Stages | **3, 5, 10, 12, 18, 24 hpf** (whole embryo) | **48, 72, 96, 120, 144 hpf** (foxc1b:GFP-sorted) |
| Scale | 91 sections, 152,977 spatial spots | 5 timepoints, 10x |
| Files | 12 × `.h5ad` (~4.8 GB), open via ftp.cngb.org | 10x outs (~40 MB) + RAW.tar (44 MB) |
| Host / DB | **CNGB STOmics** (new source) | GEO NCBI |
| Paper | Liu et al., Dev Cell 2022, 10.1016/j.devcel.2022.04.009 | PMID 37024546 |
| Domain | N3 embryology (3-24 hpf = pre-corneal window) | **N5 ocular** (Test-5 cross-field) |

The two are **complementary**: ZESTA = the early whole-embryo window (matches our pronephros + held-out work, adds a spatial dimension); GSE218068 = the late ocular window.

## Three actionable findings (the test surfaced real improvements — the "recommend where to change" loop on real data)

1. **The anti-fabrication entity gate WORKS on real data.** Running GSE218068's 15,404 gene features through `resolve_id`: `foxc1b` (the dataset's defining gene), `pitx2`, `prox1a` → correctly **NOT_FOUND / UNVERIFIED → quarantine** (NOT minted from memory). They are ocular markers absent from our pronephros-centric 32-record store. The gate caught the gap exactly as designed.
2. **ID-namespace mismatch (important).** GSE218068 features use **RefSeq (NM_*)**, not Ensembl (ENSDARG). Symbols match (foxc1a, pax2a, wt1a, cdh17, gata3, tbx2b all present) but the ID systems differ → binding to the verified store needs a **RefSeq↔Ensembl cross-map** (resolvable NO-SPEND via Ensembl xref lookups, gated). ZESTA uses Ensembl, so it binds directly.
3. **The verified store needs ocular markers.** foxc1b/pitx2/prox1a (+ likely krt12, col1a1a/b, aldh3a1) must be curated into the store (Ensembl lookup + raw-cache + human gate) before the N5 work — a clean, scoped curation task.

## High-value connection: GSE218068 closes Nat Witt GAP-5

The 2026-05-21 cornea/N5 session handoff named its **primary blocker** as "acquire a 72–120 hpf zebrafish cornea-enriched scRNA-seq dataset (GAP-5)." **GSE218068 (48–144 hpf, foxc1b:GFP anterior segment) is exactly that dataset** — and foxc1b:GFP is the biomedic's own line. This unblocks the late-stage corneal Tier-assignment work that the handoff deferred.

## What was done (NO-SPEND) vs gated

- **Done:** categorized both datasets via `corpus_classifier`; downloaded + cached GSE218068 features (153 KB, `mcp_cache/raw_geo_GSE218068_features_20260611.tsv.gz`, §7.9); ran the entity gate on real features; cataloged 2 corpus records (`rag_index/corpus_manifest.json`, `pending_review`); added CNGB STOmics to the DB registry + crosswalk; enriched the classifier keywords (stereo-seq / spatial-transcriptomics / CNGB).
- **Gated (next steps, need approval):** download the ZESTA 4.8 GB `.h5ad` (bandwidth/compute) + read with scanpy/anndata; build the RefSeq↔Ensembl cross-map; curate ocular markers into the verified store; decide the RAG backend (still OPEN) before vectorizing.

## Substrate evidence

Test 1 (multi-source reasoning + entity gate on real data), Test 3 (first real corpus population; the test surfaced 3 improvements), Test 5 (the ocular dataset supports cross-field). Claim record:
`substrate_calibration/records/claim_20260611_120000_corpus-feasibility-zesta.json`. HTML:
`reports/corpus-feasibility-zesta-gse218068-v1.html`.
