# mcp-config/

MCP (Model Context Protocol) server configuration templates for the three clients the project supports: **Claude Desktop**, **Claude Code**, and **Cursor**.

## Recommended for teammates: project-scoped `.mcp.json` (Claude Code)

The repo ships a committed **`.mcp.json` at the root**, so Tool Universe is available to **everyone who clones the project** — no manual config. Tool Universe is the Path-B external-search source (CLAUDE.md §6, ADR-0022); without it, answering outside the DATA INAMOVIBLE carries more risk, so it's treated as core. When you open the project in **Claude Code**, it detects `.mcp.json` and asks once to approve the `tooluniverse` server; after that it's active every session. Confirm with `/mcp` (should show `tooluniverse` connected).

- **Prereq:** `uv`/`uvx` installed (see Prerequisites below). Nothing else.
- **API keys (optional):** set them as **shell environment variables** (`NCBI_API_KEY`, `NVIDIA_API_KEY`, `FDA_API_KEY`) — `.mcp.json` reads them via `${VAR:-}`, so they're **never committed**. Tool Universe runs without them (rate-limited).
- **First-run cold start:** `uvx` resolves + caches the pinned package (~30-60s). If the server times out at startup, launch Claude Code with a longer MCP timeout: `MCP_TIMEOUT=120000 claude` — `MCP_TIMEOUT` (in ms) is the real startup-timeout lever; a per-server `startupTimeout` field in `.mcp.json` is **ignored** by Claude Code.
- **Version:** pinned (`tooluniverse@1.2.6`) for reproducibility across the team — bump it in `.mcp.json` deliberately to update. (Upstream's own MCP config uses `uvx --refresh tooluniverse` for always-latest; we pin for robust, identical-across-team startup, avoiding a per-launch PyPI dependency.)

The per-client templates below are for **Claude Desktop** and **Cursor** (which do **not** read Claude Code's `.mcp.json`), or for a manual Claude Code setup.

## What's here

| File | Target client | Purpose |
|---|---|---|
| `claude-desktop.json` | Claude Desktop (Mac/Windows native app) | Reference config; copy contents into your local `claude_desktop_config.json` |
| `claude-code.json` | Claude Code (CLI / VS Code extension) | Reference config; merge into your local `~/.claude.json` |
| `cursor.json` | Cursor IDE | Reference config; copy into `~/.cursor/mcp.json` or per-project `.cursor/mcp.json` |

All three templates use the **same shape** (the only differences are file location on disk and which client reads them). The shape:

```json
{
  "mcpServers": {
    "tooluniverse": {
      "command": "uvx",
      "args": ["tooluniverse"],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "NCBI_API_KEY": "<YOUR_NCBI_KEY>",
        "NVIDIA_API_KEY": "<YOUR_NVIDIA_KEY>",
        "FDA_API_KEY": "<YOUR_FDA_KEY>"
      },
      "startupTimeout": 60000,
      "requestTimeout": 120000
    }
  }
}
```

The `startupTimeout` and `requestTimeout` values are tuned for first-time `uvx tooluniverse` invocations (which can be slow while resolving and caching deps) and slow database queries (UniProt full entries, large STRING sets can exceed 30s). These values come from operational experience on this project — see the resilience protocol in `CLAUDE.md` once Gate 4 ships.

---

## Where each client reads its config

| Client | Config file path | Source |
|---|---|---|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` | [modelcontextprotocol.io](https://modelcontextprotocol.io/docs/develop/connect-local-servers) |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` | [modelcontextprotocol.io](https://modelcontextprotocol.io/docs/develop/connect-local-servers) |
| Claude Code (macOS / Linux) | `~/.claude.json` (managed by `claude mcp add` CLI; manual edits also work) | [code.claude.com/docs/en/claude-directory](https://code.claude.com/docs/en/claude-directory) |
| Claude Code (Windows) | `%USERPROFILE%\.claude.json` — note: **`%USERPROFILE%`, not `%APPDATA%`**. The `~` in `~/.claude.json` resolves to the user home directory, which on Windows is `%USERPROFILE%`. | [code.claude.com/docs/en/claude-directory](https://code.claude.com/docs/en/claude-directory) |
| Cursor (user-level, all OS) | `~/.cursor/mcp.json` | [cursor.com/docs/cli/mcp](https://cursor.com/docs/cli/mcp) |
| Cursor (Windows specifically) | `%USERPROFILE%\.cursor\mcp.json` — same convention: home dir, not `%APPDATA%`. | [cursor.com/docs/cli/mcp](https://cursor.com/docs/cli/mcp) |
| Cursor (project-level, all OS) | `.cursor/mcp.json` in repo root | [cursor.com/docs/cli/mcp](https://cursor.com/docs/cli/mcp) |

**Sources verified 2026-05-07.** Only **Claude Desktop** uses `%APPDATA%` on Windows; **Claude Code** and **Cursor** use `%USERPROFILE%` (the user home directory) per their official docs. Standardizing all three to `%APPDATA%` would cause Claude Code and Cursor to silently ignore the configs.

### Caveat for Claude Desktop on Windows MSIX (Microsoft Store install)

Per the [tracked issue at anthropics/claude-code#26073](https://github.com/anthropics/claude-code/issues/26073): the Microsoft Store / MSIX install of Claude Desktop is virtualized — the app reads its config from the package container, **not** from the documented `%APPDATA%` path. The "Edit Config" button in Developer settings opens the wrong file. Real path for MSIX installs:

```
C:\Users\<user>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
```

If you installed Claude Desktop via the Microsoft Store and your MCP config doesn't seem to take effect, that's the file to edit. The standalone `.exe` installer uses the documented `%APPDATA%` path.

---

## Prerequisites

Before any MCP config will work, you need `uvx` installed:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify with `uvx --version`. Then test that Tool Universe starts cleanly:

```bash
uvx tooluniverse --help
```

The first run takes 30-60 seconds while `uvx` resolves and caches the package. Subsequent runs are near-instant.

---

## API keys

All three keys are **free** and **optional** (Tool Universe works without them, but those specific tools will be rate-limited or unavailable).

| Variable | Where to obtain | Default rate limit without key | What it unlocks |
|---|---|---|---|
| `NCBI_API_KEY` | https://account.ncbi.nlm.nih.gov/settings/ → "API Key Management" | 3 requests/sec | PubMed search, NCBI sequence retrieval, faster lookups (10/sec with key) |
| `NVIDIA_API_KEY` | https://build.nvidia.com → sign in → generate key | None (some tools blocked) | AlphaFold2 predictions, ESMFold, genomics models |
| `FDA_API_KEY` | https://open.fda.gov/apis/authentication/ | 240 requests/min, 1000/day | FAERS adverse-event queries, drug labels, much higher rate-limits with key |

Place the keys in the `env` block of whichever config file your client reads. **Never commit keys to the repo** — `.gitignore` excludes `*.env` and `.claude/settings.local.json` for this reason.

If you prefer to keep keys out of JSON entirely, set them as environment variables on your shell and use the JSON value `""` for each — Tool Universe will read the env vars directly.

---

## Verifying the setup

Outside any client — confirm the server resolves and runs (first run caches the package, ~30–60s):

```bash
PYTHONIOENCODING=utf-8 uvx tooluniverse@1.2.6 --help              # prints the launcher usage -> package resolves
PYTHONIOENCODING=utf-8 uvx tooluniverse@1.2.6 --list-categories   # lists the tool categories it will serve
```

> **Note:** there is **no `tooluniverse status` subcommand** (an earlier version of this doc was wrong). Use `--help` / `--list-categories` / `--list-tools` to inspect the CLI. Verified against the upstream repo (mims-harvard/ToolUniverse, v1.2.6, 2026-06).

Inside **Claude Code**, run `/mcp` — `tooluniverse` should show **connected**. (Claude Desktop / Cursor: open a conversation and try a small Tool Universe call.) If you get a startup timeout, relaunch with `MCP_TIMEOUT=120000 claude` (uvx cold start). For other failures, see the MCP-resilience rules in `CLAUDE.md` §6.

---

## Multiple clients on one machine

You can run all three clients with the same MCP server entry — they each spawn their own `uvx tooluniverse` subprocess, so there's no conflict. The cost is multiple Python processes when multiple clients are active simultaneously. On a typical dev workstation this is fine.

If you start hitting memory issues, disable the MCP entry in clients you're not actively using (just remove the `tooluniverse` key from that client's `mcpServers`).
