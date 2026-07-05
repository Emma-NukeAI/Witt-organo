"""
doc_coherence_check.py — Deterministic doc↔repo coherence gate (Logic-LM-class, NOT an LLM).

The narrative documents (CLAUDE.md, PROJECT_SCOPE.md, README.md) repeat facts that actually live in
machine-readable sources of truth (the verified-identifier store, the ADR directory, the SKILL.md
frontmatter, the eval set). Those copies rot: the 2026-07 doc audit found CLAUDE.md still citing
"32 records" when the store held 51, README citing "8 ADRs" against 29 on disk, PROJECT_SCOPE closing
with "v1.0" while its header said v1.3. This check turns that class of drift from "discovered in an
audit" into "fails the commit".

Design (mirrors verify_output.py / accountability_checks.py): read-and-report, mutates NOTHING. Each
invariant names a SINGLE source of truth (SoT) and asserts every narrative doc that repeats it agrees.
Add an invariant ⇒ add one CHECKS entry; the source of truth stays the code/JSON, the docs stay
projections of it.

Exit code: 0 if no FAIL (WARN allowed); 1 if any FAIL; with --strict, WARN also fails. Intended as a
pre-commit hook AND a manual audit tool.

Usage:
    python doc_coherence_check.py                       # human-readable table, exit 0/1
    python doc_coherence_check.py --json report.json    # also write a JSON report
    python doc_coherence_check.py --strict              # WARN counts as failure
    python doc_coherence_check.py --selftest            # validate the parsers themselves
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:                                       # Windows console is cp1252; keep utf-8 on stdout (§ gotcha)
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]

# ---------- helpers ---------------------------------------------------------

def _read(rel):
    """Read a repo-relative text file as utf-8; '' if missing (a check then reports 'not found')."""
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _norm_ver(s):
    """Normalize a version token for comparison: strip a leading 'v', surrounding backticks/space."""
    return str(s).strip().strip("`").lstrip("vV").strip() if s is not None else None


def _first(pattern, text, group=1, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


def _result(name, sot_label, sot_value, refs, extra=None):
    """Build a check result. refs = [(doc, found_value_or_None)]. FAIL if any found value present and
    disagrees with SoT; WARN if a ref is missing entirely; PASS otherwise."""
    mism, missing = [], []
    for doc, found in refs:
        if found is None:
            missing.append(doc)
        elif str(found) != str(sot_value):
            mism.append((doc, found))
    status = "FAIL" if mism else ("WARN" if missing else "PASS")
    return {
        "check": name,
        "status": status,
        "source_of_truth": {"where": sot_label, "value": sot_value},
        "mismatches": [{"doc": d, "found": f, "expected": sot_value} for d, f in mism],
        "missing_refs": missing,
        "detail": extra or "",
    }


# ---------- individual invariants ------------------------------------------

def check_store_records():
    store = json.loads(_read("analysis/outputs/verified_identifiers.json") or "{}")
    sot = store.get("n_records")
    claude = _read("CLAUDE.md")
    # count cited next to the store token, tolerant to markdown bold: "... (**51 records** ...)"
    line = _first(r"verified-identifier-store@[^\n]*", claude, 0) or ""
    cited = _first(r"\*{0,2}(\d+)\s+records", line)
    return _result("store_record_count", "verified_identifiers.json:n_records", sot,
                   [("CLAUDE.md §12", int(cited) if cited else None)],
                   extra="count of records in the DATA INAMOVIBLE store")


def check_store_version():
    store = json.loads(_read("analysis/outputs/verified_identifiers.json") or "{}")
    sot = store.get("store_version")
    claude = _read("CLAUDE.md")
    cited = _first(r"verified-identifier-store@([0-9A-Za-z.\-]+)", claude)
    return _result("store_version", "verified_identifiers.json:store_version", sot,
                   [("CLAUDE.md §12", cited)],
                   extra="store_version string")


def check_highest_adr():
    nums = sorted(int(m.group(1)) for p in (ROOT / "docs" / "decisions").glob("*.md")
                  for m in [re.match(r"(\d{4})-", p.name)] if m)
    sot = f"{nums[-1]:04d}" if nums else None
    claude = _read("CLAUDE.md")
    cited = sorted(set(re.findall(r"ADR-(\d{4})", claude)))
    highest_cited = cited[-1] if cited else None
    # FAIL if the highest ADR on disk is NOT referenced anywhere in CLAUDE.md
    found = sot if (sot and sot in cited) else (highest_cited if highest_cited else None)
    return _result("highest_adr_referenced", "docs/decisions/ (max filename)", sot,
                   [("CLAUDE.md", found)],
                   extra=f"highest ADR cited anywhere in CLAUDE.md = {highest_cited}")


def check_scope_version():
    scope = _read("PROJECT_SCOPE.md")
    sot = _norm_ver(_first(r"\*\*Version:\*\*\s*([0-9.]+)", scope))
    footer = _norm_ver(_first(r"End of master scope document v?([0-9.]+)", scope))
    claude = _norm_ver(_first(r"PROJECT_SCOPE@([0-9.]+)", _read("CLAUDE.md")))
    readme = _norm_ver(_first(r"PROJECT_SCOPE\.md`?\s*v([0-9.]+)", _read("README.md")))
    return _result("scope_version", "PROJECT_SCOPE.md header **Version:**", sot,
                   [("PROJECT_SCOPE.md footer", footer),
                    ("CLAUDE.md §12", claude),
                    ("README.md", readme)],
                   extra="PROJECT_SCOPE version agreement across docs")


def check_skill_version():
    skill = _read("skills/custom/organogenesis-agent-architect/SKILL.md")
    sot = _norm_ver(_first(r"^\s*version:\s*([0-9.]+)", skill, flags=re.M))
    claude = _norm_ver(_first(r"organogenesis-agent-architect@([0-9.]+)", _read("CLAUDE.md")))
    readme = _norm_ver(_first(r"organogenesis-agent-architect`?\s*v([0-9.]+)", _read("README.md")))
    return _result("skill_version", "SKILL.md frontmatter version:", sot,
                   [("CLAUDE.md §12", claude), ("README.md", readme)],
                   extra="organogenesis-agent-architect version agreement")


def check_readme_adr_count():
    nums = [1 for p in (ROOT / "docs" / "decisions").glob("*.md") if re.match(r"\d{4}-", p.name)]
    sot = len(nums)
    readme = _read("README.md")
    cited = _first(r"(\d+)\s+records\s+as\s+of", readme)  # "; 29 records as of 2026-06 (…)"
    return _result("readme_adr_count", "count of docs/decisions/*.md", sot,
                   [("README.md repo-map", int(cited) if cited else None)],
                   extra="ADR count claimed in README repo map")


def check_eval_set_count():
    data = json.loads(_read("evaluation/held_out_set_v1.json") or "{}")
    items = data.get("questions", data) if isinstance(data, dict) else data
    sot = len(items) if items is not None else None
    claude = _first(r"held_out_set_v1\.json\D{0,4}(\d+)\s*q", _read("CLAUDE.md"))
    return _result("eval_set_count", "held_out_set_v1.json (item count)", sot,
                   [("CLAUDE.md §12", int(claude) if claude else None)],
                   extra="held-out eval set size cited vs actual (scope TARGET is 60–80 — tracked separately)")


CHECKS = [
    check_store_records, check_store_version, check_highest_adr,
    check_scope_version, check_skill_version, check_readme_adr_count,
    check_eval_set_count,
]

# ---------- runner ----------------------------------------------------------

def run():
    return [c() for c in CHECKS]


def _selftest():
    """Validate the parsers on synthetic strings — no repo state involved."""
    assert _norm_ver("`v1.3`") == "1.3"
    assert _norm_ver("V2.3.0") == "2.3.0"
    assert _first(r"@([0-9.\-]+)", "store@2026-06-23.1 (**51 records**)") == "2026-06-23.1"
    r = _result("t", "x", 5, [("a", 5), ("b", 4), ("c", None)])
    assert r["status"] == "FAIL" and r["mismatches"][0]["found"] == 4 and r["missing_refs"] == ["c"]
    r2 = _result("t", "x", 5, [("a", 5)])
    assert r2["status"] == "PASS"
    print("selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Deterministic doc↔repo coherence gate.")
    ap.add_argument("--json", metavar="PATH", help="write a JSON report to PATH")
    ap.add_argument("--strict", action="store_true", help="treat WARN as failure")
    ap.add_argument("--selftest", action="store_true", help="validate the parsers, then exit")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())

    results = run()
    n_fail = sum(r["status"] == "FAIL" for r in results)
    n_warn = sum(r["status"] == "WARN" for r in results)

    icon = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN"}
    print("doc↔repo coherence check\n" + "=" * 60)
    for r in results:
        print(f"[{icon[r['status']]}] {r['check']}")
        sot = r["source_of_truth"]
        print(f"        source of truth: {sot['where']} = {sot['value']!r}")
        for m in r["mismatches"]:
            print(f"        MISMATCH in {m['doc']}: found {m['found']!r}, expected {m['expected']!r}")
        if r["missing_refs"]:
            print(f"        reference not found in: {', '.join(r['missing_refs'])}")
    print("=" * 60)
    print(f"{len(results)} checks · {n_fail} FAIL · {n_warn} WARN")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"checks": results, "n_fail": n_fail, "n_warn": n_warn}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"wrote {args.json}")

    sys.exit(1 if (n_fail or (args.strict and n_warn)) else 0)


if __name__ == "__main__":
    main()
