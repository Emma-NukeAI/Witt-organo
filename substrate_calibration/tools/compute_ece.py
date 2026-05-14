"""
compute_ece.py — Aggregate substrate calibration records and compute ECE.

Usage:
    python compute_ece.py --records-dir ../records --output ../reports/ece_$(date +%Y%m%d).json

Per PROJECT_SCOPE.md §5 Test 4 v1.2, this script applies post-hoc calibration
(isotonic regression + histogram binning) from day 1, not as later optimization.

Three-tier reporting:
- Defensive: ECE < 0.20 (project commitment)
- Ambitious: ECE < 0.10 (aspirational)
- Per-category: decomposed by claim_category
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime

import numpy as np
from sklearn.isotonic import IsotonicRegression


def load_records(records_dir):
    records = []
    for fname in sorted(os.listdir(records_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(records_dir, fname)) as f:
            records.append(json.load(f))
    return records


def filter_observable(records):
    """Only records with observed_outcome can be calibrated."""
    return [r for r in records if r.get("observed_outcome") is not None]


def compute_ece(confidences, outcomes, n_bins=10):
    """Expected Calibration Error via histogram binning."""
    confidences = np.array(confidences)
    outcomes = np.array(outcomes, dtype=float)
    n = len(confidences)
    if n == 0:
        return None

    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (confidences >= lo) & (confidences < hi if i < n_bins - 1 else confidences <= hi)
        if mask.sum() == 0:
            continue
        bin_conf = confidences[mask].mean()
        bin_acc = outcomes[mask].mean()
        ece += (mask.sum() / n) * abs(bin_acc - bin_conf)
    return ece


def apply_isotonic_calibration(confidences, outcomes):
    """Return calibrated confidences via isotonic regression."""
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(confidences, outcomes)
    return iso.transform(confidences)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    records = load_records(args.records_dir)
    observable = filter_observable(records)

    by_category = defaultdict(list)
    by_skill = defaultdict(list)
    for r in observable:
        by_category[r.get("claim_category", "unknown")].append(r)
        by_skill[r.get("skill_origin", "unknown")].append(r)

    confidences_all = [r["stated_confidence"] for r in observable]
    outcomes_all = [1.0 if r["observed_outcome"] == "h1" else 0.0 for r in observable]

    report = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "n_total_records": len(records),
        "n_observable": len(observable),
        "aggregate": {
            "ece_raw": compute_ece(confidences_all, outcomes_all),
            "defensive_threshold": 0.20,
            "ambitious_threshold": 0.10,
        },
        "per_category": {},
        "per_skill": {},
    }

    if len(observable) >= 10:
        calibrated = apply_isotonic_calibration(confidences_all, outcomes_all)
        report["aggregate"]["ece_after_isotonic"] = compute_ece(calibrated.tolist(), outcomes_all)

    for category, recs in by_category.items():
        confs = [r["stated_confidence"] for r in recs]
        outs = [1.0 if r["observed_outcome"] == "h1" else 0.0 for r in recs]
        report["per_category"][category] = {
            "n": len(recs),
            "ece_raw": compute_ece(confs, outs),
        }

    for skill, recs in by_skill.items():
        confs = [r["stated_confidence"] for r in recs]
        outs = [1.0 if r["observed_outcome"] == "h1" else 0.0 for r in recs]
        report["per_skill"][skill] = {
            "n": len(recs),
            "ece_raw": compute_ece(confs, outs),
        }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote report to {args.output}")


if __name__ == "__main__":
    main()
