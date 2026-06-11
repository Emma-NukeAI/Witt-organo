"""
embeddings.py — self-hosted embeddings for the DATA INAMOVIBLE GraphRAG (ADR-0020). NO paid APIs.

Pluggable, all 768-dim so the Neo4j vector index dimension is stable across a model swap:
  EMBED_MODEL=bge (default)  -> fastembed BAAI/bge-base-en-v1.5  (768, ONNX, NO torch — light, runs anywhere)
  EMBED_MODEL=biobert        -> sentence-transformers BioBERT-style (768, biomedical papers; needs torch)
  EMBED_MODEL=specter2       -> SPECTER2 paper embeddings (768; needs sentence-transformers + adapters)

The general bge model is the default for the first build (light, no torch). Switch to the biomedical
model on the server for paper-heavy corpora (ADR-0020); the dimension (768) does not change, so no
reindex is needed.
"""
import os

DIM = 768  # all supported models are 768-dim -> stable Neo4j vector index dimension


def get_embedder():
    """Return embed(texts: list[str]) -> list[list[float]] (768-dim vectors). Lazy imports."""
    model = os.environ.get("EMBED_MODEL", "bge").lower()

    if model in ("biobert", "specter2"):
        from sentence_transformers import SentenceTransformer
        name = {
            "biobert": "pritamdeka/S-BioBert-snli-multinli-stsb",   # biomedical sentence embeddings, 768
            "specter2": "allenai/specter2_base",                    # scientific-paper embeddings, 768
        }[model]
        st = SentenceTransformer(name)

        def embed(texts):
            return [list(map(float, v)) for v in st.encode(list(texts), normalize_embeddings=True)]
        return embed

    # default: fastembed bge-base (ONNX, no torch)
    from fastembed import TextEmbedding
    emb = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")

    def embed(texts):
        return [list(map(float, v)) for v in emb.embed(list(texts))]
    return embed


if __name__ == "__main__":
    e = get_embedder()
    v = e(["zebrafish pronephros pax2a", "ocular anterior segment foxc1b"])
    print(f"EMBED_MODEL={os.environ.get('EMBED_MODEL','bge')} | dim={len(v[0])} | n={len(v)}")
