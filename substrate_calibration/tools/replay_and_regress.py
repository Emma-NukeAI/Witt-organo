"""
replay_and_regress.py — Replay-as-regression for the substrate (R1 · plan §3.1 #3).

Re-executes the deterministically-replayable check embedded in each stored claim record
against the CURRENT system Sigma' and compares the result to the stored observed_outcome
(the baseline v). A REGRESSION is Delta-v < 0: a case that previously RESOLVED POSITIVE now
fails under Sigma'. This is the formal lever the loop lacked — it turns "did the system
actually improve, or merely drift?" into a measurable per-case predicate.

READ-AND-REPORT ONLY. Mutates NOTHING (not the DATA INAMOVIBLE, not the ledger). Reads/refreshes
are free (CLAUDE.md §7); the tool only writes a report JSON to --output. It does NOT replace the
human gate — it surfaces regressions for the human/composite-auditor to act on.

Reuses (no greenfield):
  - resolve_id + verify_output  ... the deterministic (Logic-LM-class) source-of-truth gate
  - compute_ece.load_records / outcome_to_label  ... record enumeration + outcome->label mapping
  - the claim-record `seed`  ... deterministic replay provenance (stochastic checks reuse the seed)
  - evaluation/held_out_set_v1.json + evaluation/runs/  ... the frozen baseline H (when runs exist)

v1 supported replay type: `identifier_resolution` — the canonical marker-ID-corruption guard
(the 2026-06 finding: 15/16 wrong ENSDARG IDs + the wt1a false-positive expression row). A record
declares its check via an optional top-level `replay` block; new records carry it. Records without
one are reported as `manual` (need human/agent re-eval) — honestly, never silently passed.

Additive-by-design (plan): scans the CURRENT record set + the CURRENT held-out version, so any new
case / agent / rule enters the replay corpus automatically, with no change to this tool.

Usage:
    python replay_and_regress.py --records-dir ../records --output ../reports/regression_YYYYMMDD.json
    python replay_and_regress.py --records-dir ../records --store /path/to/sigma_prime_store.json --output ...
    python replay_and_regress.py --selftest        # demonstrates catching the 2026-06 marker-ID corruption
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --- wiring (reuse-first) ---------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parents[1]  # tools -> substrate_calibration -> repo root
sys.path.insert(0, str(_TOOLS_DIR))                                  # compute_ece (same dir)
sys.path.insert(0, str(_REPO_ROOT / "analysis" / "scripts"))        # the `lib` package

from compute_ece import load_records, outcome_to_label  # noqa: E402
from lib import resolve_id, verify_output                # noqa: E402

HELD_OUT = _REPO_ROOT / "evaluation" / "held_out_set_v1.json"
HELD_OUT_RUNS = _REPO_ROOT / "evaluation" / "runs"


# --- replay primitives ------------------------------------------------------------------------

def replay_identifier_resolution(spec, store):
    """Re-run an identifier-resolution check against `store` (a resolve_id.SourceOfTruth).

    spec = {
      "assertions": [{"symbol": "wt1a", "expected_ensdarg": "ENSDARG00000031420"}, ...],
      "must_fail":  ["...text containing ENSDARG00000054611...", ...]  # texts the gate MUST reject
    }
    Returns ("positive" | "negative", detail). POSITIVE iff every assertion holds AND every
    must_fail text fails the verify_output gate (ok is False) under `store`.
    """
    detail = {"assertions": [], "must_fail": []}
    ok = True
    for a in spec.get("assertions", []):
        rec = store.resolve(a["symbol"])
        got = None if rec is resolve_id.NOT_FOUND else rec.ensdarg
        passed = (got == a.get("expected_ensdarg"))
        ok = ok and passed
        detail["assertions"].append(
            {"symbol": a["symbol"], "expected": a.get("expected_ensdarg"), "got": got, "passed": passed}
        )
    for mf in spec.get("must_fail", []):
        text = mf if isinstance(mf, str) else mf.get("text", "")
        rep = verify_output.verify_identifiers(text, store=store)
        # Complementary check (NOT redundant with `assertions`): under a CLEAN store the wrong ID is
        # NOT_FOUND, so the gate rejects output text that reintroduces it (ok=False). When Σ' itself
        # legitimizes the bad ID, the `assertions` branch is what flips; `must_fail` guards the distinct
        # failure mode of the bad ID reappearing in OUTPUT TEXT under an unchanged store.
        passed = (rep.ok is False)
        ok = ok and passed
        detail["must_fail"].append(
            {"text": text[:120], "gate_ok": rep.ok, "must_fail_satisfied": passed,
             "unresolved": rep.unresolved}
        )
    return ("positive" if ok else "negative"), detail


_REPLAY_TYPES = {"identifier_resolution": replay_identifier_resolution}


def replay_record(record, store):
    """Dispatch a record's declared replay check. Returns (status, kind, detail).

    kind: "auto" (a `replay` block was present and re-run) | "manual" (no machine-replayable check).
    """
    spec = record.get("replay")
    if not spec or spec.get("type") not in _REPLAY_TYPES:
        return None, "manual", {"reason": "no machine-replayable `replay` block; needs human/agent re-eval"}
    status, detail = _REPLAY_TYPES[spec["type"]](spec, store)
    return status, "auto", detail


def delta_v(baseline_outcome, current_status):
    """Δv = label(current) - label(baseline), using the same outcome->label map as ECE.

    A regression is baseline POSITIVE (1.0) and current NEGATIVE (0.0) -> Δv = -1.0.
    Returns (delta, is_regression) ; delta is None when either side is unfalsifiable/unknown.
    """
    b = outcome_to_label(baseline_outcome)
    c = outcome_to_label(current_status)
    if b is None or c is None:
        return None, False
    d = c - b
    return d, (d < 0)


# --- the report -------------------------------------------------------------------------------

def run(records_dir, store, cases_dir=None):
    records = load_records(records_dir)
    # Additive (plan): the regression-case corpus (R1c, built from failure_log) grows the set of
    # auto-replayable guards from real errors — loaded alongside the immutable claim records.
    if cases_dir and os.path.isdir(cases_dir):
        records = records + load_records(cases_dir)
    per_record = []
    regressions = []
    inconclusive = []
    n_auto = 0
    for r in records:
        baseline = r.get("observed_outcome")
        status, kind, detail = replay_record(r, store)
        entry = {
            "claim_id": r.get("claim_id"),
            "seed": r.get("seed"),
            "kind": kind,
            "baseline_outcome": baseline,
            "current_status": status,
        }
        if kind == "auto":
            n_auto += 1
            d, regressed = delta_v(baseline, status)
            entry["delta_v"] = d
            entry["regressed"] = regressed
            entry["detail"] = detail
            if d is None:
                # an auto check that cannot produce a comparable label is SURFACED for the human gate,
                # not silently absorbed as no-regression (e.g. a replay that errored or returned unknown).
                entry["inconclusive_auto"] = True
                inconclusive.append(r.get("claim_id"))
            elif regressed:
                regressions.append(r.get("claim_id"))
        else:
            entry["note"] = detail.get("reason")
        per_record.append(entry)

    # Held-out regression slot: compare a stored month-0 baseline run to a current run, when present.
    held_out = {"set": None, "status": "no baseline run found (planned: evaluation/runs/month_0/)"}
    if HELD_OUT.exists():
        ho = json.loads(HELD_OUT.read_text(encoding="utf-8"))
        held_out["set"] = ho.get("set_version")
        held_out["n_questions"] = len(ho.get("questions", []))
        if HELD_OUT_RUNS.exists() and any(p.is_file() for p in HELD_OUT_RUNS.rglob("*.json")):
            held_out["status"] = "runs present — per-question Δ comparison TODO when month-N runs exist"
        elif HELD_OUT_RUNS.exists():
            held_out["status"] = "planned slot (placeholder dirs only — no run snapshots yet)"

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "store_version": store.store_version(),
        "store_path": str(store.store_path),
        "n_records": len(records),
        "n_auto_replayable": n_auto,
        "n_manual": len(records) - n_auto,
        "n_regressions": len(regressions),
        "regressed_claim_ids": regressions,
        "n_inconclusive_auto": len(inconclusive),
        "inconclusive_auto_claim_ids": inconclusive,
        "verdict": ("REGRESSION" if regressions else
                    ("REVIEW_INCONCLUSIVE" if inconclusive else "NO_REGRESSION")),
        "held_out": held_out,
        "per_record": per_record,
        "note": (
            "Read-and-report only; no DI/ledger mutation. A regression (Δv<0) does NOT auto-act — it is "
            "surfaced for the human gate / composite-auditor. `manual` records await a `replay` block."
        ),
    }


# --- self-test: catch the 2026-06 marker-ID corruption ----------------------------------------

_CANON_GOOD = "ENSDARG00000031420"   # wt1a, the verified ID
_CANON_BAD = "ENSDARG00000054611"    # the wrong ID the buggy 01_schoels used (collided w/ unrelated gene)

# A baseline record whose check is the canonical identifier guard. observed_outcome=positive.
_FIXTURE_RECORD = {
    "claim_id": "selftest_marker_id_guard",
    "seed": 42,
    "observed_outcome": "positive",
    "replay": {
        "type": "identifier_resolution",
        "assertions": [{"symbol": "wt1a", "expected_ensdarg": _CANON_GOOD}],
        "must_fail": [f"wt1a is {_CANON_BAD} (the value the buggy 01_schoels used)"],
    },
}


def _write_sigma_prime_corrupt(path):
    """A Σ' store where wt1a is corrupted to the WRONG ID — the exact 2026-06 fabrication."""
    envelope = {
        "store_version": "selftest-SIGMA-PRIME-CORRUPT",
        "records": [
            {"symbol": "wt1a", "ensdarg": _CANON_BAD, "raw_cache_ref": "RAW:selftest-fake",
             "confidence": 0.9, "taxon": 7955, "source_db": "selftest"},
        ],
    }
    Path(path).write_text(json.dumps(envelope), encoding="utf-8")


def selftest():
    print("=== replay_and_regress self-test: catch the 2026-06 marker-ID corruption ===")
    real_store = resolve_id.SourceOfTruth()  # the live verified store (Sigma)

    # (1) Baseline / Sigma: the guard must still hold (no regression).
    status_sigma, _, detail_sigma = replay_record(_FIXTURE_RECORD, real_store)
    d_sigma, reg_sigma = delta_v(_FIXTURE_RECORD["observed_outcome"], status_sigma)
    print(f"  Σ  (live store {real_store.store_version()}): current={status_sigma} Δv={d_sigma} regression={reg_sigma}")

    # (2) Σ' corrupt: wt1a -> wrong ID. The guard MUST flip to negative -> regression caught.
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "sigma_prime_corrupt.json")
        _write_sigma_prime_corrupt(sp)
        bad_store = resolve_id.SourceOfTruth(sp)
        status_bad, _, detail_bad = replay_record(_FIXTURE_RECORD, bad_store)
        d_bad, reg_bad = delta_v(_FIXTURE_RECORD["observed_outcome"], status_bad)
        print(f"  Σ' (corrupt wt1a->{_CANON_BAD}): current={status_bad} Δv={d_bad} regression={reg_bad}")
        print(f"     assertion: {detail_bad['assertions']}")
        print(f"     must_fail: {detail_bad['must_fail']}")

    # (3) must_fail in its intended regime: under the CLEAN live store the bad ID is NOT_FOUND, so the
    #     gate REJECTS output text reintroducing it (ok=False -> must_fail_satisfied=True). This shows
    #     must_fail is a COMPLEMENTARY guard (output-text reintroduction), not redundant with `assertions`
    #     (under the corrupt Σ' above the bad ID resolves, so must_fail does NOT fire there — `assertions` does).
    mf_rep = verify_output.verify_identifiers(f"wt1a is {_CANON_BAD}", store=real_store)
    mf_fires = (mf_rep.ok is False and _CANON_BAD in mf_rep.unresolved)
    print(f"  must_fail @ live store: gate_ok={mf_rep.ok} (bad-id NOT_FOUND={_CANON_BAD in mf_rep.unresolved}) -> fires={mf_fires}")

    ok = (status_sigma == "positive" and not reg_sigma and status_bad == "negative" and reg_bad
          and d_bad == -1.0 and mf_fires)
    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: live store shows NO regression; corrupted Σ' is caught "
          f"as Δv=-1.0 (the 2026-06 corruption, via `assertions`); `must_fail` fires on output-text reintroduction.")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches answer_pipeline.py)
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--records-dir")
    p.add_argument("--cases-dir", help="optional regression-case corpus (R1c, replay-bearing guards from failure_log)")
    p.add_argument("--store", help="path to a Σ' verified_identifiers.json to replay against (default: live store)")
    p.add_argument("--output")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if not args.records_dir or not args.output:
        p.error("--records-dir and --output are required (or use --selftest)")

    store = resolve_id.SourceOfTruth(args.store) if args.store else resolve_id.SourceOfTruth()
    report = run(args.records_dir, store, cases_dir=args.cases_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {args.output}: verdict={report['verdict']} "
          f"(n_auto={report['n_auto_replayable']}, n_regressions={report['n_regressions']})")


if __name__ == "__main__":
    main()
