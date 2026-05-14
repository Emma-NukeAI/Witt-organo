# mcp-config/

MCP (Model Context Protocol) server configuration templates for the three clients the project supports: **Claude Desktop**, **Claude Code**, and **Cursor**.

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

After editing your client's config and restarting it, run:

```bash
# Outside any client — just to confirm the MCP server starts cleanly:
PYTHONIOENCODING=utf-8 uvx tooluniverse status

# Should print: 2,200+ tools, 500+ categories, version 1.x
```

Inside the client (Claude Desktop / Code / Cursor), open a new conversation and try a small Tool Universe call. If you get a timeout or "MCP server not found" error, see the resilience protocol in `CLAUDE.md` (Gate 4 deliverable) for triage steps.

---

## Multiple clients on one machine

You can run all three clients with the same MCP server entry — they each spawn their own `uvx tooluniverse` subprocess, so there's no conflict. The cost is multiple Python processes when multiple clients are active simultaneously. On a typical dev workstation this is fine.

If you start hitting memory issues, disable the MCP entry in clients you're not actively using (just remove the `tooluniverse` key from that client's `mcpServers`).
