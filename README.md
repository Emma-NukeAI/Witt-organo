# Project Organogenesis × Witt

A substrate-AI venture deploying a zebrafish kidney proof-of-concept (POC) over 8 months.

## What this is

Two intertwined components:

- **Witt** — a substrate-AI thesis: capture expert calibrated judgment, expose reasoning at every step, grow with use. Domain-agnostic in concept; instantiated here in biology.
- **Project Organogenesis** — the first deployment domain. POC: zebrafish pronephros (early kidney) development, validated against four biological success gates (Induction, Specificity, Identity, Parsimony) and five substrate validation tests (orchestration, agency, iteration, calibration, cross-field).

The repo is the version-controlled source of truth for: the custom agent skill (`organogenesis-agent-architect` v2.2), the master scope document (`PROJECT_SCOPE.md` v1.2), the stress-test brief that drives v2.2 architectural decisions, the curated subset of Tool Universe skills relevant to the project's six niches, MCP configuration for any client, and operating instructions (`CLAUDE.md`) so any AI agent invoked here is immediately project-aware.

The repo is **not** a Tool Universe fork, **not** a code repository for biological simulation, **not** a wet-lab protocol repository, and **not** a place to store biological data. See `ONBOARDING.md` for what does live here vs. elsewhere.

## Quick start

1. Clone this repo: `git clone https://github.com/<owner>/witt-organogenesis.git && cd witt-organogenesis`
2. Clone Tool Universe inside `skills/external/`: `cd skills/external && git clone https://github.com/mims-harvard/ToolUniverse.git && cd ../..`
3. Install `uvx` if you don't have it: see `mcp-config/README.md` (one-line installer per OS).
4. Configure MCP for your client by copying the matching template from `mcp-config/` (see [`mcp-config/README.md`](mcp-config/README.md) for per-OS paths and the MSIX caveat for Windows Claude Desktop).
5. Set up your free API keys (NCBI, NVIDIA, FDA) — `mcp-config/README.md` lists URLs and rate-limit benefits.
6. Open `ONBOARDING.md` for the full collaborator walkthrough.

A validation script that exercises one tool from each curated skill will live in `scripts/validate_setup.py` once Phase I scripts begin (typically month 3+); for now, manual verification is described in `mcp-config/README.md`.

## Repository map

```
witt-organogenesis/
├── README.md                  ← you are here
├── CLAUDE.md                  ← operating contract for AI agents (auto-loaded by Claude Code)
├── ONBOARDING.md              ← human walkthrough for new collaborators (30–60 min)
├── PROJECT_SCOPE.md           ← v1.2 master scope: niches, phases, tests, success gates
├── LICENSE                    ← proprietary; joint copyright Nuke AI + Latido Médico Mexicano
├── docs/
│   ├── stress-test-completo.md/.pdf   ← evidence base for v2.2 architectural decisions
│   ├── v2.2-changelog.md              ← what changed v2.1 → v2.2 and why
│   └── decisions/                     ← Architecture Decision Records (ADRs); empty at setup
├── skills/
│   ├── custom/organogenesis-agent-architect/   ← the project's own skill v2.2 + 7 reference files
│   └── external/
│       ├── CURATED.md                 ← Tool Universe skills mapped to the six niches
│       ├── README.md                  ← Tool Universe layer documentation (Skill / MCP / SDK)
│       └── ToolUniverse/              ← gitignored; collaborators clone locally
├── mcp-config/                ← MCP server templates for Claude Desktop, Claude Code, Cursor
└── scripts/                   ← reserved for future Python SDK scripts (Phase I+)
```

## For deeper reading

- **`ONBOARDING.md`** — start here if you're new to the project.
- **`PROJECT_SCOPE.md`** — the master scope: what we're building, by when, by whom, with what success criteria.
- **`docs/stress-test-completo.pdf`** — the evidence base for every v2.2 architectural decision.
- **`docs/v2.2-changelog.md`** — condensed summary of what changed in v2.2.
- **`CLAUDE.md`** — the operating contract that any AI agent inside the repo must follow.
- **`skills/external/CURATED.md`** — which Tool Universe skills are in-scope, and which gaps remain.

## License

Proprietary. All rights reserved. Joint copyright held by Nuke AI and Latido Médico Mexicano under the Project Organogenesis × Witt alliance. See [`LICENSE`](LICENSE) file for full terms. This repository is private and accessible only to designated collaborators.

## Contact

- **Emmanuel** (founder, Nuke AI; co-founder, Project Organogenesis × Witt) — emmanuel@nuke-ai.com
- **Martín Gleizer** (co-founder, Latido Médico Mexicano) — Md@latidomedico.com
