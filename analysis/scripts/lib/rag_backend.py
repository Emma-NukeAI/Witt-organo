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


_default = None


def get_backend():
    global _default
    if _default is None:
        _default = TfidfRetriever()
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
