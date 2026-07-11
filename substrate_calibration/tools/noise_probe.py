"""
noise_probe.py — EPS noise-probe (RIL_PROGRAM.md §3, Cycle 2 / PR-03). NO-SPEND, stdlib + numpy.

Measures the run-to-run noise floor on three axes so that an improvement can be distinguished from
drift (RIL_PROGRAM §8: nothing is counted until it clears EPS). Two EPS flavors (closes C.20):
  EPS_delta = 2 * sigma   (one-sided signal-detection threshold for "is this delta real?")
  EPS_pass  = p25         (percentile pass/fail threshold on bounded [0,1] metrics)

Three axes (INTEGRATION §5.1), computed over PAIRED identical runs (same query, temp>0) of the
held-out set (evaluation/held_out_set_v1.json):
  (a) Retrieval Jaccard   — Jaccard of the top-K retrieved doc/cache IDs across the paired runs
  (b) Citation overlap    — overlap of evidence_cited across the paired runs
  (c) Hypothesis cosine   — cosine between embeddings of the paired output hypotheses

STATUS (Cycle 2 scaffold): axes (a) and (b) are set-overlap and run NOW on any paired-run records.
Axis (c) requires a local embedding model (bge/sentence-transformers/Ollama) + a retrieval backend,
which depend on the RAG architecture that is still OPEN (plan §A). Until then, (c) is a no-op stub
that returns None and is reported as "pending (needs embedding + RAG backend)". This file proves the
EPS math end-to-end on synthetic paired runs so the schema + thresholds are exercised, NO-SPEND.

Usage:  python substrate_calibration/tools/noise_probe.py            # self-test on synthetic pairs
        (later) feed real paired-run records once a retrieval backend exists.
"""
from pathlib import Path
import sys
import json

import numpy as np

OUT_DIR = Path("substrate_calibration/noise_probe")


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def eps_delta(values):
    """2 * sigma over the per-pair axis values (signal-detection threshold)."""
    v = np.asarray(values, dtype=float)
    return float(2.0 * v.std(ddof=0)) if len(v) else None


def eps_pass(values):
    """25th percentile (pass/fail threshold on bounded [0,1] metrics)."""
    v = np.asarray(values, dtype=float)
    return float(np.percentile(v, 25)) if len(v) else None


def _cosine(u, v):
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    denom = float(np.linalg.norm(u) * np.linalg.norm(v))
    return float(u @ v / denom) if denom else None


def hypothesis_cosine(pair, embedder=None):
    """Axis (c) — similarity between the paired output hypotheses (A1 activation, 2026-07-11).

    - `embedder` given (embed(list[str]) -> list[vec], e.g. rag_index.graphrag.embeddings.get_embedder):
      SEMANTIC cosine between embeddings of hyp_a / hyp_b — the intended axis c.
    - else: NO-SPEND lexical TF-IDF cosine proxy (sklearn, already a dep) — a surface-stability signal,
      clearly labelled so it is never mistaken for the semantic axis.
    Returns (value, method); (None, "pending") when a hypothesis text is missing (the pre-A1 stub state).
    """
    a, b = (pair.get("hyp_a") or "").strip(), (pair.get("hyp_b") or "").strip()
    if not a or not b:
        return None, "pending"
    if embedder is not None:
        try:
            va, vb = embedder([a, b])
            c = _cosine(va, vb)
            if c is not None:
                import os
                return c, f"semantic:{os.environ.get('EMBED_MODEL', 'embedder')}"
        except Exception:
            pass  # fall through to the lexical proxy — never a stopper
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        m = TfidfVectorizer().fit_transform([a, b])
        return float((m[0] @ m[1].T).toarray().ravel()[0]), "lexical-tfidf-proxy"
    except Exception:
        return None, "pending"


def probe(paired_runs, month_tag="self-test", config_hash="scaffold", embedder=None):
    """paired_runs: list of {retrieval_a, retrieval_b, citations_a, citations_b, hyp_a, hyp_b}.
    `embedder` (optional) activates the SEMANTIC axis c; without it axis c uses the lexical proxy when
    hypotheses are present, or stays 'pending' when they are absent (self-test / retrieval-only runs)."""
    jacc = [jaccard(p["retrieval_a"], p["retrieval_b"]) for p in paired_runs]
    cite = [jaccard(p["citations_a"], p["citations_b"]) for p in paired_runs]
    cos_pairs = [hypothesis_cosine(p, embedder) for p in paired_runs]
    cos = [c for c, _ in cos_pairs if c is not None]
    methods = sorted({m for _, m in cos_pairs if m != "pending"})

    if cos:
        axis_c = {"method": "+".join(methods) or "unknown",
                  "median": float(np.median(cos)), "sigma": float(np.std(cos)),
                  "eps_delta": eps_delta(cos), "eps_pass": eps_pass(cos), "n": len(cos)}
    else:
        axis_c = {"status": "pending (no hypothesis text in pairs; pass hyp_a/hyp_b + optional embedder)",
                  "median": None, "sigma": None, "eps_delta": None, "eps_pass": None}

    result = {
        "month_tag": month_tag,
        "config_hash": config_hash,
        "n_pairs": len(paired_runs),
        "axes": {
            "retrieval_jaccard": {"median": float(np.median(jacc)) if jacc else None,
                                  "sigma": float(np.std(jacc)) if jacc else None,
                                  "eps_delta": eps_delta(jacc), "eps_pass": eps_pass(jacc)},
            "citation_overlap": {"median": float(np.median(cite)) if cite else None,
                                 "sigma": float(np.std(cite)) if cite else None,
                                 "eps_delta": eps_delta(cite), "eps_pass": eps_pass(cite)},
            "hypothesis_cosine": axis_c,
        },
        "note": ("EPS is MEASURED here, not assumed. Axes a/b run on set-overlap; axis c is semantic when an "
                 "embedder is passed, else a NO-SPEND lexical TF-IDF proxy (labelled). No delta counts as "
                 "improvement below eps_delta (RIL_PROGRAM §8)."),
    }
    return result


def _selftest():
    # Synthetic paired runs: some stochastic variation between identical-config replicas.
    pairs = [
        {"retrieval_a": ["d1", "d2", "d3", "d4"], "retrieval_b": ["d1", "d2", "d3", "d9"],
         "citations_a": ["PMID:1", "PMID:2"], "citations_b": ["PMID:1", "PMID:2"], "hyp_a": "", "hyp_b": ""},
        {"retrieval_a": ["d1", "d2", "d5"], "retrieval_b": ["d1", "d2", "d5", "d6"],
         "citations_a": ["PMID:1", "PMID:3"], "citations_b": ["PMID:1"], "hyp_a": "", "hyp_b": ""},
        {"retrieval_a": ["d7", "d8"], "retrieval_b": ["d7", "d8"],
         "citations_a": ["PMID:4"], "citations_b": ["PMID:4"], "hyp_a": "", "hyp_b": ""},
    ]
    res = probe(pairs, month_tag="selftest-synthetic")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "eps_baseline_selftest.json"
    out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res["axes"], indent=2))
    print(f"[noise_probe] wrote {out} (synthetic self-test; real probe awaits the RAG backend)")


if __name__ == "__main__":
    _selftest()
