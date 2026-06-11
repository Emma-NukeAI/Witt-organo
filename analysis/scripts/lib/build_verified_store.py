"""
build_verified_store.py — Build analysis/outputs/verified_identifiers.json
(DATA INAMOVIBLE v1) from the already-verified analysis/outputs/ensembl_symbol_map.json.

This is the SINGLE WRITER of the verified-identifier store. All other code opens the store
READ-ONLY (resolve_id.py). The store is "baseline-stable but human-gated mutable" (GWT v1.1
§3.2): a human runs this builder; it makes ZERO network calls (NO-SPEND) — it only
re-expresses already-verified/cached data in the verified-identifier schema (§6.1).

Provenance tiers for `raw_cache_ref` (GWT v1.1 §6.1, the anti-fabrication honesty design):
  RAW:<file>     — a §7.9-compliant raw external response is on disk. Applies to the 7 LBPP
                   anchors (cdh17, gata3, lhx1a, pax2a, pax8, wt1a, wt1b) that were
                   cross-checked against this map and cached in
                   raw_ensembl_lookup_genes_20260531.json
                   (see claim_20260531_190000_collaborator-zebrafish-lbpp.json).
  DERIVED:...    — resolved via the authoritative symbol-lookup pipeline (02_schoels_phase2.py)
                   but the individual raw response was NOT retained. Honestly weaker than RAW:
                   a verified project artifact, not a raw external response.
  ensdarg=null   — positive NOT_FOUND (we looked; the symbol does not resolve): clcnkb, slc12a1a.

Versioning (GWT v1.1 §6.1 + ADR-0002): a new store version never overwrites a prior one in
place. Before re-running with changed inputs, snapshot the prior store to
verified_identifiers.v<store_version>.json. Bump STORE_VERSION on every change.

Usage:  python analysis/scripts/lib/build_verified_store.py
"""
from pathlib import Path
import json

ANALYSIS = Path(__file__).resolve().parents[2]          # .../analysis
MAP_PATH = ANALYSIS / "outputs" / "ensembl_symbol_map.json"
OUT_PATH = ANALYSIS / "outputs" / "verified_identifiers.json"

# The 7 anchors the LBPP (2026-05-31) cross-checked against this map AND for which a raw
# Ensembl 3-hop response was cached per CLAUDE.md §6/§7.9.
RAW_ANCHORS = {"cdh17", "gata3", "lhx1a", "pax2a", "pax8", "wt1a", "wt1b"}
RAW_CACHE = "mcp_cache/raw_ensembl_lookup_genes_20260531.json"

SCHEMA_VERSION = "1.0"
STORE_VERSION = "2026-06-10.1"


def build():
    symbol_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    records = []
    for symbol in sorted(symbol_map):
        ensdarg = symbol_map[symbol]
        if ensdarg is not None and symbol in RAW_ANCHORS:
            raw_ref = f"RAW:{RAW_CACHE}"
            resolver = "ensembl-3hop"
            anchor_match = True
            verified_on = "2026-05-31"
            notes = "LBPP anchor: raw Ensembl 3-hop response cached; cross-checked vs this map."
        elif ensdarg is not None:
            raw_ref = "DERIVED:ensembl_symbol_map.json"
            resolver = "ensembl-symbol-lookup"
            anchor_match = None
            verified_on = None  # raw response not retained (DERIVED tier); date unknown
            notes = ("DERIVED: resolved via 02_schoels_phase2.py symbol-lookup; raw external "
                     "response not retained. Backlog: re-verify with raw caching to promote to RAW.")
        else:
            raw_ref = "DERIVED:ensembl_symbol_map.json"
            resolver = "ensembl-symbol-lookup"
            anchor_match = None
            verified_on = None
            notes = "positive NOT_FOUND: symbol does not resolve to an ENSDARG via Ensembl symbol-lookup."
        records.append({
            "symbol": symbol,
            "ensdarg": ensdarg,
            "ensdarp": None,
            "ensdart": None,
            "uniprot_acc": None,
            "taxon": 7955,
            "assembly": "GRCz11",
            "ensembl_release": 111,
            "source_db": "ensembl",
            "resolver": resolver,
            "raw_cache_ref": raw_ref,
            "anchor_match": anchor_match,
            "verified_on": verified_on,
            "provenance": "ours",
            "confidence": 1.0 if ensdarg is not None else 0.0,
            "notes": notes,
        })
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "store_version": STORE_VERSION,
        "generated_by": "analysis/scripts/lib/build_verified_store.py",
        "source_artifacts": [
            "analysis/outputs/ensembl_symbol_map.json",
            "mcp_cache/raw_ensembl_lookup_genes_20260531.json",
        ],
        "read_only": True,
        "human_gate_required_to_modify": True,
        "n_records": len(records),
        "tier_legend": {
            "RAW:<file>": "raw §7.9 external response on disk (raw_cache_ref points to it)",
            "DERIVED:ensembl_symbol_map.json": "verified via 02_schoels_phase2.py symbol-lookup; raw response not retained",
            "ensdarg=null": "positive NOT_FOUND (looked up; symbol does not resolve)",
        },
        "records": records,
    }
    OUT_PATH.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    n_raw = sum(1 for r in records if str(r["raw_cache_ref"]).startswith("RAW:"))
    n_null = sum(1 for r in records if r["ensdarg"] is None)
    print(f"Wrote {OUT_PATH}")
    print(f"  {len(records)} records | {n_raw} RAW | {len(records) - n_raw - n_null} DERIVED | {n_null} NOT_FOUND")


if __name__ == "__main__":
    build()
