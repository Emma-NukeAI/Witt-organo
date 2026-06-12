"""
bootstrap.py — initialize the Neo4j schema for the DATA INAMOVIBLE GraphRAG (ADR-0020). Run ONCE
after Neo4j is up (idempotent). Creates uniqueness constraints + the HNSW vector index on Documents.

Env: NEO4J_URI (bolt://host:7687), NEO4J_USER, NEO4J_PASSWORD.
Run:  python rag_index/graphrag/bootstrap.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embeddings import get_dim  # noqa: E402


def run():
    from neo4j import GraphDatabase
    DIM = get_dim()
    uri = os.environ["NEO4J_URI"]
    drv = GraphDatabase.driver(uri, auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    stmts = [
        "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
        "CREATE CONSTRAINT entity_symbol IF NOT EXISTS FOR (e:Entity) REQUIRE e.symbol IS UNIQUE",
        "CREATE CONSTRAINT niche_id IF NOT EXISTS FOR (n:Niche) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT db_id IF NOT EXISTS FOR (b:Database) REQUIRE b.id IS UNIQUE",
        f"CREATE VECTOR INDEX doc_embeddings IF NOT EXISTS FOR (d:Document) ON (d.embedding) "
        f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {DIM}, `vector.similarity_function`: 'cosine' }} }}",
    ]
    with drv.session() as s:
        for st in stmts:
            s.run(st)
            print("  ok:", st.split("\n")[0][:80])
    drv.close()
    print(f"[bootstrap] schema + vector index (dim={DIM}) ready on {uri}")


if __name__ == "__main__":
    run()
