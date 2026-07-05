"""
store_integrity_scan.py — Error-in-store detection for the DATA INAMOVIBLE (read-and-report).

Answers the external-audit gap (Fable 5, 2026-07-05, rec 5): "the human gate protects ENTRY, not
PERSISTENCE — there is no mechanism to find an approved-but-wrong fact after the fact." This is that
mechanism: a periodic re-verification / contradiction scan over the verified-identifier store.

It NEVER mutates the store (CLAUDE.md §7: mutations are human-gated + specified). It emits findings and,
for anything actionable, a `pending_review` proposal a human can act on via the normal gated path.

Checks (deterministic, offline):
  E1 duplicate symbol            — same symbol appears in >1 record
  E2 ENSDARG collision           — one ENSDARG mapped to >1 DISTINCT symbol (the 2026-06 wt1a-class bug)
  E3 malformed ENSDARG           — not matching ENSDARG\\d{11}
  E4 provenance incomplete       — RAW/DERIVED tier record missing raw_cache_ref or verified_on
  E5 stale                       — verified_on older than --stale-days (re-verification candidate; advisory)

Optional (network, opt-in): E6 live re-resolve a sample against Ensembl REST and flag symbol↔ENSDARG
mismatches. Off by default (NO-SPEND). Enable with --live-recheck N.

Usage:
    python store_integrity_scan.py                       # offline scan, table
    python store_integrity_scan.py --json ../reports/store_integrity_YYYYMMDD.json
    python store_integrity_scan.py --stale-days 120
    python store_integrity_scan.py --live-recheck 5      # re-resolve 5 records vs Ensembl (network)
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "analysis" / "outputs" / "verified_identifiers.json"
ENSDARG_RE = re.compile(r"^ENSDARG\d{11}$")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _days_since(d):
    try:
        return (date.today() - datetime.strptime(str(d)[:10], "%Y-%m-%d").date()).days
    except Exception:
        return None


def scan(stale_days=180):
    store = json.loads(STORE.read_text(encoding="utf-8"))
    recs = store.get("records", [])
    findings = []

    def add(code, severity, detail, symbols):
        findings.append({"code": code, "severity": severity, "detail": detail, "symbols": symbols})

    by_symbol, by_ensdarg = defaultdict(list), defaultdict(set)
    for r in recs:
        by_symbol[r.get("symbol")].append(r)
        if r.get("ensdarg"):
            by_ensdarg[r["ensdarg"]].add(r.get("symbol"))

    for sym, rs in by_symbol.items():
        if len(rs) > 1:
            add("E1_duplicate_symbol", "high", f"symbol '{sym}' appears in {len(rs)} records", [sym])
    for ens, syms in by_ensdarg.items():
        if len(syms) > 1:
            add("E2_ensdarg_collision", "critical",
                f"ENSDARG {ens} maps to {len(syms)} distinct symbols {sorted(syms)} (wt1a-class corruption)",
                sorted(syms))
    for r in recs:
        sym, ens = r.get("symbol"), r.get("ensdarg")
        if ens and not ENSDARG_RE.match(str(ens)):
            add("E3_malformed_ensdarg", "high", f"'{sym}' has malformed ENSDARG '{ens}'", [sym])
        tier = (r.get("tier") or "").upper()
        if ens and tier in ("RAW", "DERIVED"):
            if not r.get("raw_cache_ref"):
                add("E4_provenance_incomplete", "medium", f"'{sym}' ({tier}) missing raw_cache_ref", [sym])
            if not r.get("verified_on"):
                add("E4_provenance_incomplete", "medium", f"'{sym}' ({tier}) missing verified_on", [sym])
        ds = _days_since(r.get("verified_on"))
        if ds is not None and ds > stale_days:
            add("E5_stale", "low", f"'{sym}' verified {ds}d ago (> {stale_days}d re-verification candidate)", [sym])

    by_code = defaultdict(int)
    for f in findings:
        by_code[f["code"]] += 1
    proposals = [
        {"proposal_id": f"integrity-{f['code']}-{'_'.join(f['symbols'])[:40]}",
         "status": "pending_review", "action": "human-gated review; NEVER auto-fixed", "finding": f}
        for f in findings if f["severity"] in ("critical", "high")
    ]
    return {"n_records": len(recs), "store_version": store.get("store_version"),
            "findings": findings, "by_code": dict(by_code), "proposals": proposals}


def live_recheck(n):
    """Opt-in: re-resolve the n most-stale records against Ensembl REST; flag symbol↔ENSDARG mismatch.
    Network + tiny spend. Returns [] on any transport error (honest degrade, never crashes the scan)."""
    import urllib.request
    store = json.loads(STORE.read_text(encoding="utf-8"))
    recs = sorted(store.get("records", []), key=lambda r: str(r.get("verified_on", "")))[:n]
    out = []
    for r in recs:
        sym, ens = r.get("symbol"), r.get("ensdarg")
        if not sym or not ens:
            continue
        try:
            url = f"https://rest.ensembl.org/xrefs/symbol/danio_rerio/{sym}?content-type=application/json"
            data = json.loads(urllib.request.urlopen(url, timeout=20).read())
            live_ids = {x.get("id") for x in data if x.get("type") == "gene"}
            match = ens in live_ids
            out.append({"symbol": sym, "stored": ens, "live_ids": sorted(live_ids), "match": match})
        except Exception as e:
            out.append({"symbol": sym, "stored": ens, "error": f"{type(e).__name__}: {str(e)[:80]}"})
    return out


def main():
    ap = argparse.ArgumentParser(description="Error-in-store detection for the DATA INAMOVIBLE (read-and-report).")
    ap.add_argument("--stale-days", type=int, default=180)
    ap.add_argument("--live-recheck", type=int, default=0, metavar="N", help="re-resolve N records vs Ensembl (network)")
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()

    rep = scan(stale_days=args.stale_days)
    print(f"store integrity scan — {rep['n_records']} records @ {rep['store_version']}")
    print("=" * 66)
    if not rep["findings"]:
        print("  [CLEAN] no integrity findings")
    else:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for f in sorted(rep["findings"], key=lambda x: order.get(x["severity"], 9)):
            print(f"  [{f['severity']:>8}] {f['code']}: {f['detail']}")
    print("=" * 66)
    print("by_code:", rep["by_code"], "| pending_review proposals:", len(rep["proposals"]))

    if args.live_recheck:
        print("\nLIVE re-resolve vs Ensembl REST (opt-in):")
        for x in live_recheck(args.live_recheck):
            if "error" in x:
                print(f"  ? {x['symbol']}: {x['error']}")
            else:
                print(f"  {'OK ' if x['match'] else 'MISMATCH'} {x['symbol']} stored={x['stored']} live={x['live_ids']}")
            rep.setdefault("live_recheck", []).append(x)

    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.json}")
    # exit nonzero if any critical/high finding (usable as a periodic gate)
    sys.exit(1 if any(f["severity"] in ("critical", "high") for f in rep["findings"]) else 0)


if __name__ == "__main__":
    main()
