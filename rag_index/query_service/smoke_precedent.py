"""smoke_precedent.py — gate determinista de la capa de precedente (bloque 6, ADR-0053).

Cubre: solo corridas CERRADAS son precedente; busqueda por relevancia con scorer DECLARADO (tfidf o
fallback — jamas un fallback disfrazado); admissible_as_evidence=false ESTRUCTURAL en cada item;
series de citas disjuntas por construccion (numeros=evidencia, letras=precedente) + su validador
determinista; y el endpoint con auth.

100% offline: SQLite tmp, cero red/spend/mutacion DI. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_precedent.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_precedent_"))
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{TMP / 'backend.db'}"
os.environ.pop("NEO4J_URI", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
import db  # noqa: E402
import precedent  # noqa: E402
from fastapi import HTTPException  # noqa: E402

os.environ.pop("NEO4J_URI", None)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _mk_run(run_id, question, answer, state="closed", verdict="APPROVE", conf=0.8):
    db.create_run(run_id, "natalia", question)
    frozen = {"answer": {"direct_answer": answer}, "audit": {"verdict": verdict},
              "confidence": {"final": conf}, "decision_state": {"state": "AUDIT_APPROVED"}}
    values = {"state": state, "frozen_record_json": json.dumps(frozen)}
    if state == "closed":
        values.update(frozen_at=db._now(), closed_by="natalia")
    db.update_run(run_id, **values)


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
AUTH = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))["token"]

# ---- 1. indice vacio: honesto, con scorer declarado --------------------------------------------------
r = precedent.search("anything")
check("sin corridas cerradas: items=[] + scorer declarado", r["items"] == [] and r["n_closed_runs"] == 0)

# ---- 2. solo lo CERRADO es precedente ----------------------------------------------------------------
_mk_run("r" + "1" * 31, "Is wt1a required for zebrafish pronephros development?",
        "The evidence does not support a direct answer about wt1a and pronephros.")
_mk_run("r" + "2" * 31, "What does BMP signaling do in dorsoventral patterning?",
        "BMP gradients pattern the dorsoventral axis via smad5.")
_mk_run("r" + "3" * 31, "pending question never closed", "irrelevant", state="awaiting_closure")
precedent._IDX["key"] = None   # invalidar cache del indice
r = precedent.search("wt1a pronephros development", k=5)
check("solo corridas closed en el corpus (awaiting_closure NO es precedente)",
      r["n_closed_runs"] == 2)
check("relevancia: la corrida de wt1a/pronephros rankea primero",
      r["items"] and r["items"][0]["run_id"] == "r" + "1" * 31,
      f"scorer={r['scorer']} top_score={r['items'][0]['score'] if r['items'] else '-'}")
check("scorer DECLARADO (jamas un fallback disfrazado)",
      r["scorer"] in ("sparse-tfidf", "token-overlap-fallback"), r["scorer"])
check("cada item: admissible_as_evidence=false ESTRUCTURAL + porque",
      all(i["admissible_as_evidence"] is False and i["why_not_admissible"] for i in r["items"]))
check("item trae lo que la UI necesita (verdict, confianza, excerpt, frozen_at)",
      all(("verdict" in i and "confidence_final" in i and "answer_excerpt" in i
           and i.get("frozen_at")) for i in r["items"]))

# ---- 3. series disjuntas por construccion ------------------------------------------------------------
check("letras: 1->A, 26->Z, 27->AA (serie de precedente)",
      precedent.letter_label(1) == "A" and precedent.letter_label(26) == "Z"
      and precedent.letter_label(27) == "AA")
check("score 0 se filtra (BMP no matchea wt1a) — el ranking no rellena con ruido",
      len(r["items"]) == 1)
ev = [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}]
two_precedents = r["items"] + [{"run_id": "r" + "2" * 31, "question": "BMP dorsoventral"}]
ser = precedent.serialize_disjoint(ev, two_precedents)
check("serialize_disjoint: evidencia numerica intacta + precedente con letras A,B",
      ser["evidence"] == ev and [p["l"] for p in ser["precedent"]] == ["A", "B"]
      and all(p["admissible_as_evidence"] is False for p in ser["precedent"]))
check("validate_disjoint acepta series correctas", precedent.validate_disjoint(ser) is True)
bad = {"evidence": [{"n": 1}, {"l": "A"}], "precedent": ser["precedent"]}
check("validate_disjoint RECHAZA una letra colada en la serie de evidencia",
      precedent.validate_disjoint(bad) is False)
bad2 = {"evidence": ev, "precedent": [{"l": "A", "n": 2, "run_id": "x", "admissible_as_evidence": False}]}
check("validate_disjoint RECHAZA un numero colado en la serie de precedente",
      precedent.validate_disjoint(bad2) is False)

# ---- 4. endpoint con auth ------------------------------------------------------------------------------
def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


check("GET /precedent/search sin token -> 401",
      _http_error(app.precedent_search, "wt1a", authorization=None) == 401)
rr = app.precedent_search("wt1a pronephros", k=3, authorization=AUTH)
check("endpoint devuelve el mismo objeto (scorer + items marcados)",
      rr["scorer"] == r["scorer"] and rr["items"][0]["admissible_as_evidence"] is False)
check("q vacia -> 400", _http_error(app.precedent_search, "  ", authorization=AUTH) == 400)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
