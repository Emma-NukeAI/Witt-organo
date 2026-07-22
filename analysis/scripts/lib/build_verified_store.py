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
OCULAR_CURATED = ANALYSIS / "outputs" / "ocular_markers_curated.json"
SIGNALING_CURATED = ANALYSIS / "outputs" / "signaling_markers_curated.json"
MITADB_CURATED = ANALYSIS / "outputs" / "mitadB_markers_curated.json"
S4_PENETRANCE_CURATED = ANALYSIS / "outputs" / "s4_penetrance_markers_curated.json"

# The 7 anchors the LBPP (2026-05-31) cross-checked against this map AND for which a raw
# Ensembl 3-hop response was cached per CLAUDE.md §6/§7.9.
RAW_ANCHORS = {"cdh17", "gata3", "lhx1a", "pax2a", "pax8", "wt1a", "wt1b"}
RAW_CACHE = "mcp_cache/raw_ensembl_lookup_genes_20260531.json"

SCHEMA_VERSION = "1.0"
STORE_VERSION = "2026-07-21.2"   # MITAD_A ZF-S4 penetrance acquisition: +3 ciliary penetrance-anchor IDs (mks1/tmem67/cep290) for the CORPUS-2026-0006 RN11 penetrance record; verified vs Ensembl REST, raw cached §7.9, human-gated ADD 2026-07-21. Prior: 2026-07-21.1 (+19, REQUEST_A_validate_DI); 2026-07-11.1 (ADR-0035, +23).


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
    # Merge curated ocular/corneal markers (curate_markers.py) as RAW rows — raw Ensembl REST lookup
    # cached per §7.9. Resolved markers only; NOT_FOUND ones stay in the curation file (needs_alias).
    existing = {r["symbol"] for r in records}
    if OCULAR_CURATED.exists():
        curated = json.loads(OCULAR_CURATED.read_text(encoding="utf-8"))
        for sym, c in sorted(curated.items()):
            if sym in existing or not c.get("ensdarg"):
                continue
            records.append({
                "symbol": sym, "ensdarg": c["ensdarg"], "ensdarp": None, "ensdart": None,
                "uniprot_acc": None, "taxon": 7955, "assembly": "GRCz11", "ensembl_release": 111,
                "source_db": "ensembl", "resolver": "ensembl-symbol-lookup",
                "raw_cache_ref": f"RAW:{c.get('raw_cache_ref')}", "anchor_match": None,
                "verified_on": c.get("verified_on"), "provenance": "ours", "confidence": 1.0,
                "refseq": c.get("refseq", []), "zfin": c.get("zfin"),
                "notes": "Ocular/corneal marker curated via Ensembl REST (raw lookup cached); for N5 / Test-5 work.",
            })

    # Merge pronephros upstream-signaling / induction markers (ADR-0029) — RAW tier (raw Ensembl REST
    # response cached per §7.9). Same single-writer + human-gate discipline as the ocular set; `existing`
    # is recomputed so an already-present symbol is never duplicated.
    existing = {r["symbol"] for r in records}
    if SIGNALING_CURATED.exists():
        curated = json.loads(SIGNALING_CURATED.read_text(encoding="utf-8"))
        for sym, c in sorted(curated.items()):
            if sym.startswith("_") or sym in existing or not isinstance(c, dict) or not c.get("ensdarg"):
                continue
            records.append({
                "symbol": sym, "ensdarg": c["ensdarg"], "ensdarp": None, "ensdart": None,
                "uniprot_acc": None, "taxon": 7955, "assembly": "GRCz11", "ensembl_release": None,
                "source_db": "ensembl", "resolver": "ensembl-rest-xrefs",
                "raw_cache_ref": f"RAW:{c.get('raw_cache_ref')}", "anchor_match": None,
                "verified_on": c.get("verified_on"), "provenance": "ours", "confidence": 1.0,
                "notes": ("Pronephros upstream-signaling / induction marker curated via Ensembl REST "
                          "(raw lookup cached 2026-06-23); for N3/N4 upstream-signal work (ADR-0029)."
                          + (f" Role: {c['role']}." if c.get("role") else "")),
            })

    # Merge MITAD_B question-bank markers (REQUEST_A_validate_DI_20260711) — RAW tier (raw Ensembl REST
    # response cached per §7.9 in raw_ensembl_mitadB-validate_20260721.json). Human-gated ADD approved by
    # Emmanuel 2026-07-21 (17 markers + both hif1a paralogs). Same single-writer discipline; `existing`
    # recomputed so an already-present symbol (e.g. bmp2b, ndr1/ndr2) is never duplicated.
    existing = {r["symbol"] for r in records}
    if MITADB_CURATED.exists():
        curated = json.loads(MITADB_CURATED.read_text(encoding="utf-8"))
        for sym, c in sorted(curated.items()):
            if sym.startswith("_") or sym in existing or not isinstance(c, dict) or not c.get("ensdarg"):
                continue
            records.append({
                "symbol": sym, "ensdarg": c["ensdarg"], "ensdarp": None, "ensdart": None,
                "uniprot_acc": None, "taxon": 7955, "assembly": "GRCz11", "ensembl_release": None,
                "source_db": "ensembl", "resolver": "ensembl-rest-lookup",
                "raw_cache_ref": f"RAW:{c.get('raw_cache_ref')}", "anchor_match": None,
                "verified_on": c.get("verified_on"), "provenance": "ours", "confidence": 1.0,
                "notes": ("MITAD_B question-bank marker verified via Ensembl REST (raw cached §7.9 "
                          "2026-07-21); human-gated ADD (REQUEST_A_validate_DI_20260711)."
                          + (f" Role: {c['role']}." if c.get("role") else "")),
            })

    # Merge S4 penetrance ciliary anchors (ZF-S4 penetrance acquisition) — RAW tier (raw Ensembl REST
    # response cached per §7.9 in raw_ensembl_S4-penetrance-ciliary_20260721.json). Human-gated ADD.
    # These 3 genes (mks1, tmem67, cep290) carry the quantified penetrance values extracted from
    # PMC9844136 (PMID 36533556) for the CORPUS-2026-0006 RN11 penetrance record. `existing` recomputed
    # so an already-present symbol is never duplicated.
    existing = {r["symbol"] for r in records}
    if S4_PENETRANCE_CURATED.exists():
        curated = json.loads(S4_PENETRANCE_CURATED.read_text(encoding="utf-8"))
        for sym, c in sorted(curated.items()):
            if sym.startswith("_") or sym in existing or not isinstance(c, dict) or not c.get("ensdarg"):
                continue
            records.append({
                "symbol": sym, "ensdarg": c["ensdarg"], "ensdarp": None, "ensdart": None,
                "uniprot_acc": None, "taxon": 7955, "assembly": "GRCz11", "ensembl_release": None,
                "source_db": "ensembl", "resolver": "ensembl-rest-lookup",
                "raw_cache_ref": f"RAW:{c.get('raw_cache_ref')}", "anchor_match": None,
                "verified_on": c.get("verified_on"), "provenance": "ours", "confidence": 1.0,
                "notes": ("ZF-S4 penetrance ciliary anchor verified via Ensembl REST (raw cached §7.9 "
                          "2026-07-21); human-gated ADD."
                          + (f" Role: {c['role']}." if c.get("role") else "")),
            })

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "store_version": STORE_VERSION,
        "generated_by": "analysis/scripts/lib/build_verified_store.py",
        "source_artifacts": [
            "analysis/outputs/ensembl_symbol_map.json",
            "analysis/outputs/ocular_markers_curated.json",
            "analysis/outputs/signaling_markers_curated.json",
            "mcp_cache/raw_ensembl_lookup_genes_20260531.json",
            "mcp_cache/raw_ensembl_ocular_lookup_*_20260611.json",
            "mcp_cache/raw_ensembl_signaling-genes_20260623.json",
            "mcp_cache/raw_ensembl_l2-candidates_20260711.json",
            "analysis/outputs/mitadB_markers_curated.json",
            "mcp_cache/raw_ensembl_mitadB-validate_20260721.json",
            "analysis/outputs/s4_penetrance_markers_curated.json",
            "mcp_cache/raw_ensembl_S4-penetrance-ciliary_20260721.json",
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
