# DATA INAMOVIBLE — front door (MCP server + `witt-di` CLI)

The single shared entry point to the DATA INAMOVIBLE GraphRAG (ADR-0020/0039). Same backend, two transports:

| Tool | What it does |
|---|---|
| **`query_data_inamovible(query, k)`** | Semantic GraphRAG retrieval — the best related info (niches, databases, datasets, curated knowledge) for a research question. |
| **`resolve_identifier(key)`** | Deterministic verified-identifier resolve (symbol / ENSDARG / RefSeq `NM_*` / UniProt). Never invents IDs. |
| **`fetch_raw(key, filename?)`** | Drill from the graph to the RAW data (presigned MinIO URL for mirrored data, or canonical `source_url` + sha256 for public source-pointers). Pass a `CORPUS-YYYY-NNNN` id or an accession (`GSE218068`…). |

**Two front doors (hybrid, CLI-primary — ADR-0039):**
- **`witt-di` CLI** — the robust primary. Any shell/agent runs `uv run --locked python rag_index/mcp_server/cli.py …`. No per-session MCP registration, no stale stdio pipe. Same backend, same no-hang guarantee. **Prefer this** when reliability matters.
- **MCP server** (`server.py`) — the agent-native enhancement. Auto-registered via the versioned `.mcp.json`; Claude gets the three tools directly. Use it, but know its registration can fail silently — if an agent has *no* `data-inamovible` tools, fall back to the CLI.

Both call the same `rag_backend` against the same hosted Neo4j, so retrieval quality is identical (top hit ≈ 0.80). Transport is orthogonal to which RAG is hit.

---

## Setup for the team (Latido) — reproducible, self-contained

The server is **already registered** in the versioned `.mcp.json` at the repo root, launched via `uv run --locked` so it always runs on the **pinned interpreter** (`pyproject.toml` + `uv.lock`: `neo4j` + `openai` + `scikit-learn` + `fastembed` + the MCP SDK). This is the structural fix for the 2026-07-18/19 incident where the server ran on a Python **without** `neo4j` and silently degraded to sparse / hung (ADR-0039). No hardcoded machine paths; no secrets in git.

> **⚠️ Windows — clone to a SHORT path.** Windows ships `LongPathsEnabled=0` and the `openai` package tree is deep (its longest file is ~110 chars alone). Clone to a deeply nested path (base > ~150 chars) and `uv sync` installs fine but Python can't open some files (MAX_PATH = 260) → semantic silently falls to **sparse** (you'll see `FAIL semantic score alto` in step 4). Clone to e.g. `C:\dev\Witt-organo`, not a nested TEMP folder. Alternative: enable long paths (`LongPathsEnabled=1`, admin). mac/Linux have no such limit.

### 1. Install `uv` (the pinned package manager)
```bash
# Windows (PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Materialize the pinned runtime
```bash
uv sync --locked          # builds .venv EXACTLY from uv.lock (~1–2 min first time). Use --locked, always:
#                           it fails loudly if the lock drifted instead of silently resolving something else.
```
> **Never `uv pip install <anything>` into this `.venv`** (e.g. `tooluniverse`). It drifts the env off the lock, and then `uv run --locked` tries to reconcile ~140 packages on every start and can half-break the env mid-start (the 2026-07-19 incident). ToolUniverse runs via `uvx` (its own isolated env). `smoke_rag.py` warns if the venv is polluted.

### 3. Provide your secrets (ask the deploy owner for the values)
```bash
cp rag_index/mcp_server/deploy.env.example .secrets/deploy.env   # .secrets/ is gitignored — NEVER commit it
```
`query_data_inamovible` needs `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `EMBED_MODEL=openai` / `OPENAI_API_KEY`. `MINIO_*` only for `fetch_raw` of mirrored private data. `server.py` auto-loads this file (so `.mcp.json` carries no secrets).

### 4. Run the setup gate — must print `6/6 PASS`
```bash
uv run --locked python rag_index/mcp_server/smoke_rag.py
```
The `6/6` is **conditional on live infrastructure + credentials**, not a bare-clone property: it forces `RAG_BACKEND=neo4j` and requires a real semantic score ≥ 0.7, so it needs a reachable hosted Neo4j, a valid `OPENAI_API_KEY`, and a short clone path. What each check means if it FAILs:

| Check | FAIL usually means |
|---|---|
| `deps completas` | `.venv` not built or polluted → re-run `uv sync --locked`. |
| `semantic score alto (>=0.7)` | secrets missing/wrong, Neo4j unreachable, **or MAX_PATH** on Windows → dense degraded to sparse. Check `.secrets/deploy.env`; run `cli.py health`. |
| `resolve pax2a` | verified store (`analysis/outputs/verified_identifiers.json`) missing — needs no network. |
| `sparse fallback` / `concurrencia` / `no-hang` | the §6 no-hang path — these pass even offline. |

Quick manual pre-flight (human-readable): `uv run --locked python rag_index/mcp_server/cli.py health`.

### 5. Approve the MCP in Claude Code
On first launch Claude auto-detects `.mcp.json` and asks once to approve `data-inamovible`. If the first startup times out while `uv` syncs, launch with `MCP_TIMEOUT=120000 claude`.

> **Precedence:** a personal `~/.claude.json` `data-inamovible` entry OVERRIDES the versioned `.mcp.json` for that user. If you have an old local override, remove it so you use the shared, reproducible config.

---

## Reading results — the `degraded` marker (ADR-0039)

A result is **not always semantic**. When the dense GraphRAG half is unavailable (Neo4j down, dim mismatch, MAX_PATH) or disabled (dev/offline), the backend falls back to the local sparse index (§6 no-hang) — but it **marks the result** so you never mistake ~0.2 sparse scores for ~0.8 semantic:

- MCP: each hit's `metadata.degraded` is set (`sparse-by-config` | `dense-failed:sparse-only` | `sparse`) — absent on a true semantic result.
- CLI: prints `⚠ DEGRADED [...]` and exits `3` (vs exit `0` for true semantic).

If you see a degraded marker, the answer is still usable (keyword-level) but **not** high-recall semantic — retry, or run `cli.py health` to diagnose.

## `witt-di` CLI reference
```bash
uv run --locked python rag_index/mcp_server/cli.py query "transcription factors pronephric mesoderm" -k 3
uv run --locked python rag_index/mcp_server/cli.py resolve pax2a
uv run --locked python rag_index/mcp_server/cli.py fetch GSE218068
uv run --locked python rag_index/mcp_server/cli.py health
# add --json to any subcommand for machine-readable output
```
Exit codes: `0` ok (true semantic / resolved / found) · `2` usage · `3` DEGRADED (sparse-only) · `4` not found / unavailable.

## Manual / advanced (hosted) registration
For a shared/hosted deployment, run the server on the rack and expose it (stdio over SSH, or an HTTP/SSE MCP transport); other project instances point their client at the rack endpoint. Secrets never go to git — use env / `.secrets/deploy.env` / placeholders (CLAUDE.md §7). The versioned `.mcp.json` `env` block is intentionally empty of secrets. See `rag_index/deploy/README.md`.
