"""
world_state.py — Unified World-State-Transition (WSTS) claim contract (R4 · plan §3.1 #2).

A scientific claim becomes a typed tuple  ⟨S, do(a), Δŝ, W, F⟩ :
  S  = current/initial state (the world the claim is about)
  do(a) = the INTERVENTION, Pearl-typed: do(a) (an intervention) vs observe (mere conditioning).
          The formal device: P(S' | do(a)) ≠ P(S' | a) in general, so a claim typed with a do-intervention
          CANNOT be satisfied by a co-occurrence/confounded association — it must name the surgical action
          whose Δŝ moves the readout. This is what an Induction/Specificity causal claim requires.
  Δŝ = the RISKY predicted transition (what the intervention is predicted to change)
  W  = observation window (when/where the readout is taken)  — unifies the dispersed `observable_at`
  F  = failure predicate (the boolean condition that would REFUTE the claim) — Popper riskiness

This UNIFIES what the substrate already has scattered: the cascade-sim's ⟨Mode A/B × hipo/KO, predicted
transition, decouple-test⟩, squidiff's source→target verdict, and the claim-record's
expected_outcome_if_h1/h0 + observable_at + observed_outcome. A well-formed WSTS claim NATIVELY emits a
calibration datum (Δŝ predicted vs observed over W) — feeding Test 4 with no extra bookkeeping.

Read-and-report: validates / projects / derives. Mutates nothing. Reuses compute_ece.outcome_to_label.
"""
import argparse
import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS_DIR))
from compute_ece import outcome_to_label, load_records  # noqa: E402

_REQUIRED = ["state", "intervention", "predicted_delta", "observation_window", "failure_predicate"]
_INTERVENTION_TYPES = {"do", "observe"}
# Heuristic markers that a claim describes an INTERVENTION (do), not a passive observation.
_DO_MARKERS = ("induce", "induc", "knockout", "knock-out", "knockdown", "ko ", "washout", "morpholino",
               "crispr", "overexpress", "express ", "perturb", "ablat", "is sufficient to", "sufficient to induce",
               "dose", "rescue", "mutant", "do(")


def is_interventional(wsts):
    """True iff the intervention slot is do-typed (an intervention), not observe-typed (conditioning).
    Guards a non-dict intervention (e.g. a bare string) so a malformed input is rejected, not crashed."""
    iv = wsts.get("intervention")
    return isinstance(iv, dict) and iv.get("type") == "do"


def validate_wsts(wsts):
    """Well-formedness + Pearl-typing of a WSTS block. Returns (ok: bool, issues, causal_admissible).

    causal_admissible = the intervention is do-typed — the precondition for an Induction/Specificity
    CAUSAL claim. A well-formed but observe-typed tuple is valid as a *description* but cannot support a
    causal claim (it is open to confounding), and is flagged.
    """
    issues = []
    for f in _REQUIRED:
        if not wsts.get(f):
            issues.append(f"missing/empty required field: {f}")
    raw_iv = wsts.get("intervention")
    iv = raw_iv if isinstance(raw_iv, dict) else {}   # coerce: a non-dict intervention is rejected, not crashed
    if not isinstance(raw_iv, dict):
        issues.append("intervention must be an object {type, target, operation}")
    else:
        if iv.get("type") not in _INTERVENTION_TYPES:
            issues.append(f"intervention.type must be one of {sorted(_INTERVENTION_TYPES)} (do = intervention; observe = conditioning)")
        if not iv.get("target"):
            issues.append("intervention.target missing (what is intervened on)")
    # W5 fix (ADR-0027): causal_admissible is granted ONLY for an EXPLICIT do-typed block, never for a
    # do-type that was keyword-INFERRED from prose. Keyword inference over-fires (a causal verb in an
    # OBSERVATIONAL sentence — e.g. "X induces Y", or a methodological record that merely DESCRIBES "do(a)"
    # — was wrongly certified causal-admissible). An inferred do-type is a CANDIDATE only; it must be
    # confirmed by an explicit world_state_transition block before it can support an Induction/Specificity claim.
    source = wsts.get("_intervention_source", "explicit")
    causal_admissible = is_interventional(wsts) and not issues and source != "inferred"
    if is_interventional(wsts) and source == "inferred":
        issues.append("NOTE: intervention.type was keyword-INFERRED from claim_text, not an explicit "
                      "world_state_transition block -- causal_admissible WITHHELD (candidate only). Add an "
                      "explicit do-typed block to assert a causal claim (W5 fix, ADR-0027).")
    if iv.get("type") == "observe":
        issues.append("NOTE: intervention is observe-typed (conditioning) -- valid as description, but "
                      "NOT causal-admissible: P(S'|do(a)) != P(S'|a), so this cannot support an "
                      "Induction/Specificity causal claim without an actual intervention.")
    ok = not [i for i in issues if not i.startswith("NOTE:")]
    return ok, issues, causal_admissible


def wsts_from_claim(record):
    """Project an existing claim record's DISPERSED fields into the unified WSTS view (no mutation).

    Demonstrates the unification: the 5 WSTS fields already exist scattered across the claim schema.
    Fields not explicitly present are best-effort INFERRED and tagged, so the projection is honest about
    what is found vs inferred.
    """
    # Prefer an EXPLICIT world_state_transition block when a (forward) record carries one — explicit
    # intervention.type beats keyword inference, removing the heuristic mis-typing risk (R4 audit).
    explicit = record.get("world_state_transition")
    if isinstance(explicit, dict) and isinstance(explicit.get("intervention"), dict):
        return (dict(explicit, outcome=explicit.get("outcome", record.get("observed_outcome")),
                     _intervention_source="explicit"),
                ["explicit world_state_transition block used (no keyword inference)"])
    text = str(record.get("claim_text", "")).lower()
    inferred = []

    # intervention: do vs observe, inferred from the claim text (tagged as inferred).
    do_typed = any(m in text for m in _DO_MARKERS)
    inferred.append("intervention.type (inferred from claim_text)")
    intervention = {
        "type": "do" if do_typed else "observe",
        "target": record.get("sub_domain") or "unspecified (see claim_text)",
        "operation": "inferred-from-claim_text",
    }
    # explicit fields where the claim schema already carries them:
    predicted = record.get("expected_outcome_if_h1") or "unspecified"
    failure = record.get("expected_outcome_if_h0") or "unspecified"
    window = record.get("observable_at") or "unspecified"
    if not record.get("expected_outcome_if_h1"):
        inferred.append("predicted_delta (expected_outcome_if_h1 absent)")
    if not record.get("expected_outcome_if_h0"):
        inferred.append("failure_predicate (expected_outcome_if_h0 absent)")
    if not record.get("observable_at"):
        inferred.append("observation_window (observable_at absent)")

    wsts = {
        "state": record.get("state") or f"context: {record.get('sub_domain', 'unspecified')} (claim antecedent)",
        "intervention": intervention,
        "predicted_delta": predicted,
        "observation_window": window,
        "failure_predicate": failure,
        "outcome": record.get("observed_outcome"),
        "_intervention_source": "inferred",   # keyword-inferred -> causal_admissible withheld (W5 fix)
    }
    if not record.get("state"):
        inferred.append("state (no explicit state field; derived from sub_domain)")
    return wsts, inferred


def calibration_datum(record):
    """The NATIVE Test-4 datum a WSTS claim emits: (stated_confidence, observed_label).

    Reuses compute_ece.outcome_to_label. Returns None when the outcome is unobserved/unfalsifiable
    (so it is excluded from ECE rather than scored 0.0)."""
    conf = record.get("stated_confidence")
    label = outcome_to_label(record.get("observed_outcome"))
    if conf is None or label is None:
        return None
    return {"stated_confidence": conf, "observed_label": label,
            "abs_error": abs(float(conf) - float(label))}


# --- self-test --------------------------------------------------------------------------------

_WSTS_DO = {
    "state": "competent intermediate mesoderm, ~12 hpf",
    "intervention": {"type": "do", "target": "9-protein set {osr1,pax2a,...}", "operation": "express"},
    "predicted_delta": "ectopic pronephros tissue identity (wt1a+/pax2a+ tubular foci)",
    "observation_window": "Phase II wet-lab reconstitution, 48–72 hpf",
    "failure_predicate": "renal identity markers absent OR generic-mesoderm only",
    "outcome": None,
}
_WSTS_OBSERVE = dict(_WSTS_DO, intervention={"type": "observe", "target": "co-expression cluster", "operation": "condition"})


def selftest():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches answer_pipeline.py)
    except Exception:
        pass
    print("=== world_state self-test: WSTS validation + do-typing + projection + calibration datum ===")
    ok1, iss1, ca1 = validate_wsts(_WSTS_DO)
    print(f"  do-typed   : valid={ok1} causal_admissible={ca1}  (expect True/True)")
    ok2, iss2, ca2 = validate_wsts(_WSTS_OBSERVE)
    print(f"  observe    : valid={ok2} causal_admissible={ca2}  (expect True/False — conditioning ≠ causation)")
    bad = {"state": "s", "intervention": {"type": "do"}, "predicted_delta": "", "observation_window": "w", "failure_predicate": "f"}
    ok3, iss3, _ = validate_wsts(bad)
    print(f"  malformed  : valid={ok3}  issues={[i[:40] for i in iss3]}  (expect False)")
    # non-dict intervention (e.g. a bare string) must be REJECTED gracefully, not crash (R4 audit fix).
    okn, _, can = validate_wsts({"state": "s", "intervention": "do", "predicted_delta": "d",
                                 "observation_window": "w", "failure_predicate": "f"})
    print(f"  non-dict iv: valid={okn} causal_admissible={can}  (expect False/False, no crash)")

    # projection of a real claim record, if present
    proj_ok = True
    rec_path = _TOOLS_DIR.parents[1] / "substrate_calibration" / "records" / "claim_20260514_143000_pronephros-minimal-set.json"
    if rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        wsts, inferred = wsts_from_claim(rec)
        okp, _, cap = validate_wsts(wsts)
        cand = is_interventional(wsts)
        print(f"  projection of 143000 minimal-set (keyword-inferred): candidate={cand} causal_admissible={cap} "
              f"(expect candidate=True, admissible=False — W5: inferred do is withheld pending an explicit block)")
        proj_ok = cand and not cap
    # native calibration datum from a resolved record
    cd_path = _TOOLS_DIR.parents[1] / "substrate_calibration" / "records" / "claim_20260610_120000_verified-identifier-store-v1.json"
    cd_ok = True
    if cd_path.exists():
        cd = calibration_datum(json.loads(cd_path.read_text(encoding="utf-8")))
        print(f"  calibration_datum(verified-store record) = {cd}  (expect conf=0.95, label=1.0)")
        cd_ok = cd is not None and cd["observed_label"] == 1.0

    ok = (ok1 and ca1 and ok2 and not ca2 and not ok3 and not okn and not can and proj_ok and cd_ok)
    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: do-typed validates + is causal-admissible; observe-typed "
          f"is valid-but-not-causal; malformed fails; a real minimal-set claim projects to a do-WSTS; a "
          f"resolved claim emits its native (confidence, outcome) calibration datum.")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--project-records", help="records dir: project each into a WSTS view + emit calibration data")
    p.add_argument("--output")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.project_records:
        recs = load_records(args.project_records)
        out = []
        for r in recs:
            wsts, inferred = wsts_from_claim(r)
            ok, issues, ca = validate_wsts(wsts)
            out.append({"claim_id": r.get("claim_id"), "wsts": wsts, "inferred_fields": inferred,
                        "valid": ok, "causal_admissible": ca,
                        # do-typed regardless of source; True-but-not-admissible = keyword-inferred candidate (W5)
                        "causal_admissible_candidate": is_interventional(wsts),
                        "calibration_datum": calibration_datum(r)})
        rep = {"n_records": len(recs), "projections": out}
        if args.output:
            Path(args.output).write_text(json.dumps(rep, indent=2), encoding="utf-8")
            print(f"Wrote {args.output} ({len(recs)} projections)")
        else:
            print(json.dumps(rep, indent=2))
        return
    p.error("use --selftest or --project-records DIR")


if __name__ == "__main__":
    main()
