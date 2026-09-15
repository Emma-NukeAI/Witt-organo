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

ADR-0079 (investigación + origen): the corpus is filtered by `runs.origin` — by default ONLY
'production' runs are precedent; smoke/simulation/fixture/replay/dev-offline runs are EXCLUDED and
COUNTED (`excluded_by_origin`). A run whose origin is NULL predates the column ('unknown-pre-adr-0079'):
it is INCLUDED and DECLARED (`origin_unknown_included`) — absence is declared, never backfilled
(ADR-0074). Callers widen the scope explicitly with `include_origins=[...]`; the response always says
which origins it is standing on (`origins_included`). Items carry their turn (thread_id / turn_no /
turn_kind) and origin so a reader can tell a root from a refine; the PARENT TURN of an investigation
can be serialized as a precedent citation (letter series, kind 'turn') — never as evidence.
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

_IDX = {"key": None, "items": [], "meta": None, "vectorizer": None, "matrix": None, "scorer": None}

# --- origin of a run (ADR-0079 F) ------------------------------------------------------------------
# The enum lives in runs.run_origin(); consumers only need the DEFAULT scope and the NULL rule.
DEFAULT_ORIGINS = ("production",)
ORIGIN_UNKNOWN = "unknown-pre-adr-0079"   # runs.origin IS NULL: born before the column — declared, not filled
ORIGIN_POLICY = ("por default solo origin 'production' cuenta como precedente/calibracion; smoke, "
                 "simulation, fixture, replay y dev-offline se EXCLUYEN y se CUENTAN "
                 "(excluded_by_origin). origin NULL = corrida anterior a ADR-0079: se INCLUYE y se "
                 "DECLARA (origin_unknown_included) — la ausencia no se rellena (ADR-0074). "
                 "include_origins=[...] amplia el alcance de forma explicita")


def origin_of(row):
    """`runs.origin` read TOLERANTLY (ADR-0074): a row without the key (a SELECT older than the column)
    or with NULL is the same declared state — 'born before ADR-0079'. Never guessed."""
    if not isinstance(row, dict):
        return None
    return row.get("origin") or None


def normalize_origins(include_origins):
    """None -> the default scope; a list/tuple/CSV -> a sorted, de-duplicated tuple (deterministic)."""
    if include_origins is None:
        return tuple(DEFAULT_ORIGINS)
    if isinstance(include_origins, str):
        include_origins = include_origins.split(",")
    vals = sorted({str(o).strip() for o in include_origins if str(o).strip()})
    return tuple(vals) if vals else tuple(DEFAULT_ORIGINS)


def origin_declaration(include_origins=None):
    """The DECLARATION every origin-scoped response carries (ADR-0079 F): origins_included,
    excluded_by_origin {origin: n}, origin_unknown_included (NULL rows that passed) and the policy in
    words. Counted by db.excluded_by_origin over the SAME base as the corpus (state == closed) — so the
    counts are whole even when the corpus itself is LIMITed. Shared by precedent and calibration."""
    origins = normalize_origins(include_origins)
    counts = db.excluded_by_origin(list(origins), states=("closed",))
    return {"origins_included": list(origins),
            "excluded_by_origin": dict(counts.get("excluded_by_origin") or {}),
            "origin_unknown_included": int(counts.get("origin_unknown_included") or 0),
            "origin_unknown_label": ORIGIN_UNKNOWN,
            "origin_policy": ORIGIN_POLICY}


def closed_runs_scoped(include_origins=None, limit=1000):
    """Closed runs INSIDE the origin scope + the declaration of what stayed outside. ONE door for both
    consumers (precedent corpus, calibration report): the filter runs in SQL (db._origin_where, NULL
    included), the counts come from the same base. Returns (rows, declaration)."""
    origins = normalize_origins(include_origins)
    rows = db.closed_runs(limit=limit, include_origins=list(origins))
    return rows, origin_declaration(origins)


def filter_by_origin(rows, include_origins=None):
    """Pure counterpart of closed_runs_scoped for rows ALREADY in hand (no DB): same rule — NULL origin
    kept and counted as unknown, anything outside the scope excluded and counted. Returns (kept, meta)."""
    origins = normalize_origins(include_origins)
    kept, excluded, n_unknown = [], {}, 0
    for r in rows:
        o = origin_of(r)
        if o is None:
            n_unknown += 1
            kept.append(r)
        elif o in origins:
            kept.append(r)
        else:
            excluded[o] = excluded.get(o, 0) + 1
    meta = {"origins_included": list(origins),
            "excluded_by_origin": dict(sorted(excluded.items())),
            "origin_unknown_included": n_unknown,
            "origin_unknown_label": ORIGIN_UNKNOWN,
            "origin_policy": ORIGIN_POLICY}
    return kept, meta


def _turn_of(row):
    """The run's place in its investigation (ADR-0079 A), read tolerantly: NULL/missing = the run
    predates the thread columns ('sin investigación') — declared as None, never as turn 1."""
    return {"run_no": row.get("run_no"),
            "thread_id": row.get("thread_id"),
            "turn_no": row.get("turn_no"),
            "turn_kind": row.get("turn_kind"),
            "origin": origin_of(row)}


def _corpus(include_origins=None):
    """Closed runs -> precedent items, scoped by origin (ADR-0079 F). Returns (items, origin_meta)."""
    rows, meta = closed_runs_scoped(include_origins)
    items = []
    for r in rows:
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
            **_turn_of(r),
            "_text": f"{r['question']} {ans.get('direct_answer') or ''}",
        })
    return items, meta


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _ensure_index(include_origins=None):
    items, meta = _corpus(include_origins)
    # ADR-0079: the origin scope is part of the cache identity — two scopes, two indices, never mixed.
    key = (len(items), items[0]["frozen_at"] if items else None, tuple(meta["origins_included"]),
           tuple(sorted(meta["excluded_by_origin"].items())))
    if _IDX["key"] == key:
        return
    _IDX.update(key=key, items=items, meta=meta, vectorizer=None, matrix=None)
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


def search(q, k=5, include_origins=None):
    """Relevance search over closed runs. Returns {scorer, items[], note} — every item structurally
    marked admissible_as_evidence: false. ADR-0079: scoped by origin (default 'production' + NULL
    declared); the response carries origins_included / excluded_by_origin / origin_unknown_included."""
    _ensure_index(include_origins)
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
    meta = _IDX["meta"] or origin_declaration(include_origins)
    return {"scorer": _IDX["scorer"] or "none", "n_closed_runs": len(items), "items": out,
            **meta,
            "note": "citation series are disjoint by construction: numbers = evidence, letters = precedent"}


# --- disjoint citation series (handoff §2.5) ---------------------------------------------------------

def letter_label(i):
    """1 -> A, 26 -> Z, 27 -> AA — the PRECEDENT series; evidence uses integers (runs.py)."""
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# Keys a precedent item may carry INTO the letter series besides run_id/question (ADR-0079 E: the
# parent TURN of an investigation is precedent with kind 'turn'). `n` is never among them —
# validate_disjoint rejects it.
_PRECEDENT_PASSTHROUGH = ("run_no", "turn_no", "kind")


def serialize_disjoint(evidence_citations, precedent_items):
    """Two series that cannot produce each other's labels: evidence keeps its numeric `n`
    (already normalized by runs.py); precedent gets letters `l`. Rejecting a letter inside the
    evidence series is validate_disjoint's job — deterministic, not disciplinary.

    ADR-0079: an item may carry run_no / turn_no / kind (kind 'turn' = the parent turn); they pass
    through untouched, and every letter ships why_not_admissible in words."""
    precedent = []
    for i, p in enumerate(precedent_items or [], 1):
        item = {"l": letter_label(i), "run_id": p["run_id"],
                "question": (p.get("question") or "")[:200],
                "admissible_as_evidence": False,
                "why_not_admissible": WHY_NOT_ADMISSIBLE}
        for k in _PRECEDENT_PASSTHROUGH:
            # corrector ADR-0079: a key the item CARRIES passes through even when null — a pre-ADR parent
            # has turn_no None and the record must declare that absence (three states), not drop the key
            if k in p:
                item[k] = p[k]
        precedent.append(item)
    return {"evidence": list(evidence_citations or []), "precedent": precedent}


def turn_item(parent_row):
    """The parent turn of an investigation as a precedent item (ADR-0079 E): {run_id, question, run_no,
    turn_no, kind: 'turn'} — feed it to serialize_disjoint; it comes out as a LETTER, never a number."""
    return {"run_id": parent_row["run_id"], "question": parent_row.get("question"),
            "run_no": parent_row.get("run_no"), "turn_no": parent_row.get("turn_no"), "kind": "turn"}


def validate_disjoint(serialized):
    """Deterministic gate: every evidence entry carries an integer `n` (never a letter label);
    every precedent entry carries a letter `l` (never a number) + admissible_as_evidence false."""
    ev_ok = all(isinstance(c.get("n"), int) and "l" not in c for c in serialized.get("evidence", []))
    pr_ok = all(re.fullmatch(r"[A-Z]+", str(c.get("l", ""))) and "n" not in c
                and c.get("admissible_as_evidence") is False
                for c in serialized.get("precedent", []))
    return ev_ok and pr_ok
