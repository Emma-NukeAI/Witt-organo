"""
ingest.py — ingest the curated DATA INAMOVIBLE corpus into the Neo4j GraphRAG (ADR-0020).

Human-gated WRITE step (run explicitly; the store is read-only by default). Pipeline:
  documents (rag_backend.gather_documents: niches + databases + datasets)  ->  embed (768-dim)  ->
  MERGE (:Document {embedding, metadata}) + (:Niche)/(:Database)/(:Entity) nodes + relationships
  (Document-[:IN_NICHE]->Niche, Document-[:FROM_DB]->Database, Database-[:FEEDS]->Niche,
   Document-[:MENTIONS]->Entity, Entity bound to its verified ENSDARG/tier).
This gives the GraphRAG both the vector layer (Document.embedding) and the graph layer (relationships)
for hybrid + multi-hop retrieval. Entities bind to the verified store (resolve_id); unverified IDs are
NOT minted. Re-runnable (MERGE = idempotent); bump the corpus version when content changes.

Env: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD ; EMBED_MODEL (bge default).
Run:  python rag_index/graphrag/ingest.py
"""
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from embeddings import get_embedder  # noqa: E402
from lib import rag_backend  # noqa: E402  (gather_documents)


def _load(p):
    return json.loads((ROOT / "rag_index" / p).read_text(encoding="utf-8"))


def run():
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    docs = rag_backend.gather_documents()
    rag_backend.build_index()  # keep the sparse half (documents.jsonl) in sync with the graph; else
    #                            newly-ingested chunks are under-ranked by hybrid RRF fusion (fix 2026-06-13)
    embed = get_embedder()
    vectors = embed([d["text"] for d in docs])

    niches = {n["id"]: n for n in _load("niches.json")["niches"]}
    dbs = {d["id"]: d for d in _load("databases.json")["databases"]}
    manifest = _load("corpus_manifest.json")

    with drv.session() as s:
        # nodes: niches + databases + db->niche FEEDS edges
        for nid, n in niches.items():
            s.run("MERGE (x:Niche {id:$id}) SET x.name=$name", id=nid, name=n["name"])
        for bid, b in dbs.items():
            s.run("MERGE (x:Database {id:$id}) SET x.name=$name, x.link=$link", id=bid, name=b["name"], link=b.get("link"))
            for nid in b.get("feeds_niches", []):
                s.run("MATCH (db:Database {id:$db}),(n:Niche {id:$n}) MERGE (db)-[:FEEDS]->(n)", db=bid, n=nid)
        # documents (with embeddings) + IN_NICHE / FROM_DB edges
        for d, vec in zip(docs, vectors):
            md = d.get("metadata", {})
            s.run("MERGE (x:Document {doc_id:$id}) SET x.text=$t, x.type=$ty, x.embedding=$e, x.meta=$m",
                  id=d["doc_id"], t=d["text"], ty=d["type"], e=vec, m=json.dumps(md, ensure_ascii=False))
            dn = md.get("data_niche")
            if dn and dn in niches:
                s.run("MATCH (doc:Document {doc_id:$id}),(n:Niche {id:$dn}) MERGE (doc)-[:IN_NICHE]->(n)", id=d["doc_id"], dn=dn)
            sdb = md.get("source_db") or md.get("db")
            if sdb and sdb in dbs:
                s.run("MATCH (doc:Document {doc_id:$id}),(b:Database {id:$db}) MERGE (doc)-[:FROM_DB]->(b)", id=d["doc_id"], db=sdb)
        # entities from corpus records, bound to verified ENSDARG/tier, + MENTIONS edges
        for r in manifest.get("records", []):
            for e in r.get("entities_extracted", []):
                sym = e.get("entity")
                if not sym:
                    continue
                s.run("MERGE (x:Entity {symbol:$s}) SET x.ensdarg=$g, x.tier=$t",
                      s=sym, g=(e.get("store_ensdarg") or e.get("external_ids_verified", {}).get("ENSDARG")),
                      t=e.get("verification_tier"))
                s.run("MATCH (doc:Document {doc_id:$id}),(en:Entity {symbol:$s}) MERGE (doc)-[:MENTIONS]->(en)",
                      id=r["corpus_record_id"], s=sym)
        counts = {k: s.run(f"MATCH (n:{k}) RETURN count(n) AS c").single()["c"]
                  for k in ("Document", "Niche", "Database", "Entity")}
    drv.close()
    print(f"[ingest] EMBED_MODEL={os.environ.get('EMBED_MODEL','bge')} | nodes: {counts}")


if __name__ == "__main__":
    run()
