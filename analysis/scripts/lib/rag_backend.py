"""
rag_backend.py — RAG retrieval backend v1 for the DATA INAMOVIBLE corpus (GWT v1.1, ADR-0019).

The SEMANTIC half of the source-of-truth interface (resolve_id.py stays the DETERMINISTIC identifier
resolver; this is the semantic retrieval layer). v1 is a flat, versioned, human-gated, NO-SPEND SPARSE
retriever (TF-IDF/BM25-style via sklearn — already installed; zero new dependency, no model download).
It is the PERMANENT sparse half of the recommended hybrid (audit data-engineering lens: hybrid
BM25+dense). A dense backend (Chroma/LanceDB + local embeddings) plugs in behind the same Retriever
interface later — gated on a bottleneck + an install decision (ADR-0015 keeps the backend choice open).

Storage (DATA INAMOVIBLE discipline): the indexed corpus is `rag_index/index/documents.jsonl`
(human-readable, diffable, versioned, committed) + `manifest.json`. The TF-IDF matrix is built
in-memory at query time from documents.jsonl (fast at this scale); persisting vectors is the dense-era
optimization. Read-only by default; only build_index() writes, and only from already-curated sources.

Usage:
  python analysis/scripts/lib/rag_backend.py build          # (re)build the index from sources
  python analysis/scripts/lib/rag_backend.py query "..."    # query the index
"""
from pathlib import Path
import sys
import json
from dataclasses import dataclass
from typing import List

ROOT = Path(__file__).resolve().parents[3]
RAG = ROOT / "rag_index"
INDEX_DIR = RAG / "index"
DOCS = INDEX_DIR / "documents.jsonl"
MANIFEST = INDEX_DIR / "manifest.json"
INDEX_VERSION = "2026-06-11.1"


# ---------------- ingestion: gather the DATA INAMOVIBLE corpus into documents ----------------
def gather_documents():
    """Build searchable documents from the curated corpus sources. Each doc: {doc_id, text, metadata}."""
    docs = []
    niches = json.loads((RAG / "niches.json").read_text(encoding="utf-8"))["niches"]
    for n in niches:
        docs.append({"doc_id": f"niche:{n['id']}", "type": "niche",
                     "text": f"{n['id']} {n['name']}. {n['purpose']} File types: {', '.join(n['file_types'])}.",
                     "metadata": {"data_niche": n["id"], "name": n["name"]}})
    dbs = json.loads((RAG / "databases.json").read_text(encoding="utf-8"))["databases"]
    for d in dbs:
        docs.append({"doc_id": f"db:{d['id']}", "type": "database",
                     "text": f"{d['name']}. {d['utility']} Data: {d['data_type']}. Feeds {', '.join(d.get('feeds_niches', []))}.",
                     "metadata": {"db": d["id"], "link": d.get("link"), "feeds_niches": d.get("feeds_niches", [])}})
    manifest = json.loads((RAG / "corpus_manifest.json").read_text(encoding="utf-8"))
    for r in manifest.get("records", []):
        sd = r.get("source_document", {})
        ents = " ".join(e.get("entity", "") for e in r.get("entities_extracted", []))
        docs.append({"doc_id": r["corpus_record_id"], "type": "dataset",
                     "text": f"{sd.get('name','')}. {r.get('fit_note','')} niche {r.get('axis_data_niche',{}).get('primary')} "
                             f"domain {r.get('axis_scientific_domain',{}).get('primary')} entities {ents} "
                             f"stage {r.get('axis_bio_context',{}).get('stage_hpf')} tissue {r.get('axis_bio_context',{}).get('tissue')}",
                     "metadata": {"accession": sd.get("accession"), "source_db": sd.get("source_db"),
                                  "data_niche": r.get("axis_data_niche", {}).get("primary"),
                                  "scientific_domain": r.get("axis_scientific_domain", {}).get("primary")}})
        # chunk-level docs (papers/PDFs via chunk_document.py): retrievable + carry raw_ref to the source
        for ch in r.get("chunks", []):
            docs.append({"doc_id": ch["chunk_id"], "type": "chunk",
                         "text": (ch.get("text") or "")[:2000],
                         "metadata": {"section": ch.get("section"), "parent": r["corpus_record_id"],
                                      "raw_ref": ch.get("raw_ref")}})
    return docs


def build_index():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    docs = gather_documents()
    with DOCS.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    by_type = {}
    for d in docs:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    MANIFEST.write_text(json.dumps({
        "schema_version": "1.0", "index_version": INDEX_VERSION,
        "backend": "sparse TF-IDF (sklearn), in-memory at query time; dense/hybrid upgrade gated (ADR-0019/0015)",
        "generated_by": "analysis/scripts/lib/rag_backend.py build",
        "sources": ["rag_index/niches.json", "rag_index/databases.json", "rag_index/corpus_manifest.json"],
        "read_only": True, "human_gate_required_to_modify": True,
        "n_documents": len(docs), "by_type": by_type,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"[rag_backend] built index: {len(docs)} documents {by_type} -> {DOCS}")


# ---------------- retrieval ----------------
@dataclass
class Hit:
    doc_id: str
    score: float
    type: str
    text: str
    metadata: dict


class Retriever:
    """Interface. v1 impl = TfidfRetriever. A DenseRetriever (Chroma/LanceDB + embeddings) plugs in later."""
    def query(self, text: str, k: int = 5) -> List[Hit]:
        raise NotImplementedError


class TfidfRetriever(Retriever):
    def __init__(self, docs_path: Path = DOCS):
        from sklearn.feature_extraction.text import TfidfVectorizer  # lazy
        self.docs = [json.loads(l) for l in docs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self._vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        self._mat = self._vec.fit_transform([d["text"] for d in self.docs])

    def query(self, text: str, k: int = 5) -> List[Hit]:
        import numpy as np
        q = self._vec.transform([text])
        sims = (self._mat @ q.T).toarray().ravel()
        order = np.argsort(-sims)[:k]
        return [Hit(self.docs[i]["doc_id"], float(sims[i]), self.docs[i]["type"],
                    self.docs[i]["text"], self.docs[i].get("metadata", {}))
                for i in order if sims[i] > 0]


# ---------------- production path (ADR-0020): dense + graph + rerank, behind the same interface ----------------
# These are the hosted-GraphRAG extension points. They activate on the rack when configured (env
# RAG_BACKEND=neo4j + NEO4J_URI/embedding service); in dev/offline they raise a clear deploy note and
# the TfidfRetriever (sparse v1) is used. The interface is stable so callers never change.

class Reranker:
    """Post-retrieval reranking (RAG_Techniques: intelligent reranking). NoOp default; cross-encoder on rack."""
    def rerank(self, query: str, hits: List[Hit], k: int) -> List[Hit]:
        return hits[:k]


class CrossEncoderReranker(Reranker):
    """Biomedical cross-encoder reranker (e.g., a MS-MARCO/BioBERT cross-encoder). Deployed on the rack."""
    def __init__(self, model: str = "biomedical-cross-encoder"):
        self.model = model

    def rerank(self, query, hits, k):
        raise NotImplementedError("CrossEncoderReranker activates on the rack (transformers/ONNX); "
                                  "dev uses NoOp. See rag_index/deploy/README.md.")


class DenseRetriever(Retriever):
    """Dense vector retrieval. Embeddings: SPECTER2/BioBERT (papers) + general (bge/nomic), self-hosted
    (ADR-0020). In production this queries Neo4j's native vector index; the standalone form is for testing."""
    def __init__(self, embedding_model: str = "SPECTER2|bge-large"):
        self.embedding_model = embedding_model

    def query(self, text, k=5):
        raise NotImplementedError("DenseRetriever activates on the rack (embedding service + vectors). "
                                  "Dev/offline uses TfidfRetriever (sparse v1). See rag_index/deploy/README.md.")


class Neo4jGraphRetriever(Retriever):
    """GraphRAG over self-hosted Neo4j (graph + native HNSW vector index), populated by graphify (ADR-0020).
    Fuses vector similarity with multi-hop Cypher expansion. Activates when NEO4J_URI is configured."""
    CYPHER_VECTOR = (
        "CALL db.index.vector.queryNodes('doc_embeddings', $k, $q_emb) YIELD node, score "
        "OPTIONAL MATCH (node)-[r]-(related) "       # 1-hop graph expansion for related entities
        "RETURN node, score, collect(distinct related) AS related ORDER BY score DESC"
    )

    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri  # e.g. bolt://<host>:7687
        self.user, self.password = user, password
        self._driver = None
        self._embed = None

    def _connect(self):
        if self._driver is None:
            from neo4j import GraphDatabase  # lazy: only on the server where the driver is installed
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        if self._embed is None:
            import sys as _sys
            _sys.path.insert(0, str(RAG / "graphrag"))
            from embeddings import get_embedder
            self._embed = get_embedder()

    def query(self, text, k=5):
        # Real GraphRAG retrieval: embed the query, run the native vector index + 1-hop graph
        # expansion. Raises (ImportError / connection error) in dev with no Neo4j -> HybridRetriever
        # falls back to sparse. See rag_index/deploy/README.md + ADR-0020.
        self._connect()
        q_emb = self._embed([text])[0]
        with self._driver.session() as s:
            rows = s.run(self.CYPHER_VECTOR, k=k, q_emb=q_emb).data()
        hits = []
        for r in rows:
            node = r.get("node", {}) or {}
            related = r.get("related", []) or []
            rel_names = [(x.get("symbol") or x.get("id") or x.get("name")) for x in related if isinstance(x, dict)]
            hits.append(Hit(node.get("doc_id", "?"), float(r.get("score", 0.0)),
                            node.get("type", "document"), node.get("text", ""),
                            {"meta": node.get("meta"), "related": [n for n in rel_names if n]}))
        return hits


class HybridRetriever(Retriever):
    """Hybrid fusion (RAG_Techniques: fusion retrieval): sparse (Tfidf) + dense, reciprocal-rank-fused,
    then reranked. In production dense = Neo4jGraphRetriever; in dev dense is skipped (sparse only)."""
    def __init__(self, sparse: Retriever, dense: Retriever = None, reranker: Reranker = None):
        self.sparse, self.dense, self.reranker = sparse, dense, reranker or Reranker()

    def query(self, text, k=5):
        # Both halves are optional and isolated: a missing sparse half (no sklearn / no documents.jsonl)
        # or a missing dense half (no Neo4j driver / no connection) must NOT crash retrieval. Whichever
        # half is available contributes; if both are present we fuse them.
        pools = []
        for r in (self.sparse, self.dense):
            if r is None:
                continue
            try:
                pools.append(r.query(text, k * 3))
            except Exception:
                pass
        # reciprocal rank fusion
        scores, byid = {}, {}
        for pool in pools:
            for rank, h in enumerate(pool):
                scores[h.doc_id] = scores.get(h.doc_id, 0.0) + 1.0 / (60 + rank)
                byid[h.doc_id] = h
        fused = sorted(byid.values(), key=lambda h: -scores[h.doc_id])
        return self.reranker.rerank(text, fused, k)


_default = None
_default_sig = None  # signature of the sparse index on disk; a change forces a rebuild (auto-refresh)


def _index_signature():
    try:
        return DOCS.stat().st_mtime_ns
    except OSError:
        return None


def get_backend():
    """Pick the backend from config (ADR-0020). Rack: RAG_BACKEND=neo4j -> Hybrid(Tfidf + Neo4jGraph),
    NoOp reranker by default (fusion order). Dev/offline (default): TfidfRetriever (sparse v1, NO-SPEND).

    AUTO-REFRESH (ADR-0022 hardening, 2026-06-13): rebuilds whenever documents.jsonl changes on disk, so a
    long-lived reader (the MCP server, a persistent agent) always reflects the latest human-gated ingest
    without a restart. Reads/refreshes are free; only the human-gated ingest writes the index (CLAUDE.md §7)."""
    global _default, _default_sig
    import os
    sig = _index_signature()
    if _default is not None and sig == _default_sig:
        return _default
    if os.environ.get("RAG_BACKEND") == "neo4j":
        dense = Neo4jGraphRetriever(uri=os.environ.get("NEO4J_URI"),
                                    user=os.environ.get("NEO4J_USER"),
                                    password=os.environ.get("NEO4J_PASSWORD"))
        try:
            sparse = TfidfRetriever()   # sparse half (sklearn + documents.jsonl); optional
        except Exception:
            sparse = None               # dense-only if sklearn/index unavailable
        reranker = CrossEncoderReranker() if os.environ.get("RAG_RERANKER") == "cross-encoder" else Reranker()
        _default = HybridRetriever(sparse, dense, reranker)
    else:
        _default = TfidfRetriever()
    _default_sig = sig
    return _default


def query(text, k=5):
    """Semantic-ish lookup over the DATA INAMOVIBLE corpus (the lookup_prior backend)."""
    return get_backend().query(text, k)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build_index()
    elif len(sys.argv) >= 3 and sys.argv[1] == "query":
        for h in query(" ".join(sys.argv[2:])):
            print(f"  [{h.score:.3f}] {h.type:9s} {h.doc_id:22s} {h.text[:90]}")
    else:
        print("usage: rag_backend.py build | query '<text>'")
