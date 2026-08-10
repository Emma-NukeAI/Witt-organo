"""
precedent.py — the precedent layer (block 6, ADR-0053): the other half of the product thesis.

Evidence and precedent are SEPARATE indices with DIFFERENT admissibility and equivalent value (webapp
decision list). A PrecedentItem is a CLOSED run (explicit closure is the requirement — a run that was
never closed is not precedent). Precedent is prior art for humans and planning; it is NEVER evidence:

  - `verify_output` is provenance-blind BY DESIGN (an ENSDARG copied from the bitácora passes if it
    resolves) — so "precedent is not evidence" cannot be enforced by the gate. It is a PRODUCT rule,
    enforced structurally here: every item ships `admissible_as_evidence: false`, and precedent text
    is never placed into the gated evidence object by any pipeline stage.
  - Citation series are DISJOINT BY CONSTRUCTION (handoff §2.5): numbers = evidence (runs.py),
    LETTERS = precedent (serialize_disjoint below). A letter can never be laundered into the
    evidence series because the two serializers cannot produce each other's labels.

Relevance scorer (prueba pequeño): TF-IDF over question+answer of closed runs when sklearn is
available (it is, in the service container — preloaded on the main thread); a deterministic
token-overlap fallback otherwise. The scorer used is ALWAYS declared in the response — a fallback
must never masquerade as the semantic path (the ADR-0039/0043 discipline, applied here).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

WHY_NOT_ADMISSIBLE = ("precedent is prior art for humans/planning — never evidence; the anti-fabrication "
                      "gate is provenance-blind by design, so this rule is enforced at the product layer "
                      "(ADR-0053): precedent text never enters the gated evidence object")

_IDX = {"key": None, "items": [], "vectorizer": None, "matrix": None, "scorer": None}


def _corpus():
    items = []
    for r in db.closed_runs():
        rec = json.loads(r["frozen_record_json"] or "{}")
        ans = rec.get("answer") or {}
        conf = rec.get("confidence") or {}
        items.append({
            "run_id": r["run_id"],
            "question": r["question"],
            "closed_by": r["closed_by"],
            "frozen_at": r["frozen_at"].isoformat(timespec="seconds") if r["frozen_at"] else None,
            "verdict": (rec.get("audit") or {}).get("verdict"),
            "decision_state": (rec.get("decision_state") or {}).get("state"),
            "confidence_final": conf.get("final", ans.get("stated_confidence")),
            "answer_excerpt": (ans.get("direct_answer") or "")[:280],
            "_text": f"{r['question']} {ans.get('direct_answer') or ''}",
        })
    return items


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _ensure_index():
    items = _corpus()
    key = (len(items), items[0]["frozen_at"] if items else None)
    if _IDX["key"] == key:
        return
    _IDX.update(key=key, items=items, vectorizer=None, matrix=None)
    texts = [i["_text"] for i in items]
    if texts:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(stop_words="english")
            _IDX.update(vectorizer=vec, matrix=vec.fit_transform(texts), scorer="sparse-tfidf")
            return
        except Exception:
            pass
    _IDX["scorer"] = "token-overlap-fallback"


def search(q, k=5):
    """Relevance search over closed runs. Returns {scorer, items[], note} — every item structurally
    marked admissible_as_evidence: false."""
    _ensure_index()
    items = _IDX["items"]
    scored = []
    if items:
        if _IDX["scorer"] == "sparse-tfidf":
            from sklearn.metrics.pairwise import linear_kernel
            sims = linear_kernel(_IDX["vectorizer"].transform([q]), _IDX["matrix"])[0]
            scored = list(zip(items, sims))
        else:
            qt = _tokens(q)
            scored = [(i, len(qt & _tokens(i["_text"])) / (len(qt | _tokens(i["_text"])) or 1))
                      for i in items]
        scored.sort(key=lambda x: x[1], reverse=True)
    out = [{**{kk: vv for kk, vv in i.items() if kk != "_text"},
            "score": round(float(s), 4),
            "admissible_as_evidence": False,
            "why_not_admissible": WHY_NOT_ADMISSIBLE}
           for i, s in scored[:max(1, min(k, 50))] if s > 0]
    return {"scorer": _IDX["scorer"] or "none", "n_closed_runs": len(items), "items": out,
            "note": "citation series are disjoint by construction: numbers = evidence, letters = precedent"}


# --- disjoint citation series (handoff §2.5) ---------------------------------------------------------

def letter_label(i):
    """1 -> A, 26 -> Z, 27 -> AA — the PRECEDENT series; evidence uses integers (runs.py)."""
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def serialize_disjoint(evidence_citations, precedent_items):
    """Two series that cannot produce each other's labels: evidence keeps its numeric `n`
    (already normalized by runs.py); precedent gets letters `l`. Rejecting a letter inside the
    evidence series is validate_disjoint's job — deterministic, not disciplinary."""
    precedent = [{"l": letter_label(i), "run_id": p["run_id"],
                  "question": (p.get("question") or "")[:200],
                  "admissible_as_evidence": False}
                 for i, p in enumerate(precedent_items or [], 1)]
    return {"evidence": list(evidence_citations or []), "precedent": precedent}


def validate_disjoint(serialized):
    """Deterministic gate: every evidence entry carries an integer `n` (never a letter label);
    every precedent entry carries a letter `l` (never a number) + admissible_as_evidence false."""
    ev_ok = all(isinstance(c.get("n"), int) and "l" not in c for c in serialized.get("evidence", []))
    pr_ok = all(re.fullmatch(r"[A-Z]+", str(c.get("l", ""))) and "n" not in c
                and c.get("admissible_as_evidence") is False
                for c in serialized.get("precedent", []))
    return ev_ok and pr_ok
