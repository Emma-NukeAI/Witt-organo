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
_SECTION_NUM_RE = re.compile(r"§\s?(\d+)")
_BARE_TIER_RE = re.compile(r"§?\s*\bTier\s*\d\b", re.I)
_QUOTE_RE = re.compile(r"[\"'“”‘’].{6,}?[\"'“”‘’]")
_QUOTE_CAP = re.compile(r"[\"'“”‘’](.{6,}?)[\"'“”‘’]")

# N6 (ADR-0027): validate the quoted criterion against the ACTUAL catalog text — the §4 contract's
# substantive half. The catalog is parsed into {section_num: body} so a quote can be checked against the
# CITED section, vs. found-elsewhere-in-catalog, vs. not-in-catalog-at-all (fabricated).
_CATALOG_PATH = (Path(__file__).resolve().parents[2] / "skills" / "custom"
                 / "organogenesis-agent-architect" / "references" / "reasoning-frameworks-catalog.md")
_SECTION_HDR_RE = re.compile(r"^#{2,4}\s+(\d+)\.\s+(.+)$", re.M)
_MIN_QUOTE_LEN = 20   # a MEANINGFUL criterion; shorter quoted spans (e.g. "the answer") are ignored (ADR-0027 close)
_catalog_cache = None


def _norm(s):
    """Lowercase + collapse all whitespace — robust substring matching across line wraps / spacing."""
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def _load_catalog():
    """Return ({section_num(str): normalized_body}, normalized_full_text). Cached. Safe on missing file:
    returns ({}, '') so N6 degrades to presence-only (never crashes, never false-FAILs on a load error).

    ADR-0027 close: each section's body is augmented with any INTRO summary-table line (the bullets before
    the first '### N.' header) that NAMES this framework — so a verbatim one-line summary of the cited
    framework (e.g. the CoVe bullet at the top) validates against the section it actually describes, rather
    than being demoted to 'elsewhere'."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    sections, full = {}, ""
    try:
        raw = _CATALOG_PATH.read_text(encoding="utf-8")
        full = _norm(raw)
        hdrs = list(_SECTION_HDR_RE.finditer(raw))
        preamble_lines = [ln for ln in (raw[:hdrs[0].start()] if hdrs else raw).splitlines() if ln.strip()]
        for i, m in enumerate(hdrs):
            num = m.group(1)
            name = re.split(r"[—\-]", m.group(2))[0].strip()        # framework name, before the Tier dash
            end = hdrs[i + 1].start() if i + 1 < len(hdrs) else len(raw)
            name_norm = _norm(name)
            intro = " ".join(ln for ln in preamble_lines if len(name_norm) >= 4 and name_norm in _norm(ln))
            sections[num] = _norm(raw[m.start():end] + " " + intro)
    except Exception:
        sections, full = {}, ""
    _catalog_cache = (sections, full)
    return _catalog_cache


def _validate_quote(fw):
    """N6: classify the quoted criterion against the catalog. Returns one of:
    'validated' (a meaningful quote ∈ cited §N body or its intro line) | 'elsewhere' (∈ catalog but outside
    §N) | 'not_in_catalog' (fabricated) | 'no_catalog' (file unavailable → skip) | 'no_quote' (no MEANINGFUL
    quoted span).

    ADR-0027 close: scans ALL quoted spans, not just the first (a legitimate record may carry an aside quote
    before the genuine criterion — first-only would false-FAIL it), and ignores spans below _MIN_QUOTE_LEN
    (a trivial 6-char quote that incidentally exists in the catalog must NOT validate)."""
    quotes = [q for q in _QUOTE_CAP.findall(fw) if len(_norm(q)) >= _MIN_QUOTE_LEN]
    if not quotes:
        return "no_quote"
    sections, full = _load_catalog()
    if not full:
        return "no_catalog"
    qn = [_norm(q) for q in quotes]
    sm = _SECTION_NUM_RE.search(fw)
    num = sm.group(1) if sm else None
    if num and num in sections and any(q in sections[num] for q in qn):
        return "validated"
    if any(q in full for q in qn):
        return "elsewhere"
    return "not_in_catalog"

_VALID_STATUS = {"invoked", "skipped-ad-hoc", "not-applicable"}
_ADDRESSED = {"invoked", "skipped-ad-hoc"}   # present + genuinely accounted-for (vs not-applicable)

# W2/N3 fix (ADR-0027): generation is detected from VERIFIABLE STRUCTURE, never from a self-declared
# claim_category used as a SUPPRESSOR (the old `!= 'methodological'` hole let a mislabel evade entirely).
# STRONG signal (→ causal-pruner REQUIRED, FAIL if absent/not-applicable): the category positively
# self-identifies as generation (rank/prun/generation), OR the output carries a structured candidate set.
# WEAK signal (→ advisory WARN only, and only when the agent is ABSENT): a mere sufficiency phrase in
# claim_text — ambiguous (a tooling/extraction record may legitimately MENTION a minimal-set), so it never
# FAILs and is suppressed to PASS when causal-pruner was explicitly addressed (invoked / skipped / N/A).
_CANDIDATE_FIELD_KEYS = ("ranked_candidates", "candidate_set", "candidate_genes", "minimal_set",
                         "proposed_set", "sufficient_set", "tf_set", "tf_program", "gene_set",
                         "gene_list", "gene_program", "core_regulators", "candidates")
# ADR-0027 close: the category signal is TIGHTENED to BIOLOGICAL candidate-generation phrasings. The prior
# bare `prun`/`generation` substrings over-fired on governance ('pruning-proposal' = DI orphan-node pruning)
# and tooling ('report-generation', 'data-generation-tooling'). The legacy generation record
# (claim_20260514_143000, category 'pruner-generation-ad-hoc') still matches via 'pruner-generation'.
_GEN_CATEGORY_RE = re.compile(r"\brank|pruner-generation|candidate-generation|sufficiency|"
                              r"\btf[- ]?set|gene[- ]?set|minimal[- ]?set", re.I)
_GEN_TEXT_KEYS = ("minimal set", "minimal-set", "minimal sufficient", "smallest sufficient",
                  "smallest set", "smallest collection", "is sufficient to", "sufficient to induce",
                  "sufficient set", "ranked candidate", "sufficiency hypothesis", "prune over",
                  "specifies renal", "establishes renal", "sufficient to specify", "sufficient to establish",
                  "able to drive", "core regulators", "core transcription factors")
_AUDIT_TEXT_KEYS = ("retrospective audit", "substrate-evidence audit", "audit gate over")
# A gene-symbol-like token (lowercase, short) — so a candidate FIELD holding repository/tool NAMES
# (e.g. ['PRIDE','MassIVE']) does NOT trip generation detection (ADR-0027 close, auditor-2 over-fire).
_GENE_SYMBOL_RE = re.compile(r"^[a-z][a-z0-9.\-]{1,14}$")


def _has_structured_candidates(r):
    """True iff a recognized candidate FIELD holds >=2 GENE-SYMBOL-LIKE items (not repository/tool names)."""
    for k in _CANDIDATE_FIELD_KEYS:
        v = r.get(k)
        if isinstance(v, (list, tuple)):
            genes = [x for x in v if isinstance(x, str) and _GENE_SYMBOL_RE.match(x.strip())]
            if len(genes) >= 2:
                return True
    return False


def _gen_strong(r):
    return bool(_GEN_CATEGORY_RE.search(str(r.get("claim_category", "")))) or _has_structured_candidates(r)


def _gen_weak(r):
    t = str(r.get("claim_text", "")).lower()
    return any(k in t for k in _GEN_TEXT_KEYS)


def _audit_strong(r):
    blob = (str(r.get("claim_text", "")) + " " + str(r.get("skill_origin", ""))).lower()
    return any(k in blob for k in _AUDIT_TEXT_KEYS)


# Coverage rules — the machine-checkable subset of agent-invocation-matrix.md §1/§2 (additive: add a row).
# Each rule: strong/weak detectors. strong => hard requirement; weak => advisory-only.
_COVERAGE = [
    {"work_type": "ranked_candidates", "required": "causal-pruner", "cite": "matrix §1 / CLAUDE.md §7.1",
     "strong": _gen_strong, "weak": _gen_weak},
    {"work_type": "substrate_audit", "required": "composite-auditor", "cite": "matrix §1 / CLAUDE.md §7",
     "strong": _audit_strong, "weak": lambda r: False},
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

    # bare-tier / no-section remain the hard FAIL (unchanged). When the citation IS well-formed, N6
    # validates the quoted criterion against the catalog text.
    if bare_tier or not has_section:
        return {"check": "framework_citation", "level": "FAIL", "framework_applied": fw[:120],
                "quote_validation": None, "issues": issues}

    qv = _validate_quote(fw)
    # N6: a quote that is NOT anywhere in the catalog is a FABRICATED criterion -> FAIL. A quote found in
    # the catalog but OUTSIDE the cited §N (paraphrase / mis-attribution) -> WARN. Validated -> PASS.
    # 'no_catalog' (file unavailable) degrades to presence-only: PASS (with note), never a false FAIL.
    if qv == "not_in_catalog":
        issues.append("§4/N6: quoted criterion is NOT found anywhere in the catalog — fabricated quote")
        level = "FAIL"
    elif qv == "elsewhere":
        issues.append("§4/N6: quoted criterion exists in the catalog but NOT in the cited §section "
                      "(paraphrase or mis-attribution — composite-auditor should confirm)")
        level = "WARN"
    elif qv == "no_quote":
        level = "WARN"   # no quoted criterion (issue already appended above)
    elif qv == "no_catalog":
        issues.append("§4/N6: catalog unavailable — quote not validated (presence-only)")
        level = "PASS"
    else:  # validated
        level = "PASS"
    return {"check": "framework_citation", "level": level, "framework_applied": fw[:120],
            "quote_validation": qv, "issues": issues}


def check_agents_invoked(record):
    """§11: field present + well-formed; hard-rule coverage for inferable work-types.

    Coverage (ADR-0027): a STRONG generation signal (self-declared rank/prun/generation category OR a
    structured candidate set) makes causal-pruner a HARD requirement — absent OR marked not-applicable is
    a FAIL (W1: a not-applicable on a strongly-detected work-type is a contradiction, not a soft WARN). A
    WEAK signal (a sufficiency phrase in claim_text) is advisory: WARN only when the agent is ABSENT, and
    PASS when the producer addressed it (invoked / skipped-ad-hoc / not-applicable) — so a tooling/extraction
    record that merely MENTIONS a minimal-set is not falsely failed, while a self-declared category can no
    longer SUPPRESS detection (the old W2/N3 hole)."""
    fail_issues, warn_issues = [], []
    ai = record.get("agents_invoked")
    if ai is None:
        return {"check": "agents_invoked", "level": "FAIL", "issues": ["agents_invoked field absent (§11)"]}
    if not isinstance(ai, list) or not ai:
        return {"check": "agents_invoked", "level": "FAIL", "issues": ["agents_invoked is empty (§11)"]}

    for a in ai:
        if not isinstance(a, dict) or "agent" not in a or "status" not in a:
            warn_issues.append(f"malformed entry (need agent+status): {str(a)[:60]}")
            continue
        if a["status"] not in _VALID_STATUS:
            warn_issues.append(f"{a['agent']}: invalid status '{a['status']}' (must be {sorted(_VALID_STATUS)})")
        if a["status"] == "skipped-ad-hoc":
            reason = str(a.get("reason", "")).strip()
            if len(reason) < 20:
                warn_issues.append(f"{a['agent']}: skipped-ad-hoc needs a substantive, non-boilerplate reason")

    invoked = _invoked_agents(record)
    coverage = []
    for rule in _COVERAGE:
        strong = bool(rule["strong"](record))
        weak_only = (not strong) and bool(rule["weak"](record))
        if not (strong or weak_only):
            continue
        present = rule["required"] in invoked
        status = invoked[rule["required"]]["status"] if present else None
        coverage.append({"work_type": rule["work_type"], "required": rule["required"], "present": present,
                         "status": status, "signal": "strong" if strong else "weak", "cite": rule["cite"]})
        if strong:
            if not present:
                fail_issues.append(f"work-type '{rule['work_type']}' (strong signal) but required agent "
                                   f"'{rule['required']}' not in agents_invoked ({rule['cite']})")
            elif status == "not-applicable":
                fail_issues.append(f"work-type '{rule['work_type']}' (strong signal) but '{rule['required']}' "
                                   f"marked not-applicable — contradiction; invoke or justify as a different "
                                   f"work-type ({rule['cite']})")
        else:  # weak-only: advisory
            if not present:
                warn_issues.append(f"possible '{rule['work_type']}' (weak signal in claim_text) and "
                                   f"'{rule['required']}' is absent — confirm not generation, or invoke/skip "
                                   f"it ({rule['cite']})")
    level = "FAIL" if fail_issues else ("WARN" if warn_issues else "PASS")
    return {"check": "agents_invoked", "level": level, "coverage": coverage,
            "issues": fail_issues + warn_issues}


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


# --- ADR-0027 hardening fixtures ---------------------------------------------------------------
_FW_OK = ("Logic-LM (Symbolic Verification) — per reasoning-frameworks-catalog.md §5: "
          "\"Problems where the answer must be provably correct, not just plausible\".")
# W1: a STRONG (category) generation claim that marks causal-pruner not-applicable -> §11 FAIL (was WARN).
_W1 = {"claim_id": "selftest_w1", "framework_applied": _FW_OK, "claim_category": "ranking",
       "claim_text": "ranked candidate TFs",
       "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable",
                           "reason": "we only enumerated them, did not run a real prune"}]}
# W2/N3: a generation claim mislabeled 'methodological' but carrying a STRUCTURED candidate set ->
# strong via structure (category can no longer SUPPRESS) -> §11 FAIL.
_W2 = {"claim_id": "selftest_w2", "framework_applied": _FW_OK, "claim_category": "methodological",
       "claim_text": "the set is sufficient to induce pronephros", "minimal_set": ["osr1", "pax2a", "lhx1a"],
       "agents_invoked": [{"agent": "reasoning-exposer", "status": "invoked",
                           "reason": "exposed the generation reasoning chain for substrate capture"}]}
# WEAK-only: a tooling/meta record that merely MENTIONS a minimal-set, with causal-pruner addressed
# (not-applicable + substantive reason) -> PASS (no over-fire; the skip-with-justification is honored).
_WEAK = {"claim_id": "selftest_weak", "framework_applied": _FW_OK, "claim_category": "methodological",
         "claim_text": "this tooling record mentions a minimal set only to DESCRIBE the WSTS projection",
         "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable",
                             "reason": "a meta/tooling record describing a minimal-set hypothesis; it generates no candidates"}]}
# N6: a fabricated quote under a valid §section -> framework FAIL (quote not in the catalog at all).
_N6 = {"claim_id": "selftest_n6", "claim_category": "methodological",
       "framework_applied": "Logic-LM — per reasoning-frameworks-catalog.md §5: "
                            "\"this exact criterion text appears nowhere in the catalog\".",
       "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable",
                           "reason": "no substrate-evidence audit performed in this fixture"}]}
# ADR-0027 CLOSE fixtures (from the closing composite-audit's constructed bypasses/over-fires):
# N6 multi-quote — an aside quote BEFORE the genuine §5 criterion must still VALIDATE (no first-quote-only false-FAIL).
_N6_MULTI = {"claim_id": "selftest_n6_multi", "claim_category": "methodological",
             "framework_applied": "Logic-LM — per reasoning-frameworks-catalog.md §5: I picked it because "
                                  "\"it felt right\" and per the catalog \"Problems where the answer must be "
                                  "provably correct, not just plausible\".",
             "agents_invoked": [{"agent": "composite-auditor", "status": "not-applicable",
                                 "reason": "no substrate-evidence audit performed in this fixture"}]}
# governance pruning (DI orphan-node pruning) is NOT biological candidate generation -> must NOT demand causal-pruner.
_GOV = {"claim_id": "selftest_gov", "framework_applied": _FW_OK, "claim_category": "pruning-proposal",
        "claim_text": "propose pruning orphan nodes from the DATA INAMOVIBLE graph",
        "agents_invoked": [{"agent": "composite-auditor", "status": "invoked",
                            "reason": "closing audit for the pruning-proposal substrate evidence"}]}
# a candidate FIELD holding repository NAMES (not gene symbols) must NOT trip generation detection.
_REPO = {"claim_id": "selftest_repo", "framework_applied": _FW_OK, "claim_category": "extraction",
         "candidates": ["PRIDE", "MassIVE"], "claim_text": "located two proteomic repositories",
         "agents_invoked": [{"agent": "causal-pruner", "status": "not-applicable",
                             "reason": "locating data repositories, not generating biological candidates"}]}


def selftest():
    print("=== accountability_checks self-test (§4 framework + §11 agents_invoked + ADR-0027 hardening) ===")
    g = check_record(_GOOD)
    b = check_record(_BAD)
    w1 = check_record(_W1)
    w2 = check_record(_W2)
    weak = check_record(_WEAK)
    n6 = check_framework_citation(_N6)
    n6m = check_framework_citation(_N6_MULTI)
    gov = check_agents_invoked(_GOV)
    repo = check_agents_invoked(_REPO)
    print(f"  GOOD : verdict={g['verdict']} fw={g['framework_citation']['level']}(qv={g['framework_citation'].get('quote_validation')}) agents={g['agents_invoked']['level']}")
    print(f"  BAD  : verdict={b['verdict']} fw={b['framework_citation']['level']} agents={b['agents_invoked']['level']}")
    print(f"  W1   : agents={w1['agents_invoked']['level']} (strong+not-applicable -> expect FAIL)")
    print(f"  W2/N3: agents={w2['agents_invoked']['level']} (methodological + structured candidate set -> expect FAIL)")
    print(f"  WEAK : agents={weak['agents_invoked']['level']} (weak mention + causal-pruner addressed -> expect PASS)")
    print(f"  N6   : fw={n6['level']} qv={n6.get('quote_validation')} (fabricated quote -> expect FAIL/not_in_catalog)")
    print(f"  N6multi: fw={n6m['level']} qv={n6m.get('quote_validation')} (aside + real §5 criterion -> expect PASS/validated)")
    print(f"  GOV  : agents={gov['level']} (governance pruning -> expect NOT FAIL)")
    print(f"  REPO : agents={repo['level']} (repository names in candidates -> expect NOT FAIL)")
    ok = (g["verdict"] == "PASS" and g["framework_citation"].get("quote_validation") == "validated"
          and b["verdict"] == "FAIL"
          and any("bare 'Tier" in i for i in b["framework_citation"]["issues"])
          and any("causal-pruner" in i for i in b["agents_invoked"]["issues"])
          and w1["agents_invoked"]["level"] == "FAIL"
          and w2["agents_invoked"]["level"] == "FAIL"
          and weak["agents_invoked"]["level"] == "PASS"
          and n6["level"] == "FAIL" and n6.get("quote_validation") == "not_in_catalog"
          and n6m["level"] == "PASS" and n6m.get("quote_validation") == "validated"
          and gov["level"] != "FAIL" and repo["level"] != "FAIL")
    print(f"\n  SELF-TEST {'PASS' if ok else 'FAIL'}: compliant record PASSes (catalog-VALIDATED quote); bare-tier "
          f"+ missing causal-pruner FAIL; W1 + W2/N3 FAIL; weak mention (agent addressed) PASSes; fabricated "
          f"quote FAILs (N6); an aside+real-criterion multi-quote VALIDATES (N6 close); governance-pruning + "
          f"repository-name candidates do NOT over-fire (ADR-0027 close).")
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
