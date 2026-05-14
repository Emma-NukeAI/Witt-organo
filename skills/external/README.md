# skills/external/

External skills — primarily the Tool Universe catalog from the MIMS Lab at Harvard.

This folder is **not** a fork or vendor of Tool Universe. The repo mirrors the upstream as a **gitignored clone** so collaborators receive updates via `git pull` without our repo growing.

## What's in this folder

| Item | Source | Tracked in our git? |
|---|---|---|
| `CURATED.md` | Project-curated subset of Tool Universe skills mapped to the six niches | ✅ Yes |
| `README.md` (this file) | Project documentation | ✅ Yes |
| `ToolUniverse/` | Local clone of `mims-harvard/ToolUniverse` | ❌ No (gitignored, see root `.gitignore`) — collaborators populate locally |

---

## Tool Universe — the three access layers

Tool Universe exposes its capabilities through three layers. The repo supports all three, because each serves a different operational mode in this project.

### Layer 1 — Agent Skills *(highest level — preferred default)*

Pre-built workflows that integrate multiple tools internally. Examples: `tooluniverse-single-cell`, `tooluniverse-spatial-omics-analysis`, `tooluniverse-systems-biology`. Use these conversationally with Claude when working on a research question.

**Install (one-time per user, per machine):**
```bash
npx skills add mims-harvard/ToolUniverse
```
Skills land in your client's skills directory (`~/.claude/skills/` for Claude Code; `~/.agents/skills/` with symlinks if you have the `skills` CLI v2+).

**When to use:**
- Default for most team work in Phase I.
- Conversational research questions that match one of the curated skills (see `CURATED.md`).
- When you want the skill's built-in workflow rather than composing it yourself.

**Upstream docs:** https://zitniklab.hms.harvard.edu/ToolUniverse/guide/skills_showcase.html

### Layer 2 — MCP server *(tool-level — used by custom agents)*

Exposes ~2,200 individual tools (UniProt, JASPAR, STRING, AlphaFold, IEDB, etc.) as atomic MCP calls. Configured per client via JSON.

**Install:** add the `tooluniverse` MCP server entry to your client's MCP config. See [`mcp-config/`](../../mcp-config/) for ready-made templates for Claude Desktop, Claude Code, and Cursor.

**When to use:**
- When the project's custom orchestrator agents (in `skills/custom/organogenesis-agent-architect/`) need to call **specific tools** rather than full skills. This is the layer that connects v2.2 architecture's specialist agents to Tool Universe data sources.
- When a niche-specific Tool Universe skill doesn't exist (see CURATED.md §gaps) and you need to compose a workflow from atomic tool calls.
- When you want fine-grained control over which exact tools are invoked (auditability for substrate-instrumentation).

**Upstream docs:** https://github.com/mims-harvard/ToolUniverse#mcp-server

### Layer 3 — Python SDK *(programmatic — Phase I+ batch scripts)*

Direct Python imports. `tu.run({"name": "<tool_name>", "arguments": {...}})`.

**Install:**
```bash
pip install tooluniverse
# or, with uv:
uv pip install tooluniverse
```

**When to use:**
- Reproducible batch analysis scripts (lives in `scripts/` when those scripts begin to exist — typically Phase I month 3+).
- Long-running computations that are not appropriate for a conversational session.
- Integration into a larger Python pipeline.

**Upstream docs:** https://github.com/mims-harvard/ToolUniverse#python-sdk

### Choosing a layer — a quick rule of thumb

| Situation | Layer |
|---|---|
| "Help me investigate the role of pax6b in zebrafish cornea development" | Layer 1 (skill: `tooluniverse-target-research` or `tooluniverse-disease-research`) |
| Inside a substrate-instrumented agent that needs only the JASPAR PWM for one TF | Layer 2 (MCP tool: `jaspar_search_matrices`) |
| "Run differential expression on these 30 RNA-seq samples reproducibly tonight" | Layer 3 (SDK script in `scripts/`) |

---

## Cloning Tool Universe locally (one-time setup)

The `ToolUniverse/` folder under this directory is gitignored — collaborators populate it themselves on first setup:

```bash
cd skills/external/
git clone https://github.com/mims-harvard/ToolUniverse.git
```

To later pull updates:
```bash
cd skills/external/ToolUniverse/
git pull
```

The folder is needed primarily for:
- Reading skill source files directly (e.g., when a skill in CURATED.md is in the source repo but not yet distributed via `npx skills add` — see `tooluniverse-gene-regulatory-networks` note in CURATED.md §A).
- Running the project's `setup-tooluniverse` skill, which expects local source.
- Reviewing changes when MIMS Lab pushes updates.

If you only use Layer 1 (skills via `npx`) and Layer 2 (MCP server via `uvx`), you may **not** need the local clone. Decide based on whether you'll be reading skill source files. New collaborators: clone it on first setup unless you have a reason not to.

---

## Versioning and update workflow

Tool Universe is upstream-maintained. The project does not pin a specific Tool Universe version because:

1. The `npx skills add` command installs latest at install time.
2. The `uvx tooluniverse` MCP server resolves latest at startup.
3. Pinning would mean re-installing per team member when we want updates — not worth the friction in Phase I.

If a Tool Universe update breaks a workflow the team depends on (regression in a skill or tool), open an ADR in `docs/decisions/` documenting the breaking change and the project's response (pin a version, file an upstream issue, replace the dependency).

---

## See also

- [`CURATED.md`](CURATED.md) — the project-curated subset of skills with niche-fit justification.
- [`../../mcp-config/`](../../mcp-config/) — MCP server config templates for the three clients.
- [`../custom/organogenesis-agent-architect/`](../custom/organogenesis-agent-architect/) — the project's custom skill that orchestrates Tool Universe alongside the substrate-validation agents.
- [`../../CLAUDE.md`](../../CLAUDE.md) — operating contract that tells any agent how to use Tool Universe in this repo (Gate 4 deliverable).
