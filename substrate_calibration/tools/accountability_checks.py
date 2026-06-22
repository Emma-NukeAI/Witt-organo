"""
accountability_checks.py — Turn §11 (agent invocation) and §4 (framework election) from REFLEX into
VERIFIABLE GATES (R3 · plan §3 / Pillars 2+3). Read-and-report; mutates nothing.

These are deterministic CHECKS over substrate-evidence outputs (claim records) — NOT learned selectors
(a learned framework/agent policy is MITAD_B, the generation engine). They make the existing matrix /
catalog enforceable:

  check_framework_citation(record)  — §4: framework_applied must cite a SPECIFIC catalog §section
    (e.g. "§5", "§8"), NOT a bare "Tier N" header (the documented §4 anti-pattern, failure_log
    `framework_miscited`), and SHOULD quote a criterion. Deterministic.

  check_agents_invoked(record)      — §11: the agents_invoked field is present + well-formed (valid
    status enum; skipped-ad-hoc carries a substantive, non-boilerplate reason), and the hard-rule
    work-types it can infer have their required agent present-or-justified.

ADDITIVE (plan): the coverage rules mirror `agent-invocation-matrix.md` §1/§2 as a small table — add a
matrix row ⇒ add one rule here; the checker enforces it without code change elsewhere. The matrix MD
stays the human-readable authority; this is its executable projection (and this checker is itself the
thing that catches drift between an output and the matrix).

Usage:
    python accountability_checks.py --records-dir ../records --output ../reports/accountability_YYYYMMDD.json
    python accountability_checks.py --record ../records/claim_....json
    python accountability_checks.py --selftest
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS_DIR))
from compute_ece import load_records  # noqa: E402  (reuse the record loader)

# §4: a specific catalog section like "§5" or "§ 8"; and the bare-tier anti-pattern.
_SECTION_RE = re.compile(r"§\s?\d")
_BARE_TIER_RE = re.compile(r"§?\s*\bTier\s*\d\b", re.I)
_QUOTE_RE = re.compile(r"[\"'“”].{6,}?[\"'“”]")

_VALID_STATUS = {"invoked", "skipped-ad-hoc", "not-applicable"}

# Coverage rules — the machine-checkable subset of agent-invocation-matrix.md §1/§2 (additive: add a row).
_COVERAGE = [
    {
        "work_type": "ranked_candidates",
        "required": "causal-pruner",
        "cite": "matrix §1 / CLAUDE.md §7.1",
        # category covers "ranking" and any "*pruner*"/"*generation*" category; text covers sufficiency/minimal-set
        # phrasings (incl. the legacy "is sufficient to induce" form the v1 keyword set missed).
        # category path (ranking / *pruner*/*generation*) = genuine candidate generation. The claim_text
        # keyword path is suppressed for `methodological` records: a tooling/meta claim that MENTIONS a
        # minimal-set (e.g. describing a projection) is NOT generating candidates — suppressing it removes
        # a real false-positive without weakening detection of biological generation (category path stays).
        "detect": lambda r: ("rank" in str(r.get("claim_category", "")).lower())
        or ("prun" in str(r.get("claim_category", "")).lower())
        or (str(r.get("claim_category", "")).lower() != "methodological" and any(
            k in (str(r.get("claim_text", "")).lower())
            for k in ("minimal set", "minimal-set", "minimal sufficient", "smallest sufficient",
                      "is sufficient to", "sufficient to induce", "sufficient set", "ranked candidate",
                      "sufficiency hypothesis", "prune over"))),
    },
    {
        "work_type": "substrate_audit",
        "required": "composite-auditor",
        "cite": "matrix §1 / CLAUDE.md §7",
        "detect": lambda r: any(
            k in (str(r.get("claim_text", "")) + " " + str(r.get("skill_origin", ""))).lower()
            for k in ("retrospective audit", "substrate-evidence audit", "audit gate over")
        ),
    },
]


def _invoked_agents(record):
    return {a.get("agent"): a for a in record.get("agents_invoked", []) if isinstance(a, dict)}


def check_framework_citation(record):
    """§4: framework_applied must cite a SPECIFIC catalog §section (not a bare 'Tier N'); criterion quoted.

    The authoritative field is `framework_applied` ONLY — a `framework_applied_corrected` retrofit on a
    legacy record is NOT honored (legacy ADR-0002 records stay FAIL by design = the forward-enforcement
    signal). The quoted-criterion check is PRESENCE-ONLY (it does not validate the quote against the cited
    section's text) and drives WARN vs PASS, never FAIL.
    """
    issues = []
    fw = record.get("framework_applied")
    if not fw:
        return {"check": "framework_citation", "level": "FAIL", "issues": ["framework_applied is absent"]}
    has_section = bool(_SECTION_RE.search(fw))
    bare_tier = bool(_BARE_TIER_RE.search(fw)) and not has_section
    has_quote = bool(_QUOTE_RE.search(fw))
    if bare_tier:
        issues.append("§4 anti-pattern: cites a bare 'Tier N' header, not a specific framework §section")
    if not has_section:
        issues.append("no specific catalog §section cited (expected e.g. '§5' / '§8')")
    if not has_quote:
        issues.append("no quoted criterion (§4 requires quoting the catalog criterion that justifies the choice)")
    level = "FAIL" if (bare_tier or not has_section) else ("WARN" if not has_quote else "PASS")
    return {"check": "framework_citation", "level": level, "framework_applied": fw[:120], "issues": issues}


def check_agents_invoked(record):
    """§11: field present + well-formed; hard-rule coverage for inferable work-types."""
    issues = []
    ai = record.get("agents_invoked")
    if ai is None:
        return {"check": "agents_invoked", "level": "FAIL", "issues": ["agents_invoked field absent (§11)"]}
    if not isinstance(ai, list) or not ai:
        return {"check": "agents_invoked", "level": "FAIL", "issues": ["agents_invoked is empty (§11)"]}

    for a in ai:
        if not isinstance(a, dict) or "agent" not in a or "status" not in a:
            issues.append(f"malformed entry (need agent+status): {str(a)[:60]}")
            continue
        if a["status"] not in _VALID_STATUS:
            issues.append(f"{a['agent']}: invalid status '{a['status']}' (must be {sorted(_VALID_STATUS)})")
        if a["status"] == "skipped-ad-hoc":
            reason = str(a.get("reason", "")).strip()
            if len(reason) < 20:
                issues.append(f"{a['agent']}: skipped-ad-hoc needs a substantive, non-boilerplate reason")

    invoked = _invoked_agents(record)
    coverage = []
    for rule in _COVERAGE:
        if rule["detect"](record):
            present = rule["required"] in invoked
            ok = present  # any status counts as 'addressed'; absence is the violation
            coverage.append({"work_type": rule["work_type"], "required": rule["required"],
                             "present": present, "cite": rule["cite"]})
            if not present:
                issues.append(f"work-type '{rule['work_type']}' detected but required agent "
                              f"'{rule['required']}' not in agents_invoked ({rule['cite']})")
            elif invoked[rule["required"]]["status"] == "not-applicable":
                issues.append(f"work-type '{rule['work_type']}' detected but '{rule['required']}' marked "
                              f"not-applicable — contradiction; justify or invoke ({rule['cite']})")
    level = "FAIL" if any("not in agents_invoked" in i or "absent" in i or "empty" in i for i in issues) \
        else ("WARN" if issues else "PASS")
    return {"check": "agents_invoked", "level": level, "coverage": coverage, "issues": issues}


def check_record(record):
    fw = check_framework_citation(record)
    ai = check_agents_invoked(record)
    worst = "FAIL" if "FAIL" in (fw["level"], ai["level"]) else ("WARN" if "WARN" in (fw["level"], ai["level"]) else "PASS")
    return {"claim_id": record.get("claim_id"), "verdict": worst, "framework_citation": fw, "agents_invoked": ai}


def run(records_dir):
    records = load_records(records_dir)
    results = [check_record(r) for r in records]
    by = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        by[r["verdict"]] += 1
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_records": len(records),
        "summary": by,
        "note": ("Read-and-report; mutates nothing. FAIL = a §4/§11 contract violation (e.g. bare-tier "
                 "framework citation, absent agents_invoked, or a hard-rule work-type missing its agent). "
                 "Legacy records (ADR-0002 immutable) may FAIL historically — surfaced, not modified."),
        "results": results,
    }


# --- self-test --------------------------------------------------------------------------------

_GOOD = {
    "claim_id": "selftest_good",
    "framework_applied": "Logic-LM (Symbolic Verification) — per reasoning-frameworks-catalog.md §5: "
                         "\"Problems where the answer must be provably correct, not just plausible\".",
    "claim_category": "methodological",
    "agents_invoked": [
        {"agent": "composite-auditor", "status": "invoked", "reason": "closing audit gate for substrate evidence"},
        {"agent": "causal-pruner", "status": "not-applicable", "reason": "no ranked biological candidates here"},
    ],
}
_BAD = {
    "claim_id": "selftest_bad",
    "framework_applied": "Tier 2 reasoning",   # the §4 anti-pattern: bare tier, no §section, no quote
    "claim_category": "ranking",               # ranked_candidates -> causal-pruner required
    "claim_text": "ranked candidate transcription factors / minimal set for pronephros",
    "agents_invoked": [
        {"agent": "reasoning-exposer", "status": "skipped-ad-hoc", "reason": "n/a"},  # reason too short
        # causal-pruner MISSING despite a ranked_candidates / minimal-set claim
    ],
}


def selftest():
    print("=== accountability_checks self-test (§4 framework + §11 agents_invoked) ===")
    g = check_record(_GOOD)
    b = check_record(_BAD)
    print(f"  GOOD: verdict={g['verdict']} | framework={g['framework_citation']['level']} | agents={g['agents_invoked']['level']}")
    print(f"  BAD : verdict={b['verdict']} | framework={b['framework_citation']['level']} {b['framework_citation']['issues']}")
    print(f"        agents={b['agents_invoked']['level']} {b['agents_invoked']['issues']}")
    ok = (g["verdict"] == "PASS" and b["verdict"] == "FAIL"
          and any("bare 'Tier" in i for i in b["framework_citation"]["issues"])
          and any("causal-pruner" in i for i in b["agents_invoked"]["issues"]))
    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: a compliant record PASSes; a bare-tier citation + a "
          f"ranked-candidates claim missing causal-pruner is caught as FAIL.")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe (matches answer_pipeline.py)
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--records-dir")
    p.add_argument("--record")
    p.add_argument("--output")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())
    if args.record:
        rec = json.loads(Path(args.record).read_text(encoding="utf-8"))
        print(json.dumps(check_record(rec), indent=2))
        return
    if not args.records_dir or not args.output:
        p.error("--records-dir + --output (or --record, or --selftest) required")
    report = run(args.records_dir)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}: {report['summary']} over {report['n_records']} records")


if __name__ == "__main__":
    main()
