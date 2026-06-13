"""
propose_from_external.py — slice 1d (ADR-0022): turn an AUDIT-APPROVED external paper into a
PROPOSED corpus record (pending_review) for the DATA INAMOVIBLE. Closes the self-reinforcing loop.

Re-fetches the paper (idempotent, cached) via fetch_paper, section-chunks it, extracts entities
through the resolve_id gate (NEVER mints IDs), and writes a corpus record with
approval_chain=pending_review. It STOPS at the human gate — it never ingests (that is
approve_dataset.py, run by a human) and never adds new verified identifiers (subject genes not in the
store are FLAGGED, not minted).

Run:
  ./.venv/Scripts/python.exe analysis/scripts/lib/propose_from_external.py --pmid 25446529 \
      --question "Is prkci required for zebrafish pronephros tubule identity?" \
      --subject-genes prkci,prkcz --niche RN1 --domain N3 [--dry-run]
"""
import argparse
import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import resolve_id, fetch_paper, chunk_document  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
CACHE = ROOT / "mcp_cache"
DATE = "20260613"
GENE_RE = re.compile(r"\b[a-z]{2,6}\d{0,3}[a-z]?\b")  # candidate gene tokens; resolve_id gates the rest


def _next_id(man):
    nums = [int(r["corpus_record_id"].split("-")[-1]) for r in man.get("records", [])
            if r["corpus_record_id"].startswith("CORPUS-2026-")]
    return f"CORPUS-2026-{(max(nums) + 1) if nums else 1:04d}"


def extract_entities(text):
    """Candidate tokens -> resolve_id gate -> verified entities only (noise resolves to NOT_FOUND, dropped)."""
    out, seen = [], set()
    for tok in sorted(set(GENE_RE.findall(text.lower()))):
        r = resolve_id.resolve(tok)
        if r is not resolve_id.NOT_FOUND and r.symbol not in seen:
            seen.add(r.symbol)
            out.append({"entity": r.symbol, "type": "gene_symbol",
                        "verified_store_ref": f"verified_identifiers.json#{r.symbol}",
                        "store_ensdarg": r.ensdarg,
                        "verification_tier": "RAW" if r.is_raw_verified else "DERIVED"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid", required=True)
    ap.add_argument("--question", required=True, help="the question this paper was retrieved to answer")
    ap.add_argument("--subject-genes", default="", help="comma-sep genes the paper is ABOUT (flagged if absent from store)")
    ap.add_argument("--niche", default="RN1")
    ap.add_argument("--domain", default="N3")
    ap.add_argument("--audit", default="composite-auditor Mode 1 (3 adversarial auditors) — see session 2026-06-13")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    got = fetch_paper.fetch_external(f"PMID:{a.pmid}")
    if not got.get("found"):
        sys.exit(f"PMID {a.pmid} not resolvable via Europe PMC")
    meta, raw_ref = got["record"], got["raw_ref"]
    cid_tag = (meta.get("pmcid") or meta.get("pmid"))
    chunks = chunk_document.chunk(CACHE / f"raw_paper_{cid_tag}_{DATE}.txt")
    entities = extract_entities(" ".join(c["text"] for c in chunks))

    gaps = []
    for g in [s.strip() for s in a.subject_genes.split(",") if s.strip()]:
        if resolve_id.resolve(g) is resolve_id.NOT_FOUND:
            gaps.append(f"subject gene '{g}' NOT in verified store — to index it as an entity, verify + add "
                        f"via the store builder + human gate (ADR-0008/0010); NOT minted here")
    if not meta.get("is_oa"):
        gaps.append("not Open Access — raw is a source-pointer (abstract cached); full text not mirrored "
                    "(publisher paywall). Promote to a MinIO mirror only with a legally-held PDF.")

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cid = _next_id(man)
    record = {
        "corpus_record_id": cid, "version": "v1.0",
        "source_document": {"name": meta.get("title"),
                            "accession": f"PMID:{meta.get('pmid')} | {meta.get('pmcid')} | DOI:{meta.get('doi')}",
                            "source_db": "EuropePMC"},
        "axis_data_niche": {"primary": a.niche, "secondary": []},
        "axis_scientific_domain": {"primary": a.domain},
        "entities_extracted": entities,
        "chunks": [{"chunk_id": f"{cid}#c{c['order']:03d}", "section": c["section"], "order": c["order"],
                    "text": c["text"], "raw_ref": raw_ref} for c in chunks],
        "proposed_placement": {"data_niche": a.niche, "confidence": 0.0,
                               "reasoning": "added via answer-pipeline loop (ADR-0022); human gate decides final placement"},
        "raw_provenance": {"policy": "hybrid: public source-pointer (not mirrored)", "n_files": 1, "files": [raw_ref]},
        "approval_chain": [{"gate": "categorization", "status": "pending_review", "approved_by": None, "approved_at": None}],
        "provenance": {"via": "answer-pipeline loop (ADR-0022)", "answers_question": a.question,
                       "retrieval": "Path B (Europe PMC) after DI insufficiency",
                       "audit": a.audit, "verified_via": "Europe PMC", "verified_on": "2026-06-13"},
        "gap_flags": gaps,
        "substrate_evidence": ["test_1", "test_3"],
    }
    print(f"[propose_from_external] {cid}: {len(chunks)} chunk(s), {len(entities)} verified entities "
          f"{[e['entity'] for e in entities]}, {len(gaps)} gap_flag(s)")
    print(json.dumps({"corpus_record_id": cid, "title": record["source_document"]["name"],
                      "accession": record["source_document"]["accession"],
                      "entities_extracted": [e["entity"] for e in entities],
                      "n_chunks": len(chunks), "gap_flags": gaps,
                      "approval_chain": record["approval_chain"]}, ensure_ascii=False, indent=2))
    if a.dry_run:
        print("\n--dry-run: NOT written to the manifest.")
        return
    man["records"].append(record)
    man["status"] = (f"{cid} PROPOSED (pending_review) via answer-pipeline loop (ADR-0022). "
                     f"HUMAN GATE: review, then approve_dataset.py to ingest.")
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n  PENDING_REVIEW written to manifest. STOP — the loop ends at your gate. To ingest:")
    print(f"  set -a; . .secrets/deploy.env; set +a; "
          f"./.venv/Scripts/python.exe analysis/scripts/lib/approve_dataset.py {cid} --by Emmanuel")


if __name__ == "__main__":
    main()
