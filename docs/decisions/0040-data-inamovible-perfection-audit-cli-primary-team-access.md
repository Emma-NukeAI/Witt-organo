# 0040 — data-inamovible perfection audit: in-band degradation marker, structural human gate, `witt-di` CLI (hybrid CLI-primary), team access via local `.secrets`

- **Date:** 2026-07-19
- **Status:** accepted
- **Decided by:** Emmanuel (chose hybrid CLI-primary + team-access Option A; deferred Option B) + a 13-agent composite-auditor Chain-of-Verification panel that surfaced the findings
- **Affects:** `analysis/scripts/lib/rag_backend.py`, `rag_index/mcp_server/{server.py,cli.py (new),smoke_rag.py,README.md}`, `rag_index/graphrag/{ingest.py,bootstrap.py}`, `skills/external/README.md`, `GUIA_MEDICOS.md` (new); reports `reports/2026-07-19_*.html`
- **Follows:** ADR-0039 (this is its hardening + team-rollout follow-up)

## Context

After ADR-0039 (portable `uv run --locked` launch), restarting the client did **not** serve `data-inamovible` via the versioned `.mcp.json`: a stale **inline venv-python** config from an older still-running client session was serving it, and this session ended up with **zero `data-inamovible` tools registered** (silent per-session MCP registration failure). A diagnostic `uv run --locked` then collided with the live server holding `.venv` file locks and **half-broke the venv**. Root cause of the drift: someone had run **`uv pip install tooluniverse` into the project `.venv`** (~143 foreign packages), so `uv run --locked` wanted to reconcile the venv on every start. The venv was recovered to a pristine 69-package lock-matched state (smoke 6/6).

The repo is now **shared with the Latido Médico team** (non-technical MDs). That raised the bar: it must work flawlessly for teammates. A **perfection audit** (13-agent composite-auditor / Chain-of-Verification, per CLAUDE.md §7) of the whole DATA INAMOVIBLE process (embedding + ingest + query) and both MCPs surfaced, adversarially-verified:

- **Silent degradation** (HIGH): `HybridRetriever.query` swallowed a dense-half failure (`except Exception: pass`) and returned sparse (~0.2) with **no marker**, under a tool named "Semantic GraphRAG" — the exact failure class of the 2026-07-18/19 incident.
- **No guardrail** (HIGH) against the `uv pip install` venv pollution that caused the incident (documented in `skills/external/README.md`).
- **MCP sole front door + silent per-session registration failure** (HIGH) — literally observed this session.
- **Procedural, not structural, human gate** (MED): `gather_documents()` / `ingest.py` did not filter corpus records by `approval_chain` status — an unapproved proposal could be ingested.
- **bge default drift** (MED): `ingest.py`/`bootstrap.py` defaulted `EMBED_MODEL=bge` (768-dim) while the query path hard-pins OpenAI/1536; a fresh (re)build could create a 768-dim index the query path then silently degrades against.

## Decision

1. **In-band degradation marker.** `rag_backend` results travel a `degraded` marker on a `HitList` (`None` | `sparse-by-config` | `dense-failed:sparse-only`); `server._query` surfaces it in the response metadata + log, and `witt-di` prints `⚠ DEGRADED` + exits `3`. A sparse-only result is **never** presented as semantic. Closes the incident's failure class.
2. **`EMBED_MODEL=openai` default on the write paths** (`ingest.py`, `bootstrap.py`) whenever `NEO4J_URI` is set; `bge` stays the offline default. A fresh rebuild can no longer create a 768-dim index against the OpenAI-pinned query path.
3. **venv-pollution guardrail.** `skills/external/README.md` now warns to **never `uv pip install` into the MCP `.venv`** (ToolUniverse runs via `uvx`); `smoke_rag.py` WARNs if it detects the pollution.
4. **Structural human gate.** `rag_backend.is_approved()` filters both `gather_documents()` and `ingest.py`'s entity loop — a record whose `approval_chain` is not fully `approved` (default-deny) **physically cannot** enter the index or graph. The gate is now code-enforced, not procedure-dependent.
5. **`witt-di` CLI + hybrid, CLI-primary transport.** New `rag_index/mcp_server/cli.py` (`query|resolve|fetch|health`) wraps the **same** `rag_backend` (same no-hang, same `.secrets`, same dense quality). The MCP is **not a data-integrity hazard** (read-only front door; human gate not bypassable via MCP; secrets safe) but **is a reliability hazard** (silent per-session registration failure, stdio-pipe staleness). Since transport is orthogonal to which RAG is hit, the CLI is the **robust primary front door** and the MCP is an **optional enhancement** (agent-native tool discovery). The MCP remains **read-only** — mutation stays in the human-gated CLI scripts (`add_dataset`/`approve_dataset`), **not** exposed as MCP tools.
6. **Team access = Option A (local `.secrets`, shared credential).** Teammates get full parity with the founder (query + resolve + fetch + human-gated ingest) by having a local `.secrets/deploy.env` on their machine. Distribution: the founder shares a loose `deploy.env` + a clean repo ZIP via the team Drive (restricted to the team); `GUIA_MEDICOS.md` gives a 4-step guide + a paste-into-Claude-Code prompt that installs `uv`, places the keys, and runs the `smoke_rag.py` gate. Credential is **shared** (simplest for 4 trusted users). Claude Code is the client.

## Alternatives considered

- **Remote hosted MCP, secrets server-side, per-doctor bearer token (Option B)** — verified feasible (Streamable HTTP + static per-user bearer token; **no OAuth server required**). **DEFERRED**: over-engineering for 4 trusted teammates who want the founder's exact Claude Code experience; the backend is identical, so migrating A→B later is a transport/secrets-location change with no rework. It becomes the right move if the group grows, the store becomes more critical, or laptops can't be trusted with write credentials.
- **Read-only hosted web portal for the doctors** — REJECTED: the founder wants teammates to have **full parity** (incl. ingest) and the Claude Code experience, not a separate reduced UI, and not a forked access path.
- **Per-doctor Neo4j credentials** (revocation + attribution without a hosted server) — offered as "A done well"; **deferred to shared** for launch simplicity (documented residual: coarse revocation + no per-person attribution).
- **Adding mutation tools to the MCP** (`propose_ingest`/`approve_and_ingest`) — considered as part of Option B; **not built**. The MCP stays read-only.

## Validation

All read-only; **zero DATA INAMOVIBLE mutation**. Complete DI sweep **20/20** (embedding 1536 query=ingest=index; query/degraded/sparse; resolve ±; fetch ±; structural gate; ingest guards; Neo4j index ONLINE 1536, docs=27). Real MCP stdio handshake via `uv run --locked` **5/5** (semantic 0.804). `smoke_rag.py` **6/6**. Degradation-marker unit **4/4** (fires `sparse-by-config` in dev + `dense-failed:sparse-only` on forced dense failure; does not over-mark true semantic). Structural-gate unit **9/9**. `witt-di` e2e: `health`/`query` 0.80 / `resolve` / `fetch` exit 0; forced dense-fail → `⚠ DEGRADED` + exit 3.

## Consequences

- The silent sparse-as-semantic trap is closed at the shared-core level — every consumer (MCP, CLI, dev) sees the marker.
- The MCP's read-only invariant (celebrated by the 2026-07-05 audit) is **retained**; no mutation surface was added.
- **Shared credential = secret sprawl** on ≤4 laptops + coarse revocation (rotate + re-provision all). Accepted at this scale and trust level; the Drive folder holding `deploy.env` must stay restricted to the team. Migrate to Option B (or per-doctor creds) if this stops being acceptable.
- `GUIA_MEDICOS.md` shipped for non-technical onboarding; the technical `ONBOARDING.md` is untouched.
- Distribution via a Drive ZIP is a frozen snapshot — repo updates require re-uploading the ZIP (or switching teammates to `git pull`).

## Evidence

- Audit: `reports/2026-07-19_data-inamovible-mcp-perfection-audit_v1.html` (13-agent CoVe, findings + adversarial verdicts).
- Architecture: `reports/2026-07-19_data-inamovible-acceso-equipo-arquitectura_v1.html` (one store, many doors, mutation always gated).
- Code: `rag_backend.py` (`HitList` + `is_approved`), `server.py` (`_query` marker), `cli.py` (new), `ingest.py`/`bootstrap.py` (embed default + gate), `smoke_rag.py` (WARN), `skills/external/README.md`, `rag_index/mcp_server/README.md`, `GUIA_MEDICOS.md`.
- Commits: `b902e1f` (marker + embed default + guardrail + CLI), `aa4a61e` (structural gate + README); on `origin/master`.
- Root-cause narrative: memory `data-inamovible-graphrag-query-down.md`.
- Prior: ADR-0039 (portable launch), ADR-0020/0021/0022 (MCP front door / raw store / §6 no-hang loop).
