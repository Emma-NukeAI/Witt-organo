"""
rolling_calibration.py — Reactive calibration (RIL online cadence), per RIL_PROGRAM.md §4 + ADR-0012/0014.

NO-SPEND, stdlib + the existing claim records. Computes, PER STREAM, a rolling K=6 high-confidence
hit-rate over the resolved predictions and decides whether the confidence auto-cap is active. Writes
substrate_calibration/retrospectives/rolling_calibration.json (supersedes the hand-seed).

Per-stream regime (ADR-0014):
  extraction_toy        : trigger hit-rate < 0.34  -> clamp new confidence to 0.30 (autoresearch parity)
  biomedical_hypothesis : trigger hit-rate < 0.60  -> clamp new confidence to max(declared, 0.60)

The window is DORMANT (no cap computed) until a stream has >= K resolved high-confidence predictions.

Usage:  python substrate_calibration/tools/rolling_calibration.py
"""
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_ece import load_records, outcome_to_label  # noqa: E402

K = 6
HIGH_CONF = 0.70
REGIME = {
    "extraction_toy": {"trigger": 0.34, "cap_value": 0.30, "cap_mode": "clamp_to"},
    "biomedical_hypothesis": {"trigger": 0.60, "cap_value": 0.60, "cap_mode": "max_declared"},
}

RECORDS_DIR = Path("substrate_calibration/records")
OUT = Path("substrate_calibration/retrospectives/rolling_calibration.json")


def stream_of(rec):
    """extraction/binary/data-integrity -> extraction_toy; ranking/generation -> biomedical_hypothesis."""
    cat = (rec.get("claim_category") or "").lower()
    return "biomedical_hypothesis" if cat in ("ranking", "generation") else "extraction_toy"


def main():
    records = load_records(str(RECORDS_DIR))
    resolved = []
    for r in records:
        lab = outcome_to_label(r.get("observed_outcome"))
        if lab is None:
            continue
        resolved.append({
            "claim_id": r.get("claim_id"),
            "stated_confidence": r.get("stated_confidence"),
            "observed_correct": bool(lab),
            "resolved_at": r.get("observed_at"),
            "sub_domain": r.get("sub_domain"),
            "claim_category": r.get("claim_category"),
            "stream": stream_of(r),
        })
    resolved.sort(key=lambda x: (x["resolved_at"] or ""))

    per_stream = {}
    for stream, reg in REGIME.items():
        items = [x for x in resolved if x["stream"] == stream]
        window = items[-K:]
        high = [x for x in window if (x["stated_confidence"] or 0) >= HIGH_CONF]
        hit_rate = (sum(1 for x in high if x["observed_correct"]) / len(high)) if high else None
        dormant = len(window) < K or hit_rate is None
        cap_active = (not dormant) and hit_rate < reg["trigger"]
        per_stream[stream] = {
            "n_resolved": len(items),
            "window_size": len(window),
            "n_high_conf_in_window": len(high),
            "hit_rate_high_conf": hit_rate,
            "trigger": reg["trigger"],
            "cap_mode": reg["cap_mode"],
            "cap_value": reg["cap_value"],
            "confidence_cap_active": cap_active,
            "status": ("dormant (window not full or no high-conf predictions; descriptive only)"
                       if dormant else ("CAP ACTIVE" if cap_active else "ok")),
            "window": window,
        }

    state = {
        "k": K,
        "high_conf_threshold": HIGH_CONF,
        "regime_doc": "substrate_calibration/RIL_PROGRAM.md §4 (ADR-0014)",
        "n_resolved_total": len(resolved),
        "per_stream": per_stream,
        "note": ("Reactive auto-cap is DORMANT until a stream has >= K=6 resolved high-confidence "
                 "predictions. Currently sparse (n=2 resolved). Full reactive behavior accrues with use."),
    }
    OUT.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    for s, v in per_stream.items():
        print(f"{s}: n={v['n_resolved']} hit_rate={v['hit_rate_high_conf']} -> {v['status']}")
    print(f"[rolling_calibration] wrote {OUT}")


if __name__ == "__main__":
    main()
