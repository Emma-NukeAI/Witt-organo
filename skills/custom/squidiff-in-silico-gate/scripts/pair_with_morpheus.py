#!/usr/bin/env python
"""
pair_with_morpheus.py — Mode 3, cross-verdict aggregator.

Reads a Squidiff metrics JSON (from run_inference.py or synthetic_fallback.py)
and a Morpheus output JSON, and produces a consolidated cross-verdict.

The cross-verdict is what catches the case v1.0 missed: scenarios where the
transcriptomic signature is normal but the morphological phenotype is extreme
(3A-KO Swiss cheese, 3B-KO masa sin arquitectura). These get flagged as
"TRANSCRIPTOMIC-ONLY PASS — morphology requires separate validation".

Morpheus JSON expected schema (see references/morpheus-pairing.md):
{
  "hypothesis_id": "...",
  "scenario_label": "3A-KO",
  "phenotype_severity": "extreme|moderate|mild|baseline",
  "phenotype_class": "swiss_cheese|catastrophic|dislocated|...",
  "confidence": 0.0..1.0,
  "morphology_decouple": "pass|partial|fail|pass-paradigm|na",
  "notes": "..."
}

Usage:
  python pair_with_morpheus.py \
    --squidiff /tmp/squidiff_metrics.json \
    --morpheus /tmp/morpheus.json \
    --out /tmp/cross_verdict.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


# Squidiff verdict derived from metrics
def squidiff_verdict_from_metrics(metrics: dict) -> dict:
    """Translate raw metrics → verdict using gate-criteria.md thresholds.

    Returns {verdict, confidence, rationale}.
    Verdict ∈ {pass, pass-decouple, moderate, fail, na}.
    """
    op = metrics.get("operation", "unknown")
    mode = metrics.get("mode", "unknown")

    # Mode 0 (synthetic fallback) caps confidence at 0.50
    is_synthetic = mode.startswith("0_") or "synthetic" in mode

    # Operation-specific thresholds
    if op == "addition":
        r = metrics.get("pearson_r", 0.0)
        d = metrics.get("directional_accuracy_top20_de", 0.0)
        # Base verdict
        if r >= 0.80 and d >= 0.75:
            verdict = "pass"
            base_conf = 0.80
        elif r >= 0.55 or d >= 0.50:
            verdict = "moderate"
            base_conf = 0.60
        else:
            verdict = "fail"
            base_conf = 0.70  # high confidence in fail
        rationale = f"Pearson r={r:.3f}, directional accuracy={d:.1%}"
    elif op == "interpolation":
        # Interpolation results don't have a single Pearson — use ΔZsem coherence
        # and the spread of intermediate predictions
        verdict = "moderate"
        base_conf = 0.60
        rationale = "Interpolation predicted; ground-truth comparison requires intermediate labels"
    else:
        verdict = "moderate"
        base_conf = 0.50
        rationale = f"Operation '{op}': default conservative verdict"

    # Transfer-learning distance penalty
    ck = metrics.get("checkpoint", {})
    distance = ck.get("transfer_distance", "unknown")
    if distance == "far":
        # Downgrade by one level
        downgrade = {"pass": "moderate", "moderate": "fail", "fail": "fail",
                     "pass-decouple": "moderate", "na": "na"}
        verdict = downgrade[verdict]
        base_conf *= 0.75
        rationale += f"; checkpoint '{ck.get('tag','?')}' applied at FAR transfer distance"
    elif distance == "mid":
        base_conf *= 0.90
        rationale += f"; checkpoint applied at MID transfer distance"

    if is_synthetic:
        base_conf = min(base_conf, 0.50)
        rationale += "; Mode 0 synthetic — confidence capped at 0.50"

    return {"verdict": verdict, "confidence": round(base_conf, 2), "rationale": rationale}


def detect_spurious_convergence(squidiff_v: dict, morpheus_v: dict | None) -> dict:
    """
    Detect the case where Squidiff says PASS but Morpheus reports extreme phenotype.
    This is the central failure mode v1.0 missed (3A-KO Swiss cheese, 3B-KO).

    Returns {is_spurious, severity, message}.
    """
    if morpheus_v is None:
        return {"is_spurious": None,
                "severity": "unknown",
                "message": "No Morpheus output provided; morphology not evaluated."}

    sq = squidiff_v["verdict"]
    morph_severity = morpheus_v.get("phenotype_severity", "unknown")
    morph_class = morpheus_v.get("phenotype_class", "unknown")
    morph_decouple = morpheus_v.get("morphology_decouple", "na")

    # Destruction-type phenotype classes — these are the spurious-convergence triggers.
    # Identity-preserved-but-disrupted classes (like "preserved_foci") are NOT spurious;
    # they are the paradigm case and get routed to PASS-DECOUPLE in consolidate().
    DESTRUCTION_CLASSES = {
        "swiss_cheese", "masa_sin_arquitectura", "catastrophic",
        "no_recognizable_organ", "cyst_amorphous"
    }

    # The spurious case: Squidiff says PASS, Morpheus reports destruction (NOT paradigm).
    # The 'pass-paradigm' decouple tag explicitly excludes this from being spurious —
    # paradigm cases are intentional decouples, not contradictions.
    if sq in ("pass", "pass-decouple") \
       and morph_severity == "extreme" \
       and morph_class in DESTRUCTION_CLASSES \
       and morph_decouple != "pass-paradigm":
        return {"is_spurious": True,
                "severity": "high",
                "message": (f"SPURIOUS CONVERGENCE: Squidiff verdict '{sq}' "
                            f"(transcriptomic identity preserved) but Morpheus reports "
                            f"extreme destruction-type phenotype ({morph_class}). "
                            f"The transcriptomic signal alone is misleading. "
                            f"Downgrading consolidated verdict and flagging for human review.")}

    # Reinforcing convergence
    if sq == morpheus_v.get("morphology_decouple"):
        return {"is_spurious": False,
                "severity": "none",
                "message": f"Both gates converge on '{sq}'. Strong signal."}

    # Mild divergence
    if (sq == "moderate" and morph_severity in ("mild", "moderate")) or \
       (sq == "pass" and morph_severity == "moderate"):
        return {"is_spurious": False,
                "severity": "mild",
                "message": "Gates differ by one level. Likely calibration drift, not contradiction."}

    return {"is_spurious": False,
            "severity": "none",
            "message": "Gates differ but not in the spurious pattern."}


def consolidate(squidiff_v: dict, morpheus_v: dict | None, spurious: dict) -> dict:
    """Produce the final cross-verdict."""
    if morpheus_v is None:
        return {
            "consolidated_verdict": squidiff_v["verdict"],
            "consolidated_label": f"TRANSCRIPTOMIC-ONLY {squidiff_v['verdict'].upper()}",
            "confidence": squidiff_v["confidence"] * 0.85,  # discount for missing morphology
            "rationale": f"{squidiff_v['rationale']}. Morphology not evaluated.",
            "spurious": spurious,
        }

    sq = squidiff_v["verdict"]
    mp = morpheus_v.get("morphology_decouple", "na")

    # Special case: pass-decouple paradigm (2B-KO style — preserved identity, no architecture)
    if sq == "pass" and mp == "pass-paradigm":
        return {
            "consolidated_verdict": "pass-decouple",
            "consolidated_label": "PASS-DECOUPLE",
            "confidence": min(squidiff_v["confidence"], morpheus_v["confidence"]) * 1.1,
            "rationale": ("Transcriptomic identity preserved (Squidiff) AND morphology shows "
                          "decouple from architecture (Morpheus). This is the paradigm case: "
                          "identity is separable from form. High-value hypothesis."),
            "spurious": spurious,
        }

    # Spurious case
    if spurious["is_spurious"]:
        return {
            "consolidated_verdict": "moderate",  # downgraded from PASS
            "consolidated_label": "TRANSCRIPTOMIC-ONLY PASS (morphology contradicts)",
            "confidence": squidiff_v["confidence"] * 0.5,
            "rationale": spurious["message"],
            "spurious": spurious,
        }

    # Reinforcing convergence — average confidence with bonus
    convergence_map = {
        ("pass", "pass"): ("pass", 1.15),
        ("fail", "fail"): ("fail", 1.10),
        ("moderate", "partial"): ("moderate", 1.05),
        ("pass", "pass-paradigm"): ("pass-decouple", 1.10),  # handled above too
    }
    key = (sq, mp)
    if key in convergence_map:
        v, mult = convergence_map[key]
        return {
            "consolidated_verdict": v,
            "consolidated_label": v.upper().replace("-", " "),
            "confidence": min(0.95, max(squidiff_v["confidence"], morpheus_v["confidence"]) * mult),
            "rationale": f"Both gates converge: Squidiff={sq}, Morpheus={mp}.",
            "spurious": spurious,
        }

    # Genuine divergence
    return {
        "consolidated_verdict": "moderate",
        "consolidated_label": "DIVERGENT — manual review",
        "confidence": (squidiff_v["confidence"] + morpheus_v["confidence"]) / 2 * 0.7,
        "rationale": f"Squidiff={sq}, Morpheus={mp}. Disagreement needs domain expert.",
        "spurious": spurious,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--squidiff", required=True, help="Path to Squidiff metrics JSON")
    ap.add_argument("--morpheus", default=None,
                    help="Path to Morpheus output JSON (omit for transcriptomic-only)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.squidiff) as f:
        sq_metrics = json.load(f)

    morpheus_v = None
    if args.morpheus and Path(args.morpheus).exists():
        with open(args.morpheus) as f:
            morpheus_v = json.load(f)

    sq_verdict = squidiff_verdict_from_metrics(sq_metrics)
    spurious = detect_spurious_convergence(sq_verdict, morpheus_v)
    consolidated = consolidate(sq_verdict, morpheus_v, spurious)

    output = {
        "squidiff_verdict": sq_verdict,
        "morpheus_verdict": morpheus_v,
        "spurious_check": spurious,
        "consolidated": consolidated,
        "metrics_source": args.squidiff,
        "hypothesis": sq_metrics.get("hypothesis", "(unspecified)"),
        "system": sq_metrics.get("system", "generic"),
        "mode": "3_cross_verdict" if morpheus_v else "1_transcriptomic_only",
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"[pair_with_morpheus] Wrote cross-verdict to {args.out}")
    print(f"[pair_with_morpheus] Verdict: {consolidated['consolidated_label']}  "
          f"(confidence {consolidated['confidence']:.2f})")


if __name__ == "__main__":
    main()
