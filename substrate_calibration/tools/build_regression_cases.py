"""
build_regression_cases.py — Turn logged errors into permanent replay-bearing guards (R1 · plan §3.1 #3, R1c).

This is the concrete "aprender del error y reforzar" step: it reads failure_log.jsonl and, for every
mechanically-guardable failure (an identifier fabrication/mismatch), synthesizes a REPLAY-bearing
regression-case so the corpus of auto-replayable guards GROWS from real errors. Once a guard exists,
replay_and_regress + governance_prefilter will catch any future REINTRODUCTION of that error as Δv<0.

ADDITIVE-by-design (plan): each new failure logged -> one more permanent guard, with no change to this
tool or to the replay engine.

Self-validating: a guard is written ONLY if, against the LIVE store, the asserted symbol resolves to
the correct ENSDARG AND the wrong ENSDARG is NOT_FOUND (i.e., the guard genuinely passes today). So a
generated guard is correct by construction; if it cannot be validated, it is reported, never written.

Writes to substrate_calibration/regression_cases/ (committed, durable guards) — NOT to the immutable
claim records (ADR-0002) and NOT to the DATA INAMOVIBLE. Idempotent (overwrites same guard file).

Usage:
    python build_regression_cases.py            # build guards from the live failure_log
    python build_regression_cases.py --dry-run  # report what would be built, write nothing
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parents[1]
sys.path.insert(0, str(_REPO_ROOT / "analysis" / "scripts"))
from lib import resolve_id  # noqa: E402

FAILURE_LOG = _REPO_ROOT / "substrate_calibration" / "retrospectives" / "failure_log.jsonl"
CASES_DIR = _REPO_ROOT / "substrate_calibration" / "regression_cases"

ENSDARG = re.compile(r"ENSDARG\d{11}")
# "<symbol> resolves to <ENSDARG>"  +  "<ENSDARG> is UNRESOLVED"
RESOLVES_TO = re.compile(r"\b([a-z][a-z0-9]+)\s+resolves to\s+(ENSDARG\d{11})", re.I)


def extract_identifier_guard(entry, store):
    """From a failure entry, try to derive (symbol, correct_ensdarg, wrong_ensdarg). Validate vs live store."""
    blob = " ".join(str(entry.get(k, "")) for k in ("step_descriptor", "error_feedback", "resolution"))
    m = RESOLVES_TO.search(blob)
    if not m:
        return None
    symbol, correct = m.group(1).lower(), m.group(2)
    wrongs = [e for e in ENSDARG.findall(blob) if e != correct]
    if not wrongs:
        return None
    wrong = wrongs[0]
    # self-validate against the LIVE store: correct must resolve to `correct`; wrong must be NOT_FOUND.
    rec = store.resolve(symbol)
    got = None if rec is resolve_id.NOT_FOUND else rec.ensdarg
    if got != correct:
        return {"_invalid": f"live store: {symbol} -> {got}, expected {correct} (skip)"}
    if store.resolve(wrong) is not resolve_id.NOT_FOUND:
        return {"_invalid": f"live store: wrong id {wrong} unexpectedly resolves (skip)"}
    return {"symbol": symbol, "correct": correct, "wrong": wrong}


def build(dry_run=False):
    store = resolve_id.SourceOfTruth()
    built, skipped = [], []
    if not FAILURE_LOG.exists():
        print(f"no failure_log at {FAILURE_LOG}")
        return 0
    if not dry_run:
        CASES_DIR.mkdir(exist_ok=True)

    for line in FAILURE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if entry.get("failure_type") not in ("fabrication_caught", "identifier_unverified"):
            continue  # contract_field_missing / framework_miscited are guarded by R3 checkers, not here
        g = extract_identifier_guard(entry, store)
        if not g:
            skipped.append((entry.get("event_timestamp"), "no extractable (symbol, correct, wrong)"))
            continue
        if "_invalid" in g:
            skipped.append((entry.get("event_timestamp"), g["_invalid"]))
            continue
        case = {
            "claim_id": f"regcase_{g['symbol']}_id_guard",
            "kind": "regression_guard",
            "derived_from_failure": {
                "event_timestamp": entry.get("event_timestamp"),
                "failure_type": entry.get("failure_type"),
                "related_claim_id": entry.get("related_claim_id"),
            },
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": 42,
            "observed_outcome": "positive",
            "observable_at": "deterministic, NO-SPEND (resolver round-trip + verify_output gate)",
            "replay": {
                "type": "identifier_resolution",
                "assertions": [{"symbol": g["symbol"], "expected_ensdarg": g["correct"]}],
                "must_fail": [f"{g['symbol']} is {g['wrong']} (the fabricated value caught in the failure log)"],
            },
            "note": (
                "Auto-built from failure_log by build_regression_cases.py (R1c). Guards against "
                f"reintroduction of the {g['symbol']}->{g['wrong']} fabrication. Replayed by "
                "replay_and_regress / governance_prefilter; surfaces Δv<0 if a future Σ' reintroduces it."
            ),
        }
        fpath = CASES_DIR / f"{case['claim_id']}.json"
        built.append(case["claim_id"])
        if not dry_run:
            fpath.write_text(json.dumps(case, indent=2), encoding="utf-8")

    print(f"{'[dry-run] ' if dry_run else ''}built {len(built)} guard(s): {built}")
    for ts, why in skipped:
        print(f"  skipped {ts}: {why}")
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches answer_pipeline.py)
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(build(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
