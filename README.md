# Project Organogenesis × Witt

A substrate-AI venture deploying a zebrafish kidney proof-of-concept (POC) over 8 months.

## What this is

Two intertwined components:

- **Witt** — a substrate-AI thesis: capture expert calibrated judgment, expose reasoning at every step, grow with use. Domain-agnostic in concept; instantiated here in biology.
- **Project Organogenesis** — the first deployment domain. POC: zebrafish pronephros (early kidney) development, validated against four biological success gates (Induction, Specificity, Identity, Parsimony) and five substrate validation tests (orchestration, agency, iteration, calibration, cross-field).

The repo is the version-controlled source of truth for: the custom agent skill (`organogenesis-agent-architect` v2.3.0), the master scope document (`PROJECT_SCOPE.md` v1.4), the stress-test brief that drives v2.2 architectural decisions, the curated subset of Tool Universe skills relevant to the project's six niches, MCP configuration for any client, and operating instructions (`CLAUDE.md`) so any AI agent invoked here is immediately project-aware.

The repo is **not** a Tool Universe fork, **not** a code repository for biological simulation, and **not** a wet-lab protocol repository. Raw biological datasets are **not** stored here (they are gitignored under `analysis/data/`); what does live here is the **verified, derived** layer — analysis scripts, the verified-identifier store (`analysis/outputs/`), substrate-calibration records, and reports. See `ONBOARDING.md` for what lives here vs. elsewhere.

## Quick start

1. Clone this repo: `git clone https://github.com/<owner>/witt-organogenesis.git && cd witt-organogenesis`
2. Clone Tool Universe inside `skills/external/`: `cd skills/external && git clone https://github.com/mims-harvard/ToolUniverse.git && cd ../..`
3. Install `uvx` if you don't have it: see `mcp-config/README.md` (one-line installer per OS).
4. Configure MCP for your client by copying the matching template from `mcp-config/` (see [`mcp-config/README.md`](mcp-config/README.md) for per-OS paths and the MSIX caveat for Windows Claude Desktop).
5. Set up your free API keys (NCBI, NVIDIA, FDA) — `mcp-config/README.md` lists URLs and rate-limit benefits.
6. Open `ONBOARDING.md` for the full collaborator walkthrough.

For MCP setup verification, see `mcp-config/README.md` (per-OS paths and a manual smoke test). Phase I analysis scripts live under `analysis/scripts/` (e.g., `01_schoels_analysis.py`), and the source-of-truth resolver + anti-fabrication gate live under `analysis/scripts/lib/` (`resolve_id.py`, `verify_output.py`).

## Repository map

```
witt-organogenesis/
├── README.md                  ← you are here
├── CLAUDE.md                  ← operating contract for AI agents (auto-loaded by Claude Code)
├── ONBOARDING.md              ← human walkthrough for new collaborators (30–60 min)
├── PROJECT_SCOPE.md           ← v1.4 master scope: niches, phases, tests, success gates
├── CONTRIBUTING.md            ← human-gated workflow to add data to the DATA INAMOVIBLE
├── LICENSE                    ← proprietary; joint copyright Nuke AI + Latido Médico Mexicano
├── docs/
│   ├── HANDOFF.md                     ← the single live hand-off: current system state, how to operate, what's next
│   ├── stress-test-completo.md/.pdf   ← evidence base for v2.2 architectural decisions
│   ├── v2.2-changelog.md              ← what changed v2.1 → v2.2 and why
│   ├── decisions/                     ← Architecture Decision Records (ADRs); 53 records as of 2026-08 (0001–0053)
│   ├── findings/                      ← negative findings / corrections (substrate iteration evidence)
│   └── autoresearch-handoff/          ← imported autoresearch discipline (STRATEGY_FINAL, INTEGRATION_PROPOSAL, guide) + proposals/ + prerequisites/
├── rag_index/                        ← DATA INAMOVIBLE GraphRAG (Neo4j) + ingest service + deploy recipes (ADR-0020/0021)
├── skills/
│   ├── custom/organogenesis-agent-architect/   ← the project's own skill v2.3.0 + reference files
│   └── external/
│       ├── CURATED.md                 ← Tool Universe skills mapped to the six niches
│       ├── README.md                  ← Tool Universe layer documentation (Skill / MCP / SDK)
│       └── ToolUniverse/              ← gitignored; collaborators clone locally
├── analysis/
│   ├── data/                          ← raw datasets (gitignored)
│   ├── scripts/                       ← Phase I analysis (01_schoels_analysis.py, …) + lib/ (resolve_id, verify_output)
│   └── outputs/                       ← verified, derived artifacts: ensembl_symbol_map.json, verified_identifiers.json (DATA INAMOVIBLE v1), marker tables
├── substrate_calibration/            ← Test 4 claim records + tools/compute_ece.py + reports/
├── reports/                          ← self-contained HTML reports (TYPE A–D, html-report-contract)
├── SIMULATION_OUTPUTS_DB/            ← simulator artifacts (kept separate from DATA INAMOVIBLE)
├── evaluation/                       ← held-out evaluation set for Test 3 (months 0/4/8)
├── mcp_cache/                         ← gitignored; raw external responses (§6/§7.9 cache discipline)
├── checkpoints/                       ← gitignored; multi-phase workflow checkpoints
├── mcp-config/                ← MCP server templates for Claude Desktop, Claude Code, Cursor
└── scripts/                   ← repo-level scripts (e.g., lbpp_verify.py — verify+cache pattern)
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
