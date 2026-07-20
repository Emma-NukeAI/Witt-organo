# DATA INAMOVIBLE — MCP server (the agents' front door)

`server.py` is the single MCP front door to the shared DATA INAMOVIBLE GraphRAG (ADR-0020). The
project's agents (and anyone with the project) query it via two MCP tools:

- **`query_data_inamovible(query, k)`** — semantic GraphRAG retrieval (the best related info for a question).
- **`resolve_identifier(key)`** — deterministic verified-identifier resolve (symbol / ENSDARG / RefSeq / UniProt).

## Run

- **Dev / offline (now):** `python rag_index/mcp_server/server.py` — runs against the local sparse v1
  (`rag_backend` TfidfRetriever); no Neo4j needed. Without the MCP SDK it runs a smoke test of the tool
  backends. With the SDK (`pip install mcp`) it serves over stdio.
- **Rack / production:** set `RAG_BACKEND=neo4j` + `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` so the
  same tools front the hosted Neo4j GraphRAG (hybrid + rerank). See `rag_index/deploy/README.md`.

## Setup para el equipo (Latido) — reproducible, 5 pasos (ADR-0039)

The server is **already registered** in the versioned `.mcp.json` at the repo root — every teammate who
clones the repo gets it. It launches via `uv run --locked`, so it always runs on the **pinned, reproducible
interpreter** (`pyproject.toml` + `uv.lock`: neo4j + openai + scikit-learn + the MCP SDK). This is the
structural fix for the 2026-07-18/19 incident where the server ran on a Python **without** `neo4j` and
silently degraded to sparse / hung (ADR-0039). No hardcoded machine paths; no secrets in git.

> **⚠️ Windows — clona en una ruta CORTA.** Windows trae `LongPathsEnabled=0` por default y el árbol de
> `openai` es profundo (el archivo más largo mide ~110 chars por sí solo). Si clonas a una ruta muy anidada
> (base > ~150 chars), `uv sync` instala bien pero Python no puede abrir algunos archivos (MAX_PATH = 260) y
> el semantic cae a **sparse en silencio** — lo verás como `FAIL semantic score alto` en el gate del paso 4.
> Clona a algo como `C:\dev\Witt-organo` (no en carpetas TEMP profundas). Alternativa: habilitar long paths
> (`LongPathsEnabled=1`, requiere admin). mac/Linux no tienen este límite.

1. **Install `uv`** (the project's package manager; Tool Universe uses it too — see `mcp-config/README.md`).
2. **Materialize the pinned runtime:** `uv sync` (creates `.venv` from `uv.lock`; ~1–2 min the first time).
3. **Provide your secrets:** copy the template and fill the real values (ask the deploy owner):
   ```
   cp rag_index/mcp_server/deploy.env.example .secrets/deploy.env   # .secrets/ is gitignored
   ```
   Required for `query_data_inamovible`: `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `EMBED_MODEL=openai`
   / `OPENAI_API_KEY`. `MINIO_*` only for `fetch_raw` of mirrored private data. server.py auto-loads this file.
4. **Run the setup gate — must print `6/6 PASS`:**
   ```
   uv run --locked python rag_index/mcp_server/smoke_rag.py
   ```
   (deps present · semantic score ≥0.7 · resolve pax2a · sparse §6 fallback · 8-user concurrency · no-hang.)
5. **Approve the MCP in Claude Code.** On first launch Claude auto-detects `.mcp.json` and asks once to
   approve `data-inamovible`. If the first startup times out while `uv` syncs, launch with
   `MCP_TIMEOUT=120000 claude` (the real startup-timeout lever).

> **Precedence:** a personal `~/.claude.json` `data-inamovible` entry OVERRIDES the versioned `.mcp.json`
> for that user. If you have an old local override, remove it so you use the shared, reproducible config.

## Manual / advanced registration

For a shared/hosted deployment, run the server on the rack and expose it (stdio over SSH, or an HTTP/SSE
MCP transport); other people's project instances point their client at the rack endpoint. Secrets
(`NEO4J_PASSWORD`) never go to git — use env / `.secrets/deploy.env` / placeholders (CLAUDE.md §7). The
versioned `.mcp.json` `env` block is intentionally empty of secrets; `server.py` loads them from
`.secrets/deploy.env`.

## Why MCP

Matches the project's existing Tool Universe / MCP pattern: agents get a tool, not a bespoke client.
The two tools mirror the source-of-truth interface (semantic + deterministic), so an agent answering a
question first `resolve_identifier`s its gene IDs (no fabrication) and `query_data_inamovible`s for the
best related corpus — exactly the multi-agent access model in ADR-0020.
