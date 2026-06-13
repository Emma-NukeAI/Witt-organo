"""
answer_pipeline.py — DI-first / external-fallback retrieval orchestrator (ADR-0022, slice 1b).

Given a question, gathers evidence on TWO paths:
  Path A — DATA INAMOVIBLE first: semantic query (rag_backend, live Neo4j) + resolve key entities.
  Path B — external fallback (only when A is insufficient): Europe PMC search + fetch_paper full text.
  NEVER-STOPPER (founder rule, 2026-06-13): absence in DI never stops the answer — it TRIGGERS Path B.

Output = an auditor-ready EVIDENCE BUNDLE. This stage only gathers + routes; it does NOT audit
(slice 1c, composite-auditor) or synthesize the final answer. Sufficiency signal (v1):
  insufficient if DI has no paper/chunk evidence on the topic, OR a key entity is absent from DI.
As the human-gated re-ingest loop (slice 1d) adds papers, chunk hits appear and Path A becomes
sufficient on its own — the store reinforces itself.

Spend: Path A embeds the query (OpenAI, authorized 2026-06-13); Path B (Europe PMC) is free.
Bundle cached to mcp_cache/answer_bundle_<slug>_<YYYYMMDD>.json.

CLI:
  python analysis/scripts/lib/answer_pipeline.py "Is osr1 required for zebrafish pronephros?" --entities osr1,prkci,pax2a
"""
import argparse
import json
import os
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
_env = ROOT / ".secrets" / "deploy.env"
if not os.environ.get("NEO4J_URI") and _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("RAG_BACKEND", "neo4j")

from lib import rag_backend, resolve_id, fetch_paper  # noqa: E402

CACHE = ROOT / "mcp_cache"
DATE = "20260613"


def path_a(question, k=6):
    """DATA INAMOVIBLE first: live semantic retrieval + a literature-presence signal."""
    hits = rag_backend.query(question, k)
    serial = [{"doc_id": h.doc_id, "type": h.type, "score": round(h.score, 4),
               "text": (h.text or "")[:140]} for h in hits]
    return {"n_hits": len(serial), "top_score": serial[0]["score"] if serial else 0.0,
            "has_literature_chunks": any(h.type == "chunk" for h in hits), "hits": serial}


def check_entities(entities):
    """Resolve each key entity against the verified store (feeds the auditor's absence re-check, 1c)."""
    out = {}
    for e in entities or []:
        r = resolve_id.resolve(e)
        out[e] = {"in_di": r is not resolve_id.NOT_FOUND,
                  "ensdarg": None if r is resolve_id.NOT_FOUND else r.ensdarg}
    return out


def assess_sufficiency(a, ent):
    reasons = []
    if not a["has_literature_chunks"]:
        reasons.append("DI has no paper/chunk evidence on this topic (catalog-only)")
    missing = [e for e, v in ent.items() if not v["in_di"]]
    if missing:
        reasons.append(f"key entities absent from DI: {missing}")
    return {"sufficient": not reasons, "reasons": reasons, "missing_entities": missing}


def path_b(question, n=2, full_text=True):
    """External fallback: Europe PMC search -> fetch_paper full text for the top hits."""
    papers = []
    for rec in fetch_paper.search_europepmc(question, n=n):
        ident = f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi"))
        got = fetch_paper.fetch_external(ident, want_full_text=full_text) if ident else {"found": False}
        papers.append({
            "search_rec": {k: rec.get(k) for k in ("pmid", "pmcid", "doi", "title", "year", "journal", "is_oa", "cited_by")},
            "fetched": {k: got.get(k) for k in ("found", "full_text", "n_chunks", "raw_cached", "raw_ref")},
        })
    return papers


def retrieve(question, entities=None, n_papers=2):
    """The orchestrator: Path A, then Path B iff A is insufficient. Never a stopper."""
    a = path_a(question)
    ent = check_entities(entities)
    suf = assess_sufficiency(a, ent)
    bundle = {"question": question, "stamp": DATE, "entities_checked": ent,
              "path_a": a, "sufficiency": suf}
    if suf["sufficient"]:
        bundle["path_b"] = {"triggered": False, "reason": "DI sufficient (literature present + entities resolved)"}
    else:
        bundle["path_b"] = {"triggered": True, "triggered_by": suf["reasons"],
                            "papers": path_b(question, n=n_papers)}
    bundle["next"] = "slice 1c: composite-auditor retrieval-audit (absence re-check + external veracity)"
    return bundle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--entities", default="", help="comma-separated gene symbols to check in DI")
    ap.add_argument("--papers", type=int, default=2)
    a = ap.parse_args()
    ents = [e.strip() for e in a.entities.split(",") if e.strip()]
    bundle = retrieve(a.question, entities=ents, n_papers=a.papers)
    slug = re.sub(r"[^a-z0-9]+", "-", a.question.lower())[:40].strip("-")
    (CACHE / f"answer_bundle_{slug}_{DATE}.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
