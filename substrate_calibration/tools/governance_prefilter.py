"""
governance_prefilter.py — No-regression pre-filter for governance proposals (R1 · plan §3.1 #4).

Tarski/Goedel: a policy cannot soundly certify its own improvement from within its own level.
The frozen held-out H (plus the regression-case corpus) is the strictly-higher level. BEFORE a
governance proposal — a meta-level change Π→Π' (a new rule, scoring fn, schema, or a store/resolver
edit) — is adopted, this pre-filter re-runs the available checks under Π' and reports per-case
dominance / regression. It is INSERTED BEFORE the human gate (queued -> approved).

NON-BLOCKING + ADVISORY (CLAUDE.md §7 / ADR-0013 `self_applied:false`): it NEVER approves or applies
anything. The human gate stays final; this only SURFACES whether Π' would regress a previously-passing
case. Producer self-application is structurally impossible — the tool emits a verdict; a human acts.
This is exactly the mechanism that makes ADDING a new rule SAFE: every proposed rule is replayed
against H before it can be adopted.

Reuses (no greenfield):
  - replay_and_regress.run  ... the Δv<0 detector (store/rule-change path)
  - governance_queue.jsonl  ... the proposals (self_applied:false invariant)
  - held_out_set_v1.json    ... frozen H (per-question dominance, when month-N runs exist)
  - compute_ece.outcome_to_label ... outcome->label mapping for per-question dominance
  (TODO when month-N run snapshots exist: wire compute_ece.compute_ece for a per-category ECE delta)

Usage:
    # store/rule change: replay records (+ regression cases) under the proposed Σ'
    python governance_prefilter.py --proposal-id gp-... --store /path/to/sigma_prime.json \
        --records-dir ../records --cases-dir ../regression_cases --output ../reports/prefilter_<id>.json
    # process/schema change with held-out run snapshots:
    python governance_prefilter.py --proposal-id gp-... --baseline-run base.json --proposed-run prop.json --output ...
    python governance_prefilter.py --selftest
"""
import argparse
import json
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parents[1]
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT / "analysis" / "scripts"))

import replay_and_regress  # noqa: E402  (same tools dir)
from compute_ece import outcome_to_label  # noqa: E402
from lib import resolve_id  # noqa: E402

QUEUE = _REPO_ROOT / "substrate_calibration" / "retrospectives" / "governance_queue.jsonl"
RECORDS = _REPO_ROOT / "substrate_calibration" / "records"
CASES = _REPO_ROOT / "substrate_calibration" / "regression_cases"

_HUMAN_GATE_NOTE = (
    "ADVISORY / NON-BLOCKING. This pre-filter does not approve, reject, or apply the proposal "
    "(ADR-0013 self_applied:false). The human gate is final; a FAIL surfaces a regression for the "
    "human / composite-auditor to weigh, a PASS means 'no regression detected on the available checks'."
)


def load_proposal(queue_path, pid):
    for line in Path(queue_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("proposal_id") == pid:
            return obj
    return None


def _per_question_dominance(baseline_run, proposed_run):
    """baseline_run / proposed_run: {question_id: outcome}. Returns dominance report."""
    base = json.loads(Path(baseline_run).read_text(encoding="utf-8"))
    prop = json.loads(Path(proposed_run).read_text(encoding="utf-8"))
    regressed, improved, same = [], [], []
    b_conf, p_conf, b_out, p_out = [], [], [], []
    for qid, b in base.items():
        p = prop.get(qid)
        lb, lp = outcome_to_label(b.get("outcome") if isinstance(b, dict) else b), \
                 outcome_to_label(p.get("outcome") if isinstance(p, dict) else p)
        if lb is None or lp is None:
            continue
        if lp < lb:
            regressed.append(qid)
        elif lp > lb:
            improved.append(qid)
        else:
            same.append(qid)
    return {"regressed": regressed, "improved": improved, "unchanged": len(same),
            "dominates": len(regressed) == 0}


def prefilter(proposal, *, sigma_prime_store=None, records_dir=None, cases_dir=None,
              baseline_run=None, proposed_run=None):
    pid = proposal.get("proposal_id") if proposal else None
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "proposal_id": pid,
        "template": (proposal or {}).get("template"),
        "human_gate_note": _HUMAN_GATE_NOTE,
    }

    if sigma_prime_store:
        # Store / rule / resolver change: replay the records (+ regression-case corpus) under Σ'.
        store = resolve_id.SourceOfTruth(sigma_prime_store)
        rep = replay_and_regress.run(records_dir or str(RECORDS), store,
                                     cases_dir=cases_dir or str(CASES))
        out["check"] = "store/rule replay (replay_and_regress under Σ')"
        out["store_version_sigma_prime"] = store.store_version()
        out["n_auto_replayable"] = rep["n_auto_replayable"]
        out["regressed_claim_ids"] = rep["regressed_claim_ids"]
        out["verdict"] = "FAIL" if rep["n_regressions"] else "PASS"
        out["detail"] = {"n_regressions": rep["n_regressions"], "n_manual": rep["n_manual"]}

    elif baseline_run and proposed_run:
        dom = _per_question_dominance(baseline_run, proposed_run)
        out["check"] = "held-out per-question dominance (Π vs Π' run snapshots)"
        out["dominance"] = dom
        out["verdict"] = "PASS" if dom["dominates"] else "FAIL"

    else:
        out["check"] = "none-automatic"
        out["verdict"] = "MANUAL_REVIEW"
        out["reason"] = (
            "This proposal type (process/schema change) has no mechanical regression check available "
            "yet: it needs a held-out month-N run (evaluation/runs/, currently the planned slot) or a "
            "Σ' store snapshot. Routed to the human gate WITHOUT an automatic no-regression certificate."
        )
    return out


# --- self-test: a proposed store/rule change is pre-filtered before the human gate ------------

def selftest():
    print("=== governance_prefilter self-test: catch a regressive rule/store change pre-gate ===")
    # A synthetic regression-case corpus carrying the wt1a identifier guard (what R1c will build
    # from failure_log). The prefilter must FAIL a proposal that would corrupt it, and PASS a clean one.
    fixture = dict(replay_and_regress._FIXTURE_RECORD)
    proposal = {"proposal_id": "gp-selftest-store-edit", "template": "store-edit",
                "self_applied": False, "status": "queued"}
    with tempfile.TemporaryDirectory() as td:
        cases_dir = os.path.join(td, "regression_cases")
        os.makedirs(cases_dir)
        Path(cases_dir, "wt1a_guard.json").write_text(json.dumps(fixture), encoding="utf-8")
        empty_records = os.path.join(td, "records")
        os.makedirs(empty_records)

        # (1) Clean Σ' = the live store -> no regression -> PASS.
        live = resolve_id.SourceOfTruth().store_path
        clean = prefilter(proposal, sigma_prime_store=str(live),
                          records_dir=empty_records, cases_dir=cases_dir)
        print(f"  clean Σ' (live store): verdict={clean['verdict']} regressions={clean['regressed_claim_ids']}")

        # (2) Corrupt Σ' (wt1a -> wrong ID) -> regression -> FAIL, BEFORE any human gate.
        sp = os.path.join(td, "sigma_prime_corrupt.json")
        replay_and_regress._write_sigma_prime_corrupt(sp)
        bad = prefilter(proposal, sigma_prime_store=sp,
                        records_dir=empty_records, cases_dir=cases_dir)
        print(f"  corrupt Σ' (wt1a->wrong): verdict={bad['verdict']} regressions={bad['regressed_claim_ids']}")

    ok = (clean["verdict"] == "PASS" and bad["verdict"] == "FAIL"
          and "selftest_marker_id_guard" in bad["regressed_claim_ids"])
    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: a regressive store/rule change is flagged FAIL "
          f"pre-gate; a clean one PASSes. Human gate remains final (advisory only).")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches answer_pipeline.py)
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--proposal-id")
    p.add_argument("--queue", default=str(QUEUE))
    p.add_argument("--store", help="Σ' verified_identifiers.json (store/rule change path)")
    p.add_argument("--records-dir", default=str(RECORDS))
    p.add_argument("--cases-dir", default=str(CASES))
    p.add_argument("--baseline-run", help="per-question baseline outcomes JSON (held-out path)")
    p.add_argument("--proposed-run", help="per-question proposed outcomes JSON (held-out path)")
    p.add_argument("--output")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())
    if not args.proposal_id or not args.output:
        p.error("--proposal-id and --output are required (or use --selftest)")

    proposal = load_proposal(args.queue, args.proposal_id)
    if proposal is None:
        p.error(f"proposal {args.proposal_id} not found in {args.queue}")

    report = prefilter(proposal, sigma_prime_store=args.store, records_dir=args.records_dir,
                       cases_dir=args.cases_dir, baseline_run=args.baseline_run,
                       proposed_run=args.proposed_run)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {args.output}: proposal={report['proposal_id']} verdict={report['verdict']} ({report['check']})")


if __name__ == "__main__":
    main()
