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

# Outcome-vocabulary reconciliation (GWT v1.1 §5.3 / ADR-0014). Records historically used
# "h1"/"h0"; the first resolved record (2026-05-31) uses "positive". The prior code scored
# anything != "h1" as 0.0 — so the one resolved record would have been scored WRONG (a latent
# bug). Map both vocabularies; EXCLUDE unfalsifiable/unknown outcomes from ECE rather than
# silently scoring them 0.0.
_POSITIVE = {"h1", "positive", "true", "correct", "yes"}
_NEGATIVE = {"h0", "negative", "false", "incorrect", "no"}


def outcome_to_label(observed_outcome):
    """Map a heterogeneous observed_outcome to 1.0 / 0.0, or None to EXCLUDE from ECE."""
    if observed_outcome is None:
        return None
    v = str(observed_outcome).strip().lower()
    if v in _POSITIVE:
        return 1.0
    if v in _NEGATIVE:
        return 0.0
    return None  # e.g. "unfalsifiable_in_phase_I" / unknown -> excluded, not scored 0.0


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
    """Return calibrated confidences via isotonic regression.

    sklearn is imported lazily so the n<10 path (the current state: only "case capture")
    runs with numpy alone, without requiring sklearn to be installed.
    """
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(confidences, outcomes)
    return iso.transform(confidences)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    records = load_records(args.records_dir)
    observable = filter_observable(records)  # observed_outcome is not None

    # Score only records whose outcome maps to a label; exclude unfalsifiable/unknown.
    scored = [(r, outcome_to_label(r.get("observed_outcome"))) for r in observable]
    excluded = [r for r, lab in scored if lab is None]
    scored = [(r, lab) for r, lab in scored if lab is not None]

    by_category = defaultdict(list)
    by_skill = defaultdict(list)
    by_sub_domain = defaultdict(list)
    for r, lab in scored:
        by_category[r.get("claim_category", "unknown")].append((r, lab))
        by_skill[r.get("skill_origin", "unknown")].append((r, lab))
        by_sub_domain[r.get("sub_domain", "unspecified")].append((r, lab))

    confidences_all = [r["stated_confidence"] for r, _ in scored]
    outcomes_all = [lab for _, lab in scored]
    n_scored = len(scored)

    # ADR-0005 test-claim language: "satisfied" only when measured+aggregated (n>=10 + ECE);
    # "case capture" at 1<=n<10; "infrastructure populated" at n==0.
    if n_scored >= 10:
        test_4_status = "satisfied"
    elif n_scored >= 1:
        test_4_status = "case capture"
    else:
        test_4_status = "infrastructure populated"

    report = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "n_total_records": len(records),
        "n_observable": len(observable),
        "n_scored": n_scored,
        "n_excluded_unfalsifiable": len(excluded),
        "tests_status": {"test_4": test_4_status},
        "reporting_note": (
            "Per ADR-0005, 'Test 4 satisfied' requires n_scored>=10 with a computed aggregate ECE. "
            f"Current state: n_scored={n_scored} -> '{test_4_status}'. ece_raw at n<10 is descriptive "
            "only, not a calibration verdict; post-hoc isotonic is not applied until n_scored>=10."
        ),
        "aggregate": {
            "ece_raw": compute_ece(confidences_all, outcomes_all),
            "defensive_threshold": 0.20,
            "ambitious_threshold": 0.10,
        },
        "per_category": {},
        "per_skill": {},
        "per_sub_domain": {},
    }

    if n_scored >= 10:
        calibrated = apply_isotonic_calibration(confidences_all, outcomes_all)
        report["aggregate"]["ece_after_isotonic"] = compute_ece(calibrated.tolist(), outcomes_all)

    for category, pairs in by_category.items():
        confs = [r["stated_confidence"] for r, _ in pairs]
        outs = [lab for _, lab in pairs]
        report["per_category"][category] = {"n": len(pairs), "ece_raw": compute_ece(confs, outs)}

    for skill, pairs in by_skill.items():
        confs = [r["stated_confidence"] for r, _ in pairs]
        outs = [lab for _, lab in pairs]
        report["per_skill"][skill] = {"n": len(pairs), "ece_raw": compute_ece(confs, outs)}

    # Per-sub-domain decomposition (Vega et al. / INTEGRATION §5.4): structure exists from day 1;
    # a per-sub-domain isotonic fit activates once a sub-domain reaches n>=10.
    for sub, pairs in by_sub_domain.items():
        confs = [r["stated_confidence"] for r, _ in pairs]
        outs = [lab for _, lab in pairs]
        entry = {"n": len(pairs), "ece_raw": compute_ece(confs, outs), "isotonic_fit": "pending (n<10)"}
        if len(pairs) >= 10:
            cal = apply_isotonic_calibration(confs, outs)
            entry["ece_after_isotonic"] = compute_ece(cal.tolist(), outs)
            entry["isotonic_fit"] = "applied"
        report["per_sub_domain"][sub] = entry

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote report to {args.output} (n_scored={n_scored}, test_4='{test_4_status}')")


if __name__ == "__main__":
    main()
