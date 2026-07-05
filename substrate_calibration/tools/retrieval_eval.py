"""
retrieval_eval.py — Known-item retrieval evaluation for the DATA INAMOVIBLE (recall@k, MRR).

Answers the external-audit gap (Fable 5, 2026-07-05, rec 1): "retrieval quality is unmeasured; a
knowledge-graph + vector + sparse store lives or dies on recall/precision." Until this exists, the
retrieval layer is a load-bearing UNMEASURED control. This is the measurement.

Method (known-item test): for each catalogued corpus record we KNOW is in the store, build a query from
its salient terms (name + entities + tissue) and check whether the record's own doc_id is retrieved in
the top-k. Reports recall@1 / recall@k and Mean Reciprocal Rank (MRR). Data-driven (probes derive from the
manifest), so it does not rot as the corpus grows. Read-and-report; mutates nothing.

  recall@k = fraction of probes whose target doc_id appears in the top-k hits
  MRR      = mean of 1/rank over probes (0 if target absent from top-k)

Backends: offline sparse TF-IDF by default; RAG_BACKEND=neo4j (+ secrets) for the live hybrid store.

Usage:
    python retrieval_eval.py                 # sparse backend, k=5
    python retrieval_eval.py --k 10 --json ../reports/retrieval_eval_YYYYMMDD.json
    RAG_BACKEND=neo4j python retrieval_eval.py --k 5     # live hybrid
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis" / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MANIFEST = REPO / "rag_index" / "corpus_manifest.json"


def build_probes():
    """One known-item probe per catalogued corpus record: (query, target_doc_id, label).
    The query uses the record's OWN salient terms — a retriever that can't find a document from its own
    name+entities has a real recall problem."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    probes = []
    for r in man.get("records", []):
        cid = r.get("corpus_record_id")
        sd = r.get("source_document", {})
        ents = " ".join(e.get("entity", "") for e in r.get("entities_extracted", []))
        bio = r.get("axis_bio_context", {})
        q = " ".join(str(x) for x in [sd.get("name", ""), ents, bio.get("tissue", ""),
                                      r.get("axis_data_niche", {}).get("primary", "")] if x).strip()
        if cid and q:
            probes.append({"query": q[:200], "target": cid, "label": sd.get("name", cid)[:50]})
    return probes


def run(k=5):
    from lib import rag_backend as R
    probes = build_probes()
    results, rr_sum, hit_k, hit_1 = [], 0.0, 0, 0
    for p in probes:
        hits = R.query(p["query"], k=k)
        ids = [h.doc_id for h in hits]
        rank = next((i + 1 for i, d in enumerate(ids) if d == p["target"]), None)
        rr = (1.0 / rank) if rank else 0.0
        rr_sum += rr
        if rank:
            hit_k += 1
            if rank == 1:
                hit_1 += 1
        results.append({"label": p["label"], "target": p["target"], "rank": rank,
                        "reciprocal_rank": round(rr, 3), "top_k_ids": ids[:k]})
    n = len(probes)
    summary = {
        "backend": "neo4j-hybrid" if __import__("os").environ.get("RAG_BACKEND") == "neo4j" else "sparse-tfidf",
        "n_probes": n, "k": k,
        "recall_at_1": round(hit_1 / n, 3) if n else None,
        "recall_at_k": round(hit_k / n, 3) if n else None,
        "mrr": round(rr_sum / n, 3) if n else None,
    }
    return {"summary": summary, "probes": results}


def main():
    ap = argparse.ArgumentParser(description="Known-item retrieval eval (recall@k, MRR) for the DATA INAMOVIBLE.")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()
    rep = run(k=args.k)
    s = rep["summary"]
    print(f"retrieval eval [{s['backend']}] — {s['n_probes']} known-item probes, k={s['k']}")
    print("=" * 60)
    for r in rep["probes"]:
        mark = f"rank {r['rank']}" if r["rank"] else "MISS"
        print(f"  [{mark:>7}] {r['label']}  ({r['target']})")
    print("=" * 60)
    print(f"recall@1={s['recall_at_1']}  recall@{s['k']}={s['recall_at_k']}  MRR={s['mrr']}")
    if s["n_probes"] < 5:
        print(f"NOTE: only {s['n_probes']} probes (small corpus) — this is a SCAFFOLD; recall figures are")
        print("      indicative, not statistically robust. Grows meaningful as the corpus grows.")
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
