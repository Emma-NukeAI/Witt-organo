"""
approve_prune.py — the HUMAN GATE for DELETIONS from the DATA INAMOVIBLE (CLAUDE.md §7). Reads a
pending_review prune proposal (from propose_prune.py) and executes EXACTLY the deletions it lists,
then keeps the sparse index in sync. Only a human runs it (--by required), and only after reviewing
the proposal file. Mirror of approve_dataset.py for the delete path.

Run: set -a; . .secrets/deploy.env; set +a;
     ./.venv/Scripts/python.exe analysis/scripts/lib/approve_prune.py rag_index/prune_proposals/PRUNE-....json --by Emmanuel
"""
import argparse
import datetime
import json
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import rag_backend  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proposal", help="path to a PRUNE-*.json proposal (from propose_prune.py)")
    ap.add_argument("--by", required=True, help="approver name (the human gate)")
    a = ap.parse_args()

    p = pathlib.Path(a.proposal)
    prop = json.loads(p.read_text(encoding="utf-8"))
    if prop.get("status") != "pending_review":
        sys.exit(f"proposal status is '{prop.get('status')}', not pending_review — refusing.")
    docs = [d["doc_id"] for d in prop.get("orphan_documents", [])]
    ents = list(prop.get("orphan_entities", []))
    print(f"[approve_prune] {a.by} executing {prop['proposal_id']}: DELETE {len(docs)} document(s), "
          f"{len(ents)} entity(ies)")
    print(f"  documents: {docs}")
    print(f"  entities:  {ents}")

    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    with drv.session() as s:
        if docs:
            s.run("MATCH (d:Document) WHERE d.doc_id IN $ids DETACH DELETE d", ids=docs)
        if ents:
            s.run("MATCH (e:Entity) WHERE e.symbol IN $sym DETACH DELETE e", sym=ents)
        counts = {k: s.run(f"MATCH (n:{k}) RETURN count(n) AS c").single()["c"]
                  for k in ("Document", "Niche", "Database", "Entity")}
    drv.close()
    rag_backend.build_index()  # keep the sparse half in sync after the deletion

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    prop.update(status="executed", approved_by=a.by, executed_at=now, nodes_after=counts)
    p.write_text(json.dumps(prop, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[approve_prune] done. nodes now: {counts}. proposal -> executed by {a.by} at {now}.")


if __name__ == "__main__":
    main()
