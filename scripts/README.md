# scripts/

Reserved for reproducible Python SDK scripts that call Tool Universe programmatically (Layer 3 access — see `skills/external/README.md`).

## When this folder gets populated

Phase I, around month 3, when batch analyses begin to recur and warrant reproducible scripts (rather than conversational invocations of skills).

Typical contents at maturity:
- `run_tool.py` — thin wrapper around `tu.run({...})` for ad-hoc tool invocation.
- `screens/` — scripts driving CRISPR/expression-screen interpretation pipelines.
- `single_cell/` — scripts running scanpy / single-cell skill workflows in batch.
- `validate_setup.py` — health check that exercises one tool from each curated skill (referenced from `README.md` quick-start).

## What does NOT belong here

- Biological data (compliance: stays in IACUC/IBC-compliant systems).
- Wet-lab protocols (live in lab partner systems).
- Long-running biological simulations (those have their own repos when they exist).
- API keys or credentials of any kind.

## Conventions when scripts arrive

- Each script begins with a docstring stating: purpose, niche(s) served, expected runtime, required environment variables.
- Use `argparse` for parameters; never hardcode tool inputs.
- Read API keys from environment variables, never from disk.
- Output to `./output/` (gitignored) by default; never overwrite without `--force`.

*This README will be updated when the first script is added.*
