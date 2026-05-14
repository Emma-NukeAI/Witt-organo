# Calibration tooling

`compute_ece.py` aggregates records and computes ECE with optional post-hoc isotonic calibration.

Requirements: `numpy`, `sklearn` (installed by `setup_environment.sh` of `squidiff-in-silico-gate` if not already present).

Usage:

```bash
python compute_ece.py --records-dir ../records --output ../reports/ece_$(date +%Y%m%d).json
```

Decomposition: aggregate, per_category, per_skill. The per_skill axis is what tells you whether Squidiff calibration is improving over time vs other skills.
