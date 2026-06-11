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


def hypothesis_cosine(_pair):
    """Axis (c) — STUB. Requires a local embedding model + retrieval backend (RAG still OPEN)."""
    return None


def probe(paired_runs, month_tag="self-test", config_hash="scaffold"):
    """paired_runs: list of {retrieval_a, retrieval_b, citations_a, citations_b, hyp_a, hyp_b}."""
    jacc = [jaccard(p["retrieval_a"], p["retrieval_b"]) for p in paired_runs]
    cite = [jaccard(p["citations_a"], p["citations_b"]) for p in paired_runs]
    cos = [c for c in (hypothesis_cosine(p) for p in paired_runs) if c is not None]

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
            "hypothesis_cosine": {"status": "pending (needs local embedding model + RAG backend; plan §A OPEN)",
                                  "median": None, "sigma": None, "eps_delta": None, "eps_pass": None},
        },
        "note": ("EPS is MEASURED here, not assumed. Axes a/b run now on set-overlap; axis c activates "
                 "with the RAG backend. No delta is counted as improvement below eps_delta (RIL_PROGRAM §8)."),
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
