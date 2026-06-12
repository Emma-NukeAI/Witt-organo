# ADR-0021 — Raw store + provenance-to-raw (MinIO, hybrid policy)

- **Status:** Accepted (Emmanuel, 2026-06-12)
- **Supersedes/relates:** ADR-0020 (hosted GraphRAG on Neo4j). This adds the RAW backing layer beneath it.

## Context

The DATA INAMOVIBLE graph (Neo4j, ADR-0020) stores documents/chunks + embeddings as a **guide/index**.
But an agent (or a person) sometimes needs more than a chunk: it must drill down to the **raw data that
composes the truth** (the full `.h5ad`, count matrix, PDF, etc.). The graph had no path back to raw, and
the only copies of downloaded raw (e.g., the 5.4 GB ZESTA atlas) lived on one workstation under
`mcp_cache/` (gitignored) — not durable, not shareable. Teammates also need to contribute raw data to the
source of truth without holding write credentials or running scripts.

## Decision

1. **Provenance-to-raw is first-class.** Every graph node (document/chunk/dataset record) carries a
   `raw_ref`. A new MCP tool **`fetch_raw(key, filename?)`** resolves a `corpus_record_id`/accession to
   retrievable raw URLs + `sha256`. Lib: `analysis/scripts/lib/raw_store.py`.

2. **Durable raw store = self-hosted MinIO** (S3-compatible) as a Docker-Compose stack on Dokploy, next
   to Neo4j, on a **dedicated volume**. Free, self-hosted, S3 API; agents read via time-limited
   **presigned URLs**.

3. **Hybrid storage policy** (the cost/trust trade-off):
   - **Public / reproducible** sources (ZESTA@CNGB, GSE*@GEO, Ensembl) → **source-pointer**: record the
     canonical `source_url` + `sha256` (+ bytes); do **not** mirror the bytes. `fetch_raw` returns the
     source URL; integrity is checked against the stored `sha256` after re-download.
   - **Private / derived / non-reproducible** bytes → **mirror** into MinIO; `fetch_raw` returns a
     presigned URL.

4. **The graph never stores raw bytes.** Only KB-scale documents + embeddings + entities + the `raw_ref`
   pointer go into Neo4j. Embeddings are computed client-side (OpenAI API) at ingest; the server only
   stores. Methodology (embedding/chunking) lives in git (`rag_index/graphrag/`) and is changed there +
   re-run — never by editing anything on the server (the server runs only the Neo4j + MinIO containers).

5. **`raw_ref` schema:** `{mode: mirror|source-pointer, store, bucket, key, source_url, sha256, bytes,
   content_type, recorded_on}`.

## Consequences

- Drill-down (chunk → raw) works without bloating the graph or the repo.
- Public datasets cost ~zero storage (pointer + checksum); only private/derived bytes consume MinIO disk.
- Re-download of a public source can break if the source disappears; mitigated by the recorded `sha256`
  (integrity) and the option to promote any source-pointer to a mirror later (one call to `raw_store.put`).
- MinIO is a new service to operate (deploy + creds + a dedicated volume). Bolt/S3 must not be exposed
  publicly without auth/TLS (same discipline as Neo4j, CLAUDE.md §7).
- Teammate contribution: `add_dataset.py` (one-command, repo-side) now; a hosted ingestion service
  (write-tool MCP + human gate, no repo/creds) is the follow-up that builds on this layer.
