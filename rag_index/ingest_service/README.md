# Hosted ingestion service — let teammates complement the DATA INAMOVIBLE (no repo, no creds)

**Status:** scaffold, ready to deploy (ADR-0017/0021). It is the "path B" of `CONTRIBUTING.md`: a teammate
submits data over HTTP; only an admin token can approve it into the source of truth. The human gate is
preserved — teammates **submit to a queue**, a human **approves**.

## What it does

```
teammate  --POST /submit (submit token)-->  [queue]  --admin /approve-->  manifest + Neo4j ingest
            url (public) or file upload                 human gate (admin token)
```
- `/submit` stores the raw (source-pointer for a public URL / MinIO mirror for an upload), classifies it,
  extracts **verified entities** (resolve_id gate — never minted), and parks a PROPOSED record.
- **Auth (ADR-0056): dos puertas, una identidad.** La webapp manda el bearer de SESIÓN del backend (el
  firmante se deriva del usuario de sesión; `by` se ignora); los scripts CLI usan los tokens estáticos y
  declaran `by` explícito (400 si falta). Requiere `WITT_BACKEND_DB_URL` en el Environment (mismo valor
  que el query service); sin ella solo funciona la puerta CLI (fail-closed de sesión).
- `/pending` (admin) lists the queue (FIFO by `created_at`, con `submitted_by`); `/pending/{id}` (admin) returns the FULL
  proposal — confidence, reasoning, gap_flags, entities, raw provenance — so the approver never signs
  blind (ADR-0052). `/approve/{id}?by=Name` (admin) merges it into the manifest + ingests into Neo4j.
  `/reject/{id}?by=Name&reason=...` (admin) ARCHIVES the proposal with author+reason — never deletes
  (ADR-0045). `/actions` (admin) is the DI-change history (who did what, when, outcome). Approve/reject
  are serialized by an in-process + cross-process write lock (concurrency 1, honest 503 when busy).

## Deploy on Dokploy

1. **Create → Compose**, connect your repo, compose path `rag_index/ingest_service/docker-compose.ingest.yml`
   (build context is the repo root — needs Stage A git, unlike the paste-only Neo4j/MinIO stacks).
2. **Environment** (secrets): `INGEST_SUBMIT_TOKEN`, `INGEST_ADMIN_TOKEN`, `NEO4J_URI=bolt://neo4j:7687`,
   `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `MINIO_ENDPOINT=minio:9000`, `MINIO_ACCESS_KEY`,
   `MINIO_SECRET_KEY`. Put it on the **same internal network** as the Neo4j + MinIO services.
3. Behind Traefik with **TLS + the bearer tokens**. Do not expose without both.

## Use

```bash
# teammate — submit a public dataset:
curl -H "Authorization: Bearer $SUBMIT" -F name="Zebrafish Y atlas" -F source_db=GEO_NCBI \
     -F accession=GSE222222 -F url=https://ftp.ncbi.nlm.nih.gov/.../features.tsv.gz -F niche=RN1 \
     https://ingest.example.com/submit

# admin — review + approve (the human gate):
curl -H "Authorization: Bearer $ADMIN" https://ingest.example.com/pending
curl -X POST -H "Authorization: Bearer $ADMIN" "https://ingest.example.com/approve/<id>?by=Emmanuel"
```

## Git push-back (manifest stays canonical in git)

`/approve` keeps git canonical: it reads the current `corpus_manifest.json` **from GitHub** (Contents API),
appends the approved record, ingests into Neo4j, then **commits the updated manifest back to GitHub** — no
git binary or clone in the container, just `GITHUB_TOKEN`. Set in the Environment tab:
```
GITHUB_TOKEN=<fine-grained PAT with Contents read/write on the repo>
GITHUB_REPO=Emma-NukeAI/Witt-organo
GITHUB_BRANCH=master
```
Pull locally (`git pull`) to get service-approved records. If `GITHUB_TOKEN` is empty, push-back is
disabled (the record still enters Neo4j; a maintainer syncs the manifest — the fallback).

## Scaffold boundary (be honest about it)

- Entity extraction from uploaded `.h5ad` needs `anndata` in the image (optional, commented in
  requirements). Without it, uploads still queue + mirror; entities are extracted from public feature
  lists or left empty + flagged.
- This is the multi-user write path; the repo-side flow (`add_dataset.py` + `approve_dataset.py`) stays
  the canonical maintainer path.
