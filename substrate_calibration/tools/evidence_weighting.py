"""
evidence_weighting.py — lens-validity weighting for ranked hypotheses (ADR-0028).

EXECUTABLE LESSON from the 2026-06-22 end-to-end test (reports/2026-06-22_pronephros-upstream-signal_e2e.html):
a Self-Consistency panel converged 5/5 on a top candidate ("Wnt, inducer") whose support was ONLY
low-tier (human-ortholog PPI), over a candidate ("RA") that had the strongest evidence in the set —
zebrafish-NATIVE loss-of-function — but for a DIFFERENT role (proximodistal patterning). Majority-vote
amplified a SHARED lens-validity bias; the composite-auditor caught it (2 REVISE). This module turns
that catch into a DETERMINISTIC guard so the panel cannot silently over-claim again.

Two mechanisms:
  1. EVIDENCE_TIER + lens_weight()  — a validity hierarchy over evidence LENSES (native perturbation >
     native expression > ortholog regulatory > pathway membership > absence). Extends the IDENTIFIER
     tier_weight of verify_output (ADR-0024) to EVIDENCE lenses.
  2. rank_with_lens_validity()      — re-scores raw ranker probabilities by the BEST tier supporting each
     candidate, and raises an `overclaim_flag` when the raw-top candidate is supported only by sub-native
     tiers while a DIFFERENT candidate carries native evidence (the exact failure the auditor flagged).
     The companion practice (panel design) is to make rankers PERSPECTIVE-DIVERSE (one lens each) rather
     than N identical prompts, so a shared bias cannot reach a false consensus (see ADR-0028 / catalog §4).

Read-and-report; mutates nothing. NO-SPEND. Deterministic (a check, not a learned selector — a learned
policy is MITAD_B).

Usage:
    python evidence_weighting.py --selftest
"""
import argparse
import sys

# Validity hierarchy over evidence LENSES. native = in the TARGET species (e.g. zebrafish, taxon 7955).
# `absence` is 0.0 AND non-informative when the signal is structurally invisible to the lens (e.g. a
# nuclear-receptor signal like retinoic acid is invisible to a protein-protein-interaction database) —
# callers must NOT treat such an absence as evidence-against (the documented absence-of-evidence fallacy).
EVIDENCE_TIER = {
    "native_perturbation": 1.0,   # in-vivo loss/gain-of-function in the target species (strongest causal)
    "native_expression":   0.7,   # native expression / localization in the target species
    "ortholog_regulatory": 0.5,   # ortholog PPI / regulatory edge (cross-species projection)
    "pathway_membership":  0.2,   # enrichment / pathway membership (identity, not causation)
    "absence":             0.0,   # absent from a lens (non-informative if structurally invisible)
}
_NATIVE_TIERS = ("native_perturbation", "native_expression")
# A raw-top candidate whose best supporting tier is at or below this is "low-tier" for over-claim purposes.
_LOW_TIER_CEILING = EVIDENCE_TIER["ortholog_regulatory"]


def lens_weight(tier):
    """Validity weight in [0,1] for an evidence-lens tier string (unknown -> 0.0)."""
    return EVIDENCE_TIER.get(tier, 0.0)


def _best_tier(cand):
    tiers = cand.get("support_tiers") or []
    return max((lens_weight(t) for t in tiers), default=0.0)


def rank_with_lens_validity(candidates):
    """Re-rank ranker output by lens-validity and detect over-claim.

    candidates: list of dicts, each:
        {"name": str, "role": str (optional), "raw_prob": float, "support_tiers": [tier, ...]}
    Returns:
        {
          "ranked":  [...candidate dicts with `best_tier_weight` and `adjusted` = raw_prob*best_tier_weight,
                      sorted by `adjusted` desc...],
          "raw_top": <name of highest raw_prob>,
          "weighted_top": <name of highest adjusted>,
          "overclaim_flag": bool,   # raw-top is low-tier AND a different candidate has native evidence
          "note": str,
        }
    """
    cands = []
    for c in candidates:
        bt = _best_tier(c)
        cands.append({**c, "best_tier_weight": bt, "adjusted": float(c.get("raw_prob", 0.0)) * bt})
    by_raw = sorted(cands, key=lambda x: x.get("raw_prob", 0.0), reverse=True)
    by_adj = sorted(cands, key=lambda x: x["adjusted"], reverse=True)
    raw_top = by_raw[0] if by_raw else None
    weighted_top = by_adj[0] if by_adj else None

    overclaim = False
    note = "no candidates"
    if raw_top:
        raw_top_low = raw_top["best_tier_weight"] <= _LOW_TIER_CEILING
        native_elsewhere = next(
            (c for c in cands if c["name"] != raw_top["name"]
             and any(t in _NATIVE_TIERS for t in (c.get("support_tiers") or []))),
            None,
        )
        overclaim = bool(raw_top_low and native_elsewhere)
        if overclaim:
            ro = raw_top.get("role")
            no = native_elsewhere.get("role")
            note = (
                f"OVER-CLAIM GUARD: raw-top '{raw_top['name']}'"
                + (f" ({ro})" if ro else "")
                + f" is supported only by sub-native evidence (best tier weight {raw_top['best_tier_weight']:.2f}); "
                f"the native-evidence candidate is '{native_elsewhere['name']}'"
                + (f" ({no})" if no else "")
                + ". Do NOT collapse to a single winner: report the role-split and gate on native confirmation."
            )
        else:
            note = (f"raw-top '{raw_top['name']}' is adequately supported (best tier weight "
                    f"{raw_top['best_tier_weight']:.2f}); no native-evidence conflict detected.")
    return {
        "ranked": by_adj,
        "raw_top": raw_top["name"] if raw_top else None,
        "weighted_top": weighted_top["name"] if weighted_top else None,
        "overclaim_flag": overclaim,
        "note": note,
    }


# --- self-test: reproduce the 2026-06-22 pronephros over-claim, now caught deterministically ----------

def selftest():
    print("=== evidence_weighting self-test: reproduce + catch the pronephros over-claim (ADR-0028) ===")
    # The actual panel input from the E2E test (raw_prob + the lens tier that supported each).
    pronephros = [
        {"name": "Wnt", "role": "inducer", "raw_prob": 0.42, "support_tiers": ["ortholog_regulatory"]},
        {"name": "RA", "role": "proximodistal_patterning", "raw_prob": 0.40, "support_tiers": ["native_perturbation"]},
        {"name": "Notch", "role": "co-regulator", "raw_prob": 0.07, "support_tiers": ["ortholog_regulatory"]},
        {"name": "TGF-beta/BMP", "role": "co-regulator", "raw_prob": 0.05, "support_tiers": ["ortholog_regulatory"]},
        {"name": "FGF", "role": "weak/none", "raw_prob": 0.03, "support_tiers": ["absence"]},
    ]
    r = rank_with_lens_validity(pronephros)
    print(f"  raw_top      = {r['raw_top']}  (the panel's 5/5 winner)")
    print(f"  weighted_top = {r['weighted_top']}  (after lens-validity weighting)")
    print(f"  overclaim_flag = {r['overclaim_flag']}")
    print(f"  note: {r['note']}")
    print("  ranked (adjusted):")
    for c in r["ranked"]:
        print(f"     {c['name']:14} raw={c.get('raw_prob'):.2f} x tier={c['best_tier_weight']:.2f} -> adj={c['adjusted']:.3f}")

    # The guard must (1) FLAG the over-claim, (2) demote the ortholog-only raw-top below the native candidate.
    ok = (r["overclaim_flag"] is True
          and r["raw_top"] == "Wnt"
          and r["weighted_top"] == "RA"
          and lens_weight("native_perturbation") > lens_weight("ortholog_regulatory") > lens_weight("pathway_membership"))

    # A clean case: when the raw-top IS native-supported, no over-claim is raised.
    clean = rank_with_lens_validity([
        {"name": "RA", "role": "inducer", "raw_prob": 0.6, "support_tiers": ["native_perturbation"]},
        {"name": "Wnt", "role": "co-regulator", "raw_prob": 0.3, "support_tiers": ["ortholog_regulatory"]},
    ])
    print(f"\n  clean case: raw_top={clean['raw_top']} overclaim_flag={clean['overclaim_flag']} (expect False)")
    ok = ok and (clean["overclaim_flag"] is False and clean["weighted_top"] == "RA")

    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: the ortholog-only raw-top (Wnt) is FLAGGED as an over-claim "
          f"and demoted below the native-evidence candidate (RA); a native-supported raw-top raises no flag.")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches the other tools)
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        sys.exit(selftest())
    p.error("use --selftest (or import rank_with_lens_validity / lens_weight)")


if __name__ == "__main__":
    main()
