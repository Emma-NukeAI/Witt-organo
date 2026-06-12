# Contributing data to the DATA INAMOVIBLE (the shared source of truth)

The DATA INAMOVIBLE is the project's shared, verified knowledge base: a **Neo4j GraphRAG** (the guide:
documents + chunks + embeddings + verified entities) backed by a **raw store** (the full files an agent
drills into when a chunk isn't enough). This page is for a teammate who wants to **add information** to it.

Two ways to contribute — pick by where you are:

- **A) Repo-side (today, this page).** You have the repo + can run Python. Two commands + a human gate.
- **B) Hosted (no repo/creds).** Submit through the hosted ingestion service (see
  `rag_index/ingest_service/README.md`). Same human gate; you don't touch Neo4j/MinIO. *(rolling out.)*

Everything is **human-gated**: nothing enters the source of truth without a person approving it. Identifiers
are **never minted** — only gene symbols already in the verified store (`resolve_id`) become entities;
unknown ones are flagged, not invented (CLAUDE.md §7).

---

## A) Repo-side contribution

### One-time setup
```bash
python -m venv .venv && . .venv/Scripts/activate        # (Linux/macOS: .venv/bin/activate)
pip install -r rag_index/graphrag/requirements.txt
# .secrets/deploy.env (gitignored) — ask the project owner for the values:
#   NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD     (to ingest into the graph)
#   EMBED_MODEL=openai / OPENAI_API_KEY         (to embed)
#   MINIO_* (only if you mirror PRIVATE files)
```

### Step 1 — propose a dataset (no writes to the truth yet)
```bash
set -a; . .secrets/deploy.env; set +a
# public dataset (recorded as a source-pointer: URL + sha256; --download to fetch+hash+extract entities):
./.venv/Scripts/python.exe analysis/scripts/lib/add_dataset.py \
    --name "Zebrafish X atlas" --accession GSE123456 --source-db GEO_NCBI \
    --url https://ftp.ncbi.nlm.nih.gov/.../features.tsv.gz --download --niche RN1 --domain N3

# private/derived local file (mirrored into MinIO, not a public source):
./.venv/Scripts/python.exe analysis/scripts/lib/add_dataset.py \
    --name "Internal proteomics run" --source-db local --file ./data/run1.csv --private --niche RN4
```
This writes a **PROPOSED** record (`approval_chain: pending_review`) to `rag_index/corpus_manifest.json`
with: the `raw_ref` (provenance to raw), the proposed niche (classifier), and the **verified entities**
(only store-known symbols; the rest are flagged). It does **not** ingest.

### Step 2 — human gate: review, then approve + ingest
Review the proposed record in `rag_index/corpus_manifest.json` (niche placement, entities, gap_flags).
When it's right:
```bash
set -a; . .secrets/deploy.env; set +a
./.venv/Scripts/python.exe analysis/scripts/lib/approve_dataset.py CORPUS-2026-NNNN --by "<your name>"
```
This flips the gate to `approved`, then ingests into Neo4j (idempotent). Commit the manifest change.

### Text documents (papers/PDFs)
Chunk first (`chunk_document.py`), then the chunks become retrievable nodes that point back to the raw PDF:
```bash
python analysis/scripts/lib/chunk_document.py ./papers/smith2024.pdf --attach CORPUS-2026-NNNN
```

---

## The hybrid raw policy (where the bytes live)
- **Public/reproducible** (GEO, CNGB, Ensembl): we store a **source-pointer** (canonical URL + `sha256`),
  not the bytes. `fetch_raw` returns the URL; re-download + verify the checksum.
- **Private/derived/non-reproducible**: mirrored into **MinIO** (`--private`); `fetch_raw` returns a
  time-limited presigned URL.

## Drilling from the graph to the raw
Any agent (or you) can go from a chunk to the full raw data:
```
resolve_identifier / query_data_inamovible   -> find the record / accession
fetch_raw("GSE218068")                        -> raw download URLs + sha256
```

## Rules (non-negotiable — CLAUDE.md §7)
- Human gate to write. No identifier minted from memory. Raw responses cached/verified before use.
- Secrets only in `.secrets/deploy.env` (gitignored) — never commit credentials.
