"""
propose_prune.py — detect DEAD/orphan nodes in the DATA INAMOVIBLE graph and write a PRUNE PROPOSAL
(pending_review) specifying EXACTLY what would be deleted. It NEVER deletes (CLAUDE.md §7: every
mutation — including DELETE — is human-gated and specified). Execute an approved proposal with
approve_prune.py.

Orphans detected:
  - :Document nodes whose doc_id is no longer produced by the current corpus (gather_documents)
  - :Entity nodes with no remaining MENTIONS edge
(:Niche / :Database are static config and are never proposed for prune here.)

Run: set -a; . .secrets/deploy.env; set +a; ./.venv/Scripts/python.exe analysis/scripts/lib/propose_prune.py
"""
import datetime
import json
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import rag_backend  # noqa: E402

PROP_DIR = ROOT / "rag_index" / "prune_proposals"


def main():
    from neo4j import GraphDatabase
    current = {d["doc_id"] for d in rag_backend.gather_documents()}
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    with drv.session() as s:
        orphan_docs = [{"doc_id": r["id"], "type": r["t"]} for r in s.run(
            "MATCH (d:Document) WHERE NOT d.doc_id IN $cur RETURN d.doc_id AS id, d.type AS t", cur=list(current))]
        orphan_ents = [r["sym"] for r in s.run(
            "MATCH (e:Entity) WHERE NOT EXISTS { (e)<-[:MENTIONS]-() } RETURN e.symbol AS sym")]
    drv.close()

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not orphan_docs and not orphan_ents:
        print(f"[propose_prune] CLEAN — 0 orphan nodes. The graph matches the current corpus "
              f"({len(current)} docs); nothing to prune.")
        return
    proposal = {
        "proposal_id": f"PRUNE-{now[:19].replace(':', '').replace('-', '')}",
        "created_at": now, "detected_by": "propose_prune.py", "status": "pending_review",
        "reason": "orphan/dead nodes: not in the current corpus (gather_documents) or with no MENTIONS",
        "current_corpus_doc_count": len(current),
        "orphan_documents": orphan_docs, "orphan_entities": orphan_ents,
        "counts": {"documents": len(orphan_docs), "entities": len(orphan_ents)},
        "human_gate": "review this file, then run: approve_prune.py <file> --by <name> (executes the deletions)",
    }
    PROP_DIR.mkdir(exist_ok=True)
    f = PROP_DIR / f"{proposal['proposal_id']}.json"
    f.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[propose_prune] {proposal['counts']} orphan(s) -> PROPOSAL {f.relative_to(ROOT)} (pending_review).")
    print(f"  Documents: {[d['doc_id'] for d in orphan_docs]}")
    print(f"  Entities:  {orphan_ents}")
    print(f"  HUMAN GATE — review, then: approve_prune.py {f.relative_to(ROOT)} --by <name>")
    print("  NOTHING deleted. The store stays inamovible until a human approves this exact list (§7).")


if __name__ == "__main__":
    main()
