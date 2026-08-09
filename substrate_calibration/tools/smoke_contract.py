"""
smoke_contract.py — Contract-level smoke test: does the system actually behave as the load-bearing
documents (CLAUDE.md, PROJECT_SCOPE.md, docs/HANDOFF.md) claim?

This is deliberately DIFFERENT from smoke_adr0027_hardening.py (which stress-tests the detection layer).
This one is a breadth check: it takes the concrete, testable promises made in the three governing docs and
turns each into ONE executable assertion, tagged with the doc + section it verifies. It reuses the real
machinery (resolve_id, verify_output, accountability_checks, replay_and_regress, world_state, compute_ece,
doc_coherence_check, the ADR-0027 smoke) — it does not reimplement it. NO-SPEND, read-and-report,
mutates nothing.

HONESTY BOUNDARY (audit discipline — CLAUDE.md §7, SCOPE "What the tests do NOT prove"):
This test proves the SUBSTRATE MACHINERY behaves as documented. It does NOT prove (a) the biological
objective (pronephros induction sufficiency is wet-lab-only, OPEN per HANDOFF), nor (b) that the five
validation tests all "pass" (several are 'case capture' / exploratory by the project's own language
discipline, ADR-0005). Claims that need the hosted stack / MCP / network are reported as SKIP(needs-live),
never as PASS — absence of a live check is not evidence of success.

Usage:
    python substrate_calibration/tools/smoke_contract.py            # table, exit 1 on any FAIL
    python substrate_calibration/tools/smoke_contract.py --json ../reports/smoke_contract_YYYYMMDD.json
    python substrate_calibration/tools/smoke_contract.py --strict   # SKIP also fails (require live stack)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis" / "scripts"))
sys.path.insert(0, str(REPO / "substrate_calibration" / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib import resolve_id                       # noqa: E402
from lib import verify_output as V               # noqa: E402
import accountability_checks as A                # noqa: E402
import replay_and_regress as R                   # noqa: E402
import world_state as W                          # noqa: E402

RECORDS = str(REPO / "substrate_calibration" / "records")
CASES = str(REPO / "substrate_calibration" / "regression_cases")
STORE_PATH = REPO / "analysis" / "outputs" / "verified_identifiers.json"

results = []   # (doc_ref, claim, status, detail)


def add(doc_ref, claim, status, detail=""):
    results.append((doc_ref, claim, status, detail))
    print(f"  [{status:4}] {doc_ref:22} {claim}" + (f"  -- {detail}" if detail else ""))


def ok(doc_ref, claim, cond, detail=""):
    add(doc_ref, claim, "PASS" if cond else "FAIL", detail)


def skip(doc_ref, claim, reason):
    add(doc_ref, claim, "SKIP", reason)


def _section(title):
    print("\n" + "=" * 96 + f"\n{title}\n" + "=" * 96)


# ---------------------------------------------------------------------------
_section("CLAUDE.md — the operating contract")

sot = resolve_id.SourceOfTruth()
store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
_sha_start = hashlib.sha256(STORE_PATH.read_bytes()).hexdigest()

# §7 anti-fabrication gate + §10 resolve()-first
ok("CLAUDE §7/§10", "known symbol resolves with provenance (resolve_id)",
   getattr(sot.resolve("pax2a"), "ensdarg", None) == "ENSDARG00000028148")
ok("CLAUDE §7/§10", "absent symbol -> NOT_FOUND (never invented)",
   sot.resolve("definitely_not_a_gene") is resolve_id.NOT_FOUND)
try:
    sot.require("definitely_not_a_gene"); _raised = False
except Exception:
    _raised = True
ok("CLAUDE §7/§10", "require() RAISES on NOT_FOUND (scripts can't proceed on a bad id)", _raised)
ok("CLAUDE §7", "fabricated ENSDARG -> admissible=False (verify_output gate)",
   V.admissible("gene x is ENSDARG09999999999")[0] is False)
ok("CLAUDE §7", "real symbol↔ENSDARG binding -> admissible=True",
   V.admissible({"identifier_bindings": [{"symbol": "pax2a", "ensdarg": "ENSDARG00000028148"}]})[0] is True)
ok("CLAUDE §7 (ADR-0027)", "MIS-bound symbol↔ENSDARG -> admissible=False (N1 binding, not just id-exists)",
   V.admissible({"identifier_bindings": [{"symbol": "pax2a", "ensdarg": "ENSDARG00000031420"}]})[0] is False)

# §7 DATA INAMOVIBLE read-only + human-gated flags present in the store itself
ok("CLAUDE §7", "store is self-declared read-only + human-gate-required",
   store.get("read_only") is True and store.get("human_gate_required_to_modify") is True,
   f"read_only={store.get('read_only')} gate={store.get('human_gate_required_to_modify')}")

# §4 framework-citation gate + §11 agents_invoked gate (the executable reflexes, ADR-0025)
_bare = {"claim_category": "methodological", "framework_applied": "Tier 2 heuristic",
         "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable", "reason": "fixture"}]}
_good = {"claim_category": "methodological",
         "framework_applied": 'Logic-LM — per reasoning-frameworks-catalog.md §5: "Problems where the answer must be provably correct, not just plausible".',
         "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable", "reason": "fixture"}]}
ok("CLAUDE §4 (ADR-0025)", "bare 'Tier N' citation -> §4 FAIL", A.check_framework_citation(_bare)["level"] == "FAIL")
ok("CLAUDE §4 (ADR-0025)", "specific §-section + real quote -> §4 PASS",
   A.check_framework_citation(_good)["level"] == "PASS")
_strong = {"framework_applied": A._FW_OK, "claim_category": "ranking", "claim_text": "ranked TFs",
           "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable", "reason": "only enumerated"}]}
ok("CLAUDE §11 (ADR-0025)", "ranking work + causal-pruner not-applicable -> §11 FAIL",
   A.check_agents_invoked(_strong)["level"] == "FAIL")

# §5 output contract: existing claim records carry the mandatory fields.
# NOTE: the claim-record schema names the confidence field `stated_confidence` (calibration schema),
# whereas CLAUDE §5's example JSON names it `confidence` — a minor doc↔schema naming drift, accepted here.
recs = A.load_records(RECORDS)
_conf_keys = ("confidence", "confidence_by_subclaim", "stated_confidence")
_conform = sum(1 for r in recs if any(k in r for k in _conf_keys) and "framework_applied" in r)
ok("CLAUDE §5", "claim records carry the §5 contract fields (confidence + framework_applied)",
   _conform == len(recs), f"{_conform}/{len(recs)} records conform")

# ---------------------------------------------------------------------------
_section("PROJECT_SCOPE.md — the substrate architecture & tests")

# §6 DATA INAMOVIBLE: versioned + distinct from the outputs DB
ok("SCOPE §6", "DATA INAMOVIBLE is versioned (store_version present)", bool(store.get("store_version")),
   store.get("store_version"))
ok("SCOPE §6", "SIMULATION_OUTPUTS_DB is a dir distinct from the DI outputs",
   (REPO / "SIMULATION_OUTPUTS_DB").is_dir() and (REPO / "analysis" / "outputs").is_dir())

# §5 Test 4: calibration is computable (calibration-tracker owns Test 4). Run compute_ece for real.
_py = sys.executable
_ece_out = REPO / "substrate_calibration" / "reports" / "_smoke_ece.json"
_r = subprocess.run([_py, str(REPO / "substrate_calibration" / "tools" / "compute_ece.py"),
                     "--records-dir", RECORDS, "--output", str(_ece_out)],
                    capture_output=True, text=True)
_ece = json.loads(_ece_out.read_text(encoding="utf-8")) if _ece_out.exists() else {}
_agg = (_ece.get("aggregate") or {})
_ece_val = _agg.get("ece_after_isotonic", _agg.get("ece_raw"))
_test4 = (_ece.get("tests_status") or {}).get("test_4")
ok("SCOPE §5 (Test 4)", "ECE is computable over claim records (calibration instrumented)",
   _ece.get("n_scored", 0) > 0 and _ece_val is not None,
   f"n_scored={_ece.get('n_scored')} ece_raw={_agg.get('ece_raw')} defensive<{_agg.get('defensive_threshold')}")
# Honesty: report Test-4 language, do NOT assert 'satisfied' as proof of the substrate objective.
# NOTE (composite-audit 2026-07-04): the per_skill block is a SINGLETON MOSAIC (each skill n=1), not a
# single skill — so there is no intra-skill calibration curve, and 'satisfied' at a cross-sectional n=10
# is weaker than the full Test-4 definition (longitudinal 'improve with use' + ≥85% high-conf sub-threshold).
_n_skills = len(_ece.get("per_skill") or {})
add("SCOPE §5 (Test 4)", "Test-4 status is REPORTED, not asserted as objective-met", "INFO",
    f"tool says test_4={_test4!r} at n_scored={_ece.get('n_scored')} across {_n_skills} skills × n=1 "
    f"(singleton mosaic; cross-sectional, NOT longitudinal; ≥85% high-conf sub-threshold unchecked)")

# §5 "What the tests do NOT prove" — the biological objective is explicitly OUT of this smoke's reach
skip("SCOPE §4/§5", "biological objective (pronephros induction sufficiency)",
     "wet-lab GOF only (Phase II) — OPEN per HANDOFF; not an in-silico claim")

# ADR-0006 discipline: composite-auditor replaces single-LLM Yes/No (structural — the audit gate exists)
ok("SCOPE §6 (ADR-0006)", "accountability audit runs as a deterministic gate over records",
   A.run(RECORDS).get("summary", {}).get("PASS", 0) > 0)

# ---------------------------------------------------------------------------
_section("docs/HANDOFF.md — current operational state")

# 2026-08-09: was a frozen snapshot ("51 @ 2026-06-23.1") that rotted on every human-gated ADD (the store
# grew 51->74->113). A hardcoded count in a test is the same drift class doc_coherence_check.py exists to
# catch — so assert store-INTERNAL consistency here and leave doc<->store agreement to that gate (invoked
# below as its own check).
ok("HANDOFF", "store is internally consistent (n_records == len(records), versioned)",
   store.get("n_records") == len(store.get("records", [])) and bool(store.get("store_version")),
   f"n={store.get('n_records')} v={store.get('store_version')}")

# ADR-0029: the 5 signaling/induction markers resolve
adr0029 = ["osr1", "wnt8a", "fgf8a", "aldh1a2", "cyp26a1"]
_resolved = [g for g in adr0029 if sot.resolve(g) is not resolve_id.NOT_FOUND]
ok("HANDOFF (ADR-0029)", "all 5 signaling/induction markers resolve",
   len(_resolved) == 5, f"{len(_resolved)}/5: {_resolved}")

# MITAD_A R1: replay-as-regression — corrupt store REGRESSES, live store does NOT
import tempfile, os  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    sp = os.path.join(td, "corrupt.json"); R._write_sigma_prime_corrupt(sp)
    _corrupt = R.run(RECORDS, resolve_id.SourceOfTruth(sp), cases_dir=CASES)
_live = R.run(RECORDS, resolve_id.SourceOfTruth(), cases_dir=CASES)
ok("HANDOFF (R1/ADR-0023)", "corrupt store -> replay REGRESSION (loop catches drift)",
   _corrupt["verdict"] == "REGRESSION" and _corrupt["n_regressions"] >= 1, f"n_reg={_corrupt['n_regressions']}")
ok("HANDOFF (R1/ADR-0023)", "live store -> replay NO_REGRESSION", _live["verdict"] == "NO_REGRESSION")

# MITAD_A R4: world_state do-typing (conditioning != causation); no keyword-inferred causal claims.
# Corpus-clean invariant (negative direction):
_n_falsely_causal = sum(1 for r in recs if W.validate_wsts(W.wsts_from_claim(r)[0])[2])
ok("HANDOFF (R4/ADR-0026)", "0 records falsely marked causal_admissible without an explicit WSTS block",
   _n_falsely_causal == 0, f"causal_admissible={_n_falsely_causal}")
# Detector-FIRES invariant (positive direction — added per composite-audit 2026-07-04, auditor 1 finding):
# a keyword-only 'X causes Y' with NO explicit do-block must NOT be causal_admissible; a proper do-WSTS must.
_kw_only = {"claim_text": "osr1 causes pronephros induction", "claim_category": "methodological"}
_do_wsts = {"state": "IM competent field",
            "intervention": {"type": "do", "target": "osr1", "operation": "overexpress"},
            "predicted_delta": "ectopic pax2a/wt1a induced", "observation_window": "24-48 hpf",
            "failure_predicate": "no ectopic pronephros markers"}
_kw_adm = W.validate_wsts(W.wsts_from_claim(_kw_only)[0])[2]
_do_adm = W.validate_wsts(_do_wsts)[2]
ok("HANDOFF (R4/ADR-0026)", "detector fires: keyword-only causal claim -> NOT causal_admissible",
   _kw_adm is False, f"kw_only_admissible={_kw_adm}")
ok("HANDOFF (R4/ADR-0026)", "detector fires: explicit do-WSTS -> causal_admissible",
   _do_adm is True, f"do_wsts_admissible={_do_adm}")

# The ADR-0027 hardening smoke passes end-to-end (delegate; assert exit 0)
_h = subprocess.run([_py, str(REPO / "substrate_calibration" / "tools" / "smoke_adr0027_hardening.py")],
                    capture_output=True, text=True)
_tail = (_h.stdout.strip().splitlines() or ["(no output)"])[-1]
ok("HANDOFF (ADR-0027)", "detection-hardening smoke passes (delegated)", _h.returncode == 0,
   [l for l in _h.stdout.splitlines() if "SMOKE TEST" in l][-1:] or _tail)

# doc↔repo coherence (the new drift gate) passes
_d = subprocess.run([_py, str(REPO / "substrate_calibration" / "tools" / "doc_coherence_check.py")],
                    capture_output=True, text=True)
ok("HANDOFF", "doc↔repo coherence gate passes (docs match sources of truth)", _d.returncode == 0)

# The self-reinforcing loop (ADR-0022) — module is present & structured, but LIVE run needs the hosted stack
try:
    from lib import answer_pipeline  # noqa: E402,F401
    _loop_importable = True
except Exception as e:
    _loop_importable = False; _loop_err = str(e)
ok("HANDOFF (ADR-0022)", "answer-pipeline loop module present & imports offline", _loop_importable)
skip("HANDOFF (ADR-0022)", "LIVE loop (DI-first -> MCP fallback -> audit -> reingest)",
     "needs Neo4j + OpenAI + Tool Universe MCP + .secrets/deploy.env — not exercised offline")
skip("HANDOFF", "hosted stack liveness (Neo4j / MinIO / ingest on Dokploy)",
     "needs deploy.env credentials + network")

# ---------------------------------------------------------------------------
_section("ROUND-2 — write spine, simulators, external evidence (composite-audit coverage close, 2026-07)")
# Offline/sandbox checks run always; live checks are gated by SMOKE_CONTRACT_LIVE=1 (+ the relevant env).
LIVE = os.environ.get("SMOKE_CONTRACT_LIVE") == "1"

# (offline) sandbox DI mutation cycle — write spine + read-back, real DI untouched (does NOT mutate STORE_PATH)
try:
    _d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    _n0 = _d["n_records"]
    _rec = {"symbol": "sandbox_testgene", "ensdarg": "ENSDARG09999999999", "taxon": 7955,
            "source_db": "sandbox", "resolver": "sandbox", "raw_cache_ref": "RAW:sandbox",
            "verified_on": "2026-07-04", "provenance": "sandbox", "confidence": 1.0, "tier": "RAW"}
    _recs = (_d.get("records") or []) + [_rec]
    _d["records"] = _recs; _d["n_records"] = len(_recs); _d["store_version"] = "SANDBOX"
    _sand = str(Path(tempfile.mkdtemp()) / "di_sandbox.json")
    Path(_sand).write_text(json.dumps(_d), encoding="utf-8")
    _sb = resolve_id.SourceOfTruth(_sand).resolve("sandbox_testgene")
    ok("HANDOFF §7 (write spine)", "sandbox DI ADD + read-back via resolver (real DI untouched)",
       getattr(_sb, "ensdarg", None) == "ENSDARG09999999999" and _d["n_records"] == _n0 + 1)
except Exception as e:
    ok("HANDOFF §7 (write spine)", "sandbox DI ADD + read-back", False, f"{type(e).__name__}: {e}")

# (offline) ingest MERGE-never-deletes — verify-by-construction (CLAUDE §7 'inamovible')
_ing = (REPO / "rag_index" / "graphrag" / "ingest.py").read_text(encoding="utf-8")
_deletes = len(re.findall(r"\b(?:DELETE|DETACH|REMOVE)\b", _ing))
ok("CLAUDE §7 (inamovible)", "ingest.py has zero DELETE/DETACH/REMOVE (MERGE-only, never deletes)",
   _deletes == 0, f"delete_ops={_deletes}")

# (offline) governance_prefilter functional — corrupt Σ' store -> advisory FAIL (not just selftest)
try:
    import governance_prefilter as _G
    _sp = os.path.join(tempfile.mkdtemp(), "corrupt.json"); R._write_sigma_prime_corrupt(_sp)
    _gp = _G.prefilter({"proposal_id": "smoke", "template": "store-change"}, sigma_prime_store=_sp,
                       records_dir=RECORDS, cases_dir=CASES)
    ok("HANDOFF (R1/ADR-0023)", "governance_prefilter fires FAIL on a corrupt Σ' store",
       _gp["verdict"] == "FAIL" and _gp["detail"]["n_regressions"] > 0, f"n_reg={_gp['detail']['n_regressions']}")
except Exception as e:
    ok("HANDOFF (R1/ADR-0023)", "governance_prefilter functional", False, f"{type(e).__name__}: {e}")

# (offline) squidiff Mode 0 — runs + deterministic by seed
try:
    _sf = REPO / "skills" / "custom" / "squidiff-in-silico-gate" / "scripts" / "synthetic_fallback.py"
    _o1 = str(Path(tempfile.mkdtemp()) / "s1.json"); _o2 = str(Path(tempfile.mkdtemp()) / "s2.json")
    for _o in (_o1, _o2):
        subprocess.run([sys.executable, str(_sf), "--operation", "addition", "--system", "pronephros",
                        "--seed", "42", "--out", _o], capture_output=True, text=True)
    _m1 = json.loads(Path(_o1).read_text()); _m2 = json.loads(Path(_o2).read_text())
    _keys = ("pearson_r", "r_squared", "delta_zsem_norm", "directional_accuracy_top20_de")
    _det = all(_m1.get(k) == _m2.get(k) for k in _keys)
    ok("SCOPE §5 (squidiff)", "squidiff Mode 0 runs + deterministic by seed (metrics identical)",
       _det and _m1.get("mode") == "0_synthetic_proxy", f"deterministic={_det}")
except Exception as e:
    ok("SCOPE §5 (squidiff)", "squidiff Mode 0 runs + deterministic", False, f"{type(e).__name__}: {e}")

# (offline, dep-gated) ingest_service HUMAN GATE — submit parks a proposal; only ADMIN may /approve.
# Verifies the gate mechanism (CLAUDE.md §7) WITHOUT mutating the DI: submit/pending/401 never touch Neo4j.
try:
    import importlib.util as _ilu
    if _ilu.find_spec("fastapi") is None:
        skip("HANDOFF (ADR-0021, gate)", "ingest_service human gate (submit->401 on non-admin approve)",
             "fastapi not installed (service dep) — pip install fastapi to run")
    else:
        _qd = tempfile.mkdtemp(prefix="ingest_q_")
        os.environ.setdefault("INGEST_SUBMIT_TOKEN", "smoke-submit")
        os.environ.setdefault("INGEST_ADMIN_TOKEN", "smoke-admin")
        os.environ["INGEST_QUEUE_DIR"] = _qd
        sys.path.insert(0, str(REPO / "rag_index" / "ingest_service"))
        from starlette.testclient import TestClient as _TC
        import app as _svc
        _c = _TC(_svc.app)
        _sub = _c.post("/submit", headers={"Authorization": "Bearer smoke-submit"},
                       data={"name": "smoke", "source_db": "smoke", "niche": "N3",
                             "url": "https://example.org/smoke.txt"})
        _sid = _sub.json().get("submission_id")
        _bad = _c.post(f"/approve/{_sid}?by=smoke", headers={"Authorization": "Bearer smoke-submit"})
        ok("HANDOFF (ADR-0021, gate)", "ingest_service: submit parks + non-admin /approve -> 401 (human gate)",
           _sub.status_code == 200 and _bad.status_code == 401, f"submit={_sub.status_code} approve_as_submit={_bad.status_code}")
except Exception as e:
    ok("HANDOFF (ADR-0021, gate)", "ingest_service human gate", False, f"{type(e).__name__}: {e}")
# NOTE: the mutating /approve (MERGE into live Neo4j) is intentionally NOT run here — it is a human-gated
# DI mutation (CLAUDE.md §7). Verified live in-session (2026-07-05) up to the gate; MERGE is idempotent /
# never-deletes by construction (see the ingest.py DELETE-count check above).

# (live-gated) MinIO raw-store round-trip
if LIVE and os.environ.get("MINIO_ENDPOINT"):
    try:
        from lib import raw_store as _RS
        import urllib.request as _url
        _f = str(Path(tempfile.mkdtemp()) / "smoke.txt"); _pl = b"smoke-contract minio round-trip"
        Path(_f).write_bytes(_pl); _shal = hashlib.sha256(_pl).hexdigest()
        _RS.ensure_bucket(); _ref = _RS.put(_f, key="sandbox/smoke_contract.txt", content_type="text/plain")
        _got = _url.urlopen(_RS.presign(_ref, 300), timeout=30).read()
        _RS._client().remove_object(_ref["bucket"], _ref["key"])
        ok("HANDOFF (ADR-0021)", "MinIO put->presign->download->sha256 round-trip",
           hashlib.sha256(_got).hexdigest() == _shal)
    except Exception as e:
        ok("HANDOFF (ADR-0021)", "MinIO raw-store round-trip", False, f"{type(e).__name__}: {e}")
else:
    skip("HANDOFF (ADR-0021)", "MinIO raw-store round-trip", "set SMOKE_CONTRACT_LIVE=1 + MINIO_* env")

# (live-gated) Neo4j retrieval + answer_pipeline both branches
if LIVE and os.environ.get("RAG_BACKEND") == "neo4j":
    try:
        from lib import rag_backend as _RB
        _hits = _RB.query("zebrafish pronephros induction", k=3)
        ok("HANDOFF (ADR-0020)", "live Neo4j semantic retrieval returns hits", len(_hits) > 0, f"hits={len(_hits)}")
        from lib import answer_pipeline as _AP
        _di = _AP.retrieve("What TFs mark the zebrafish pronephros?", entities=["pax2a", "wt1a"], n_papers=0)
        _fb = _AP.retrieve("CRISPR base editing in adult cardiac fibrosis?", entities=["notagene_xyz"], n_papers=0)
        ok("HANDOFF (ADR-0022)", "answer_pipeline DI-sufficient -> DI_SUFFICIENT",
           _di["decision_state"]["state"] == "DI_SUFFICIENT")
        ok("HANDOFF (ADR-0022)", "answer_pipeline DI-insufficient -> FALLBACK_FETCHED (audit required)",
           _fb["decision_state"]["state"] == "FALLBACK_FETCHED" and _fb["decision_state"]["may_answer_now"] is False)
    except Exception as e:
        ok("HANDOFF (ADR-0020/0022)", "live Neo4j + answer_pipeline", False, f"{type(e).__name__}: {e}")
else:
    skip("HANDOFF (ADR-0020/0022)", "live Neo4j retrieval + answer_pipeline branches",
         "set SMOKE_CONTRACT_LIVE=1 + RAG_BACKEND=neo4j + secrets")

# Path B execute_tool is a session-MCP capability, not a python API — exercised in-session, noted here.
skip("HANDOFF (ADR-0026)", "Tool Universe Path B (execute_tool) live",
     "MCP session capability — exercised via the agent session (Reactome enrichment), not this script")

# ---------------------------------------------------------------------------
_section("INVARIANT — this smoke mutated nothing")
_sha_end = hashlib.sha256(STORE_PATH.read_bytes()).hexdigest()
ok("ALL", "DATA INAMOVIBLE unchanged by this run (read-and-report)", _sha_start == _sha_end, _sha_end[:16])

# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Contract-level smoke test vs CLAUDE/SCOPE/HANDOFF.")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--strict", action="store_true", help="SKIP (needs-live) also fails")
    args = ap.parse_args()

    n_pass = sum(1 for _, _, s, _ in results if s == "PASS")
    n_fail = sum(1 for _, _, s, _ in results if s == "FAIL")
    n_skip = sum(1 for _, _, s, _ in results if s == "SKIP")
    n_info = sum(1 for _, _, s, _ in results if s == "INFO")
    print("\n" + "=" * 96)
    print(f"CONTRACT SMOKE: {n_pass} PASS · {n_fail} FAIL · {n_skip} SKIP(needs-live) · {n_info} INFO")
    print("Scope of proof: substrate MACHINERY behaves as documented. NOT proven here: the biological")
    print("objective (wet-lab only) and 'all five validation tests pass' (several are case-capture/open).")
    if n_fail:
        print("FAILURES:", [f"{d} :: {c}" for d, c, s, _ in results if s == "FAIL"])
    print("=" * 96)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "results": [{"doc_ref": d, "claim": c, "status": s, "detail": det} for d, c, s, det in results],
            "summary": {"PASS": n_pass, "FAIL": n_fail, "SKIP": n_skip, "INFO": n_info},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.json}")

    sys.exit(1 if (n_fail or (args.strict and n_skip)) else 0)


if __name__ == "__main__":
    main()
