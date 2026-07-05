# Calibration tooling

`compute_ece.py` aggregates records and computes ECE with optional post-hoc isotonic calibration.

Requirements: `numpy`, `sklearn` (installed by `setup_environment.sh` of `squidiff-in-silico-gate` if not already present).

Usage:

```bash
python compute_ece.py --records-dir ../records --output ../reports/ece_$(date +%Y%m%d).json
```

Decomposition: aggregate, per_category, per_skill. The per_skill axis is what tells you whether Squidiff calibration is improving over time vs other skills.

## `doc_coherence_check.py` — doc↔repo drift gate

Deterministic (Logic-LM-class, **not** an LLM) check that the narrative docs (CLAUDE.md, PROJECT_SCOPE.md, README.md) still agree with the machine-readable sources of truth: the verified-identifier store (`n_records`, `store_version`), the ADR directory (highest number), the SKILL.md frontmatter (skill version), the PROJECT_SCOPE header (scope version), and the eval set size. Read-and-report — mutates nothing.

```bash
python doc_coherence_check.py            # human-readable table; exit 1 if any FAIL
python doc_coherence_check.py --json ../reports/doc_coherence_$(date +%Y%m%d).json
python doc_coherence_check.py --strict   # WARN (a doc that omits a fact) also fails
python doc_coherence_check.py --selftest # validate the parsers themselves
```

Add an invariant ⇒ add one function to `CHECKS`. The source of truth stays the JSON/code; the docs are projections of it. This catches the class of drift found in the 2026-07 doc audit (CLAUDE.md "32 records" vs. store's 51, README "8 ADRs" vs. 29 on disk, PROJECT_SCOPE footer "v1.0" vs. header "v1.3").

**Optional pre-commit hook** (opt-in, tracked in `.githooks/`): enable once per clone with
`git config core.hooksPath .githooks`. It runs this check and blocks a commit that introduces drift.
