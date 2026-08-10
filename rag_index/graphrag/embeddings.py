"""
embeddings.py — embeddings for the DATA INAMOVIBLE GraphRAG (ADR-0020, amended 2026-06-11).

Pluggable via EMBED_MODEL. The vector-index dimension is read from get_dim() so it always matches the
chosen model (bootstrap.py uses it).

  EMBED_MODEL=openai (RECOMMENDED — simplest, no self-hosted infra; needs OPENAI_API_KEY)
      -> OpenAI text-embedding-3-small (1536-dim). Override model via OPENAI_EMBED_MODEL
         (e.g. text-embedding-3-large -> 3072-dim).
  EMBED_MODEL=bge (default for dev/offline; no API key, no torch)
      -> fastembed BAAI/bge-base-en-v1.5 (768-dim, ONNX).
  EMBED_MODEL=biobert | specter2  -> biomedical sentence-transformers (768-dim; needs torch).

Decision (Emmanuel, 2026-06-11): use OpenAI embeddings on the server (OpenAI/Claude API available) to
keep it simple — no Ollama. The general bge stays the zero-dependency dev/offline fallback.
"""
import os

_DIMS = {"openai": 1536, "openai-large": 3072, "bge": 768, "biobert": 768, "specter2": 768}


# --- embedding-usage accounting (block 4, ADR-0051) -------------------------------------------------
# Process-wide cumulative counter fed by ACTUAL OpenAI API usage responses (a measurement, never an
# estimate). Readers snapshot before/after a window and diff; with concurrent runs the window may
# include a neighbor's embeds — callers must label the attribution accordingly.
import threading as _threading  # noqa: E402

CUMULATIVE_USAGE = {"total_tokens": 0, "calls": 0}
_USAGE_LOCK = _threading.Lock()


def usage_snapshot():
    with _USAGE_LOCK:
        return dict(CUMULATIVE_USAGE)


def get_dim():
    model = os.environ.get("EMBED_MODEL", "bge").lower()
    if model == "openai":
        return 3072 if "large" in os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small") else 1536
    return _DIMS.get(model, 768)


def get_embedder():
    """Return embed(texts: list[str]) -> list[list[float]]. Lazy imports per backend."""
    model = os.environ.get("EMBED_MODEL", "bge").lower()

    if model == "openai":
        from openai import OpenAI
        # BOUNDED (2026-07-19): the SDK default is timeout=600s x max_retries=2 == up to ~1800s of silent
        # hang if the first embeddings POST cannot connect — the exact 1800s the MCP client aborted on.
        # Cap it hard so a query fails fast (and HybridRetriever falls back to sparse) instead of hanging.
        _t = float(os.environ.get("OPENAI_EMBED_TIMEOUT_S", "10"))
        client = OpenAI(timeout=_t, max_retries=0)  # reads OPENAI_API_KEY from env
        name = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")

        def embed(texts):
            texts = [t if t.strip() else " " for t in texts]
            resp = client.embeddings.create(model=name, input=list(texts))
            try:  # block 4 (ADR-0051): embedding spend was INVISIBLE — measure it from the API response
                with _USAGE_LOCK:
                    CUMULATIVE_USAGE["total_tokens"] += int(resp.usage.total_tokens or 0)
                    CUMULATIVE_USAGE["calls"] += 1
            except Exception:
                pass
            return [d.embedding for d in resp.data]
        return embed

    if model in ("biobert", "specter2"):
        from sentence_transformers import SentenceTransformer
        name = {"biobert": "pritamdeka/S-BioBert-snli-multinli-stsb",
                "specter2": "allenai/specter2_base"}[model]
        st = SentenceTransformer(name)

        def embed(texts):
            return [list(map(float, v)) for v in st.encode(list(texts), normalize_embeddings=True)]
        return embed

    # default dev/offline: fastembed bge-base (ONNX, no torch, no API key)
    from fastembed import TextEmbedding
    emb = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")

    def embed(texts):
        return [list(map(float, v)) for v in emb.embed(list(texts))]
    return embed


if __name__ == "__main__":
    e = get_embedder()
    v = e(["zebrafish pronephros pax2a", "ocular anterior segment foxc1b"])
    print(f"EMBED_MODEL={os.environ.get('EMBED_MODEL','bge')} | dim={len(v[0])} (get_dim={get_dim()}) | n={len(v)}")
