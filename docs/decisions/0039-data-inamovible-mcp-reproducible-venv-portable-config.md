# 0039 — data-inamovible MCP: run on a reproducible interpreter (uv.lock) + portable versioned `.mcp.json`

- **Date:** 2026-07-19
- **Status:** accepted
- **Decided by:** Emmanuel (chose `uv run --locked` + `uv.lock` as the launch mechanism, and this ADR); double root cause diagnosed and both fixes validated live + deterministically this session
- **Affects:** `.mcp.json` (new `data-inamovible` entry), new `pyproject.toml` + `uv.lock`, `rag_index/mcp_server/{server.py,smoke_rag.py,deploy.env.example,README.md}`, `rag_index/graphrag/embeddings.py`, `analysis/scripts/lib/rag_backend.py`

## Context

`query_data_inamovible` was hanging (~1800s) and/or silently returning low-precision sparse results (scores ~0.2 instead of ~0.8). The 2026-07-19 diagnosis found a **double** root cause (see memory `data-inamovible-graphrag-query-down.md`):

1. **Wrong interpreter.** The MCP subprocess was launched (via `~/.claude.json`) on the **global** Python, which lacks `neo4j`/`openai`. `Neo4jGraphRetriever._connect()` raised `ModuleNotFoundError`, `HybridRetriever` **swallowed it** (`except Exception: pass`), and every query fell back to sparse. The founder's CLI always used the repo `.venv` (which HAS the deps), which is why the CLI-vs-MCP behaviour diverged.
2. **Import deadlock.** A first-time `import sklearn` on a **non-main worker thread** of the stdio subprocess (VS Code-launched, no console) deadlocked on the import lock — the true 1800s stall. `resolve_identifier` never touches sklearn, so it always worked.

Code-level fixes for (2) and for hosted-Neo4j slowness were applied (server.py main-thread preload + dense-timeout + §6 direct sparse fallback; `embeddings.py` OpenAI `timeout=10, max_retries=0`; `rag_backend.query_sparse`). But the **decisive** semantic fix — pointing the launcher at the `.venv` — lived only in `~/.claude.json`: **machine-local, absolute-path, does not travel.** The Latido team will all use this MCP; a per-machine `.claude.json` edit is not shippable.

## Decision

1. **Launch via `uv run --locked`** from the **versioned** `.mcp.json`: `command: "uv"`, `args: ["run","--locked","python","rag_index/mcp_server/server.py"]`. `uv` resolves the correct interpreter cross-platform (Win/mac/Linux), with **no hardcoded machine path**; `--locked` binds it to `uv.lock`.
2. **Pin the runtime** in `pyproject.toml` + `uv.lock` (`mcp, neo4j, openai, scikit-learn, numpy, fastembed, minio`) — the exact set that passes `smoke_rag.py` 6/6. This is the **structural fix for cause (1)**: the server can never again run on an interpreter missing `neo4j`/`mcp`. (`[tool.uv] package = false` — the repo is an application, not a built package.)
3. **Retain the code defenses** for cause (2) and hosted slowness (main-thread preload, §6 sparse no-hang fallback, bounded OpenAI client). Not reverted.
4. **`smoke_rag.py` is the deterministic setup gate** (6/6) each teammate runs before first use.
5. **No secrets in `.mcp.json` or `pyproject.toml`.** `server.py` loads `NEO4J_*`/`OPENAI_API_KEY`/`MINIO_*` from the gitignored `.secrets/deploy.env`; teammates copy `rag_index/mcp_server/deploy.env.example` (CLAUDE.md §7).

## Validation

- **Live (this session):** interpreter serving the MCP = the repo venv (the `Python312`-path process is the venv-launcher's base-interpreter child running venv site-packages — proven by `neo4j` importing + semantic scores; a raw-global process logs `ModuleNotFoundError`, which no longer occurs). `query_data_inamovible` → `db:ZFIN` 0.804 / `CORPUS-2026-0003#c000` 0.822 / `CORPUS-2026-0003` 0.833, **no** `degraded:sparse`. `resolve_identifier pax2a → ENSDARG00000028148`.
- **Deterministic / reproducible:** `smoke_rag.py` = **6/6 PASS** on the live venv, AND **6/6 PASS from a CLEAN `uv run --locked` environment** materialized only from `uv.lock` (67 packages, CPython 3.12.3) — proving a fresh clone reproduces the working stack.

## Alternatives considered

- **`.venv` relative path in `.mcp.json`** (`.venv/Scripts/python.exe`) — REJECTED as primary: the command differs per OS (`Scripts` vs `bin`) so one file can't be cross-platform, and each teammate must hand-build the venv; no lockfile.
- **PEP 723 `uv run --script`** (deps in the server.py header) — viable and zero-config, but no lock pinning without extra flags; rejected in favour of an auditable `uv.lock` for team reproducibility.
- **Fix only `~/.claude.json`** — REJECTED: machine-local, absolute path, does not ship to the team.
- **Hosted HTTP/SSE MCP endpoint (one server for all)** — DEFERRED: bigger build; per-clone stdio + `uv.lock` is the `prueba pequeño antes de armar bien` step. Noted as a Phase-II option once the team baseline is stable.

## Consequences

- Every teammate who clones + installs `uv` + `uv sync` + fills `.secrets/deploy.env` gets an identical, working `data-inamovible` MCP; the smoke gate proves the setup before use.
- The repo gains a root `pyproject.toml` + `uv.lock` and becomes uv-managed for its Python runtime (`package = false`, nothing is built).
- **Precedence caveat:** a personal `~/.claude.json` `data-inamovible` entry takes precedence over the versioned `.mcp.json` for that user. The founder's local override remains valid but is now redundant; remove it to adopt the shared config. Backup of the pre-fix `~/.claude.json` is at `~/.claude.json.bak-20260719-mcp`.
- First MCP startup is slower (uv first sync ~1–2 min) — documented via `MCP_TIMEOUT=120000`.
- **Not addressed here (still open):** security hardening of the hosted Neo4j/MinIO public ports (ADR-0033, deferred); a hosted single-endpoint MCP; the cosmetic log interleaving from 2 concurrent client-spawned instances.

## Evidence

- Config: `.mcp.json` (`data-inamovible` entry), `pyproject.toml`, `uv.lock`.
- Code: `rag_index/mcp_server/server.py` (main-thread preload + §6 no-hang fallback), `rag_index/graphrag/embeddings.py` (OpenAI `timeout=10, max_retries=0`), `analysis/scripts/lib/rag_backend.py` (`query_sparse`).
- Gate: `rag_index/mcp_server/smoke_rag.py` (6/6, live + clean-lock env).
- Onboarding: `rag_index/mcp_server/README.md`, `rag_index/mcp_server/deploy.env.example`.
- Root-cause narrative: memory `data-inamovible-graphrag-query-down.md`.
- Prior: ADR-0020 (MCP front door), ADR-0021 (raw store / `fetch_raw`), ADR-0022 (§6 no-hang directive origin).
