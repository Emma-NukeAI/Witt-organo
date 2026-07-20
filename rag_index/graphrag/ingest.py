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
from embeddings import get_embedder, get_dim  # noqa: E402
from lib import rag_backend, verify_output  # noqa: E402  (gather_documents; tier_weight for Bayes-purity)


def _load(p):
    return json.loads((ROOT / "rag_index" / p).read_text(encoding="utf-8"))


def run(confirm_embed_model_change=False):
    from neo4j import GraphDatabase
    import datetime
    # EMBED_MODEL resolution (ADR-0039, 2026-07-19): default to 'openai' (1536-dim) WHENEVER a hosted Neo4j
    # is configured, so a fresh-clone ingest builds/matches the live 1536-dim 'doc_embeddings' index that the
    # QUERY path hard-pins to OpenAI (server.py / rag_backend.py). The old blanket 'bge' default (768-dim)
    # let a hosted re-ingest create a 768-dim index that the OpenAI query path then silently degrades against
    # (dense fails -> sparse-only). 'bge' remains the zero-dependency default only for genuinely offline use
    # (no NEO4J_URI). An explicit EMBED_MODEL always wins. We stamp it into the env so get_dim()/get_embedder()
    # below read the SAME resolved value.
    embed_model = os.environ.get("EMBED_MODEL") or ("openai" if os.environ.get("NEO4J_URI") else "bge")
    os.environ["EMBED_MODEL"] = embed_model
    dim = get_dim()
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))

    # A1: ensure schema + vector index (idempotent). Schema/index setup runs INSIDE the human-gated ingest
    # path (approve_dataset.py invokes this) — never by an agent ad-hoc (CLAUDE.md §7).
    with drv.session() as s:
        for st in (
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
            "CREATE CONSTRAINT entity_symbol IF NOT EXISTS FOR (e:Entity) REQUIRE e.symbol IS UNIQUE",
            "CREATE CONSTRAINT niche_id IF NOT EXISTS FOR (n:Niche) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT db_id IF NOT EXISTS FOR (b:Database) REQUIRE b.id IS UNIQUE",
            "CREATE CONSTRAINT meta_key IF NOT EXISTS FOR (m:Meta) REQUIRE m.key IS UNIQUE",
            f"CREATE VECTOR INDEX doc_embeddings IF NOT EXISTS FOR (d:Document) ON (d.embedding) "
            f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine' }} }}",
        ):
            s.run(st)
        # A2: dim guard — the live index dimension MUST match the embedder's dimension.
        live_dim = None
        try:
            row = s.run("SHOW INDEXES YIELD name, options WHERE name='doc_embeddings' "
                        "RETURN options['indexConfig']['vector.dimensions'] AS d").single()
            live_dim = int(row["d"]) if row and row["d"] is not None else None
        except Exception:
            pass
        if live_dim is not None and live_dim != dim:
            drv.close()
            raise SystemExit(f"[ingest] DIM MISMATCH: index 'doc_embeddings' is {live_dim}-dim but "
                             f"EMBED_MODEL={embed_model} is {dim}-dim. Changing the index dimension is a "
                             f"human-gated mutation (§7): drop + rebuild the index deliberately, then re-ingest.")
        # A3: embedding-model change guard — a model change re-embeds all + invalidates the vector space.
        prior = s.run("MATCH (m:Meta {key:'data_inamovible'}) RETURN m.embed_model AS em").single()
        prior_model = prior["em"] if prior else None
        if prior_model and prior_model != embed_model and not confirm_embed_model_change:
            drv.close()
            raise SystemExit(f"[ingest] EMBED-MODEL CHANGE: the store was embedded with '{prior_model}', now "
                             f"EMBED_MODEL='{embed_model}'. This re-embeds ALL docs + invalidates the old vector "
                             f"space — a human-gated mutation (§7). Re-run: ingest.py --confirm-embed-model-change")

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
                # R2 / ADR-0024 (Bayes-purity): stamp a verified_tier_weight on the Entity AND the MENTIONS
                # edge (RAW=1.0 confirmed / DERIVED=0.7 / NOT_FOUND|unknown=0.0). Only RAW-confirmed mentions
                # may later carry full calibration label-weight; the deterministic verifier keeps f -> 0.
                tier = e.get("verification_tier")
                tw = verify_output.tier_weight(tier)
                s.run("MERGE (x:Entity {symbol:$s}) SET x.ensdarg=$g, x.tier=$t, x.verified_tier_weight=$w",
                      s=sym, g=(e.get("store_ensdarg") or e.get("external_ids_verified", {}).get("ENSDARG")),
                      t=tier, w=tw)
                s.run("MATCH (doc:Document {doc_id:$id}),(en:Entity {symbol:$s}) "
                      "MERGE (doc)-[m:MENTIONS]->(en) SET m.verified_tier_weight=$w",
                      id=r["corpus_record_id"], s=sym, w=tw)
        counts = {k: s.run(f"MATCH (n:{k}) RETURN count(n) AS c").single()["c"]
                  for k in ("Document", "Niche", "Database", "Entity")}
        # A6: stamp freshness — embed model/dim, refresh time, doc count (introspectable by agents/health checks)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        s.run("MERGE (m:Meta {key:'data_inamovible'}) SET m.embed_model=$em, m.embed_dim=$d, "
              "m.refreshed_at=$t, m.doc_count=$n", em=embed_model, d=dim, t=now, n=len(docs))
    drv.close()
    print(f"[ingest] EMBED_MODEL={embed_model} dim={dim} | nodes: {counts} | refreshed_at={now}")


if __name__ == "__main__":
    import sys
    run(confirm_embed_model_change="--confirm-embed-model-change" in sys.argv)
