"""Exigent smoke test for the ADR-0027 detection-layer hardening of MITAD_A (durable, repo-relative).
Three axes: (A) evasion->CAUGHT (the bypasses the 2026-06-22 adversarial validation + closing audit found,
now fixed), (B) non-regression (real corpus + replay), (C) invariants (DI untouched). Prints a PASS/FAIL
tally and exits non-zero on any failure. NO-SPEND, read-and-report.

    python substrate_calibration/tools/smoke_adr0027_hardening.py   (PYTHONIOENCODING=utf-8 recommended)
"""
import os, sys, tempfile, subprocess, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # tools -> substrate_calibration -> repo root
sys.path.insert(0, str(REPO / "analysis" / "scripts"))
sys.path.insert(0, str(REPO / "substrate_calibration" / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from lib import verify_output as V
import accountability_checks as A
import replay_and_regress as R
from lib import resolve_id

RECORDS = str(REPO / "substrate_calibration" / "records")
CASES = str(REPO / "substrate_calibration" / "regression_cases")
STORE = REPO / "analysis" / "outputs" / "verified_identifiers.json"

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))

print("=" * 90)
print("A . EVASION -> CAUGHT  (each bypass the validation + closing audit found, now under ADR-0027)")
print("=" * 90)

# N1 structured mis-binding (both {symbol,ensdarg} and the REAL {marker,ens_id} 01_schoels shape) -> FAIL
mis = {"identifier_bindings": [{"symbol": "pax2a", "ensdarg": "ENSDARG00000031420"}]}        # wt1a's id
real_shape = {"canonical_rows": [{"marker": "pax2a", "ens_id": "ENSDARG00000031420"}]}        # wt1a's id, real keys
notfound_sym = {"markers": [{"symbol": "osr1", "ensdarg": "ENSDARG00000031420"}]}             # NOT_FOUND symbol, reverse
check("N1 mis-binding {symbol,ensdarg} -> admissible=False", V.admissible(mis)[0] is False)
check("N1 mis-binding {marker,ens_id} (real 01_schoels shape) -> admissible=False", V.admissible(real_shape)[0] is False)
check("N1 reverse (NOT_FOUND symbol bound to other-gene id) -> admissible=False", V.admissible(notfound_sym)[0] is False)
check("N1 control: correct binding -> admissible=True",
      V.admissible({"identifier_bindings": [{"symbol": "pax2a", "ensdarg": "ENSDARG00000028148"}]})[0] is True)

# canonical + N2 reformatted fabrications -> caught
check("fabricated store-absent ENSDARG -> admissible=False", V.admissible("gene foo is ENSDARG09999999999")[0] is False)
check("N2 lowercase fabrication -> admissible=False", V.admissible("wt1a is Ensdarg00000054611")[0] is False)
check("N2 separator fabrication -> admissible=False", V.admissible("wt1a is ENSDARG_00000054611")[0] is False)
check("N2 versioned fabrication -> admissible=False", V.admissible("wt1a is ENSDARG00000054611.1")[0] is False)

# W1 strong + not-applicable -> FAIL ; W2/N3 structured generation under methodological -> FAIL
w1 = {"framework_applied": A._FW_OK, "claim_category": "ranking", "claim_text": "ranked TFs",
      "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable", "reason": "only enumerated, no real prune performed"}]}
w2 = {"framework_applied": A._FW_OK, "claim_category": "methodological", "claim_text": "is sufficient to induce pronephros",
      "minimal_set": ["osr1", "pax2a", "lhx1a"],
      "agents_invoked": [{"agent": "reasoning-exposer", "status": "invoked", "reason": "exposed the generation reasoning for capture"}]}
check("W1 strong+not-applicable -> §11 FAIL", A.check_agents_invoked(w1)["level"] == "FAIL")
check("W2/N3 methodological+structured candidates -> §11 FAIL", A.check_agents_invoked(w2)["level"] == "FAIL")

# N6 fabricated quote -> FAIL ; multi-quote (aside + real §5 criterion) -> validated
n6 = {"claim_category": "methodological",
      "framework_applied": 'Logic-LM — per reasoning-frameworks-catalog.md §5: "this criterion appears nowhere in the catalog".',
      "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable", "reason": "no substrate audit in this fixture"}]}
n6m = {"claim_category": "methodological",
       "framework_applied": 'Logic-LM — per ...md §5: I picked it because "it felt right" and per "Problems where the answer must be provably correct, not just plausible".',
       "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable", "reason": "no substrate audit in this fixture"}]}
fc = A.check_framework_citation(n6)
fcm = A.check_framework_citation(n6m)
check("N6 fabricated quote -> §4 FAIL (not_in_catalog)", fc["level"] == "FAIL" and fc.get("quote_validation") == "not_in_catalog")
check("N6 multi-quote (aside + real §5 criterion) -> validated/PASS", fcm["level"] == "PASS" and fcm.get("quote_validation") == "validated")

# W2/N3 over-fire guards: governance pruning + repository candidates must NOT FAIL
gov = {"framework_applied": A._FW_OK, "claim_category": "pruning-proposal", "claim_text": "prune orphan nodes from the DI graph",
       "agents_invoked": [{"agent": "composite-auditor", "status": "invoked", "reason": "closing audit for the pruning proposal substrate evidence"}]}
repo = {"framework_applied": A._FW_OK, "claim_category": "extraction", "candidates": ["PRIDE", "MassIVE"],
        "claim_text": "located two proteomic repositories",
        "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable", "reason": "locating data repositories, not generating biological candidates"}]}
check("governance 'pruning-proposal' does NOT over-fire §11", A.check_agents_invoked(gov)["level"] != "FAIL")
check("repository-name candidates do NOT over-fire §11", A.check_agents_invoked(repo)["level"] != "FAIL")

# canonical: corrupt store -> replay REGRESSION (Δv=-1.0)
with tempfile.TemporaryDirectory() as td:
    sp = os.path.join(td, "corrupt.json"); R._write_sigma_prime_corrupt(sp)
    rep = R.run(RECORDS, resolve_id.SourceOfTruth(sp), cases_dir=CASES)
    check("corrupt store -> replay REGRESSION (Δv=-1.0)", rep["verdict"] == "REGRESSION" and rep["n_regressions"] >= 1,
          f"n_regressions={rep['n_regressions']}")

print()
print("=" * 90)
print("B . NON-REGRESSION  (real corpus must not break; legitimate outputs not newly FAILed)")
print("=" * 90)
ar = A.run(RECORDS)
verdicts = {r["claim_id"]: r["verdict"] for r in ar["results"]}
r_recs = [c for c in verdicts if c.startswith("claim_20260618")]
check("R1-R4 records still PASS", all(verdicts[c] == "PASS" for c in r_recs))
check("legacy 2026-05-14 records still FAIL (by design, §4)", all(verdicts[c] == "FAIL" for c in verdicts if c.startswith("claim_20260514")))
check("no NEW record-level FAIL beyond the 4 legacy", sum(1 for v in verdicts.values() if v == "FAIL") == 4,
      f"summary={ar['summary']}")
rr = R.run(RECORDS, resolve_id.SourceOfTruth(), cases_dir=CASES)
check("replay over real corpus (live store) -> NO_REGRESSION", rr["verdict"] == "NO_REGRESSION", f"n_auto={rr['n_auto_replayable']}")
import world_state as W
n_adm = sum(1 for r in A.load_records(RECORDS) if W.validate_wsts(W.wsts_from_claim(r)[0])[2])
check("world_state: 0 keyword-inferred records falsely causal_admissible (W5)", n_adm == 0, f"causal_admissible={n_adm}")

print()
print("=" * 90)
print("C . INVARIANTS  (DATA INAMOVIBLE untouched)")
print("=" * 90)
sha = hashlib.sha256(STORE.read_bytes()).hexdigest()
check("SHA256(verified_identifiers.json) == baseline f070b40c...707", sha.startswith("f070b40c641b4f5c"), sha[:16])
def git(*a):
    return subprocess.run(["git", "-C", str(REPO), "diff", "--stat", "--", *a], capture_output=True, text=True).stdout.strip()
for scope in ("analysis/outputs/", "substrate_calibration/regression_cases/"):
    check(f"git diff empty for {scope}", git(scope) == "")

print()
print("=" * 90)
n_pass = sum(1 for _, ok, _ in results if ok); n = len(results)
print(f"SMOKE TEST (ADR-0027 hardening): {n_pass}/{n} PASS")
if n_pass != n:
    print("FAILURES:", [name for name, ok, _ in results if not ok])
print("=" * 90)
sys.exit(0 if n_pass == n else 1)
