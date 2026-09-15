"""smoke_precedent.py — gate determinista de la capa de precedente (bloque 6, ADR-0053).

Cubre: solo corridas CERRADAS son precedente; busqueda por relevancia con scorer DECLARADO (tfidf o
fallback — jamas un fallback disfrazado); admissible_as_evidence=false ESTRUCTURAL en cada item;
series de citas disjuntas por construccion (numeros=evidencia, letras=precedente) + su validador
determinista; y el endpoint con auth.

ADR-0079 (origen + investigacion): el corpus se acota por `runs.origin` (default: solo 'production' +
NULL declarado como pre-ADR); `include_origins` amplia; la respuesta declara origins_included /
excluded_by_origin / origin_unknown_included; los items traen thread_id/turn_no/turn_kind/origin; el
turno padre se serializa como LETRA (kind 'turn') y jamas como numero; el PDF imprime el precedente en
letras con 'NO ADMISIBLE COMO EVIDENCIA' y declara 'NO INSTRUMENTADO' en registros pre-1.8.

Decision de origen para ESTE smoke: las corridas base se marcan origin='production' EXPLICITAMENTE
(la BD es SQLite temporal — no contamina nada) para que el alcance por default se sostenga sea cual
sea WITT_RUN_ORIGIN en el entorno; la exclusion se prueba con corridas marcadas 'smoke'/'simulation'.

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


# ---- ADR-0079: origen/turno de las corridas del smoke -------------------------------------------------
# El smoke escribe las columnas de la espec (runs.origin / thread_id / turn_no / turn_kind) DIRECTO en la
# fila — aqui no hay servidor que las derive (la derivacion al encolar la cubre smoke_runs_thread_http.py).
# Si db.closed_runs no expone alguna de estas columnas, el check del item FALLA: la asimetria lista/detalle
# que rompio dos veces (ADR-0055/0076), atrapada a la primera.
_TURN_KEYS = ("origin", "thread_id", "turn_no", "turn_kind")


def _mk_run(run_id, question, answer, state="closed", verdict="APPROVE", conf=0.8, origin="production",
            **turn):
    assert set(turn) <= set(_TURN_KEYS), turn
    db.create_run(run_id, "natalia", question, origin=origin, **turn)
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
        "The evidence does not support a direct answer about wt1a and pronephros.",
        origin="production", thread_id="r" + "1" * 31, turn_no=1, turn_kind="root")
_mk_run("r" + "2" * 31, "What does BMP signaling do in dorsoventral patterning?",
        "BMP gradients pattern the dorsoventral axis via smad5.",
        origin=None)   # ADR-0079: NULL explicito = corrida anterior a la columna (se incluye y se declara)
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

# ---- 5. ADR-0079: el corpus se acota por ORIGEN — por default solo 'production' + NULL declarado ---------
check("ADR-0079a: la respuesta DECLARA su alcance (origins_included=['production']) y el NULL incluido "
      "se cuenta (origin_unknown_included=1: la corrida BMP nacio sin origin)",
      rr["origins_included"] == ["production"] and rr["origin_unknown_included"] == 1
      and rr["excluded_by_origin"] == {} and "ADR-0074" in rr["origin_policy"],
      f"included={rr['origins_included']} unknown={rr['origin_unknown_included']}")
check("ADR-0079b: el item trae su turno y su origen (thread_id/turn_no/turn_kind/origin) — raiz = turno 1",
      rr["items"][0]["thread_id"] == "r" + "1" * 31 and rr["items"][0]["turn_no"] == 1
      and rr["items"][0]["turn_kind"] == "root" and rr["items"][0]["origin"] == "production",
      json.dumps({k: rr["items"][0].get(k) for k in ("thread_id", "turn_no", "turn_kind", "origin")})
      + ("" if rr["items"][0]["turn_kind"] == "root" else
         "  [GAP lista/detalle: db.closed_runs no SELECTea runs.c.turn_kind — un None aqui se leeria "
         "como 'sin investigacion' en una corrida que SI es raiz; agregar la columna al SELECT]"))
# una corrida de SMOKE cerrada y muy relevante: NO debe entrar al precedente por default
_mk_run("r" + "4" * 31, "wt1a pronephros development in zebrafish (smoke run)",
        "wt1a pronephros development — synthetic smoke answer.", origin="smoke")
_mk_run("r" + "5" * 31, "wt1a pronephros simulation", "simulated wt1a pronephros answer.", origin="simulation")
precedent._IDX["key"] = None
r_def = precedent.search("wt1a pronephros development", k=5)
check("ADR-0079c: por default las corridas 'smoke' y 'simulation' se EXCLUYEN y se CUENTAN "
      "(excluded_by_origin={'simulation':1,'smoke':1}); n_closed_runs no las cuenta",
      r_def["n_closed_runs"] == 2 and r_def["excluded_by_origin"] == {"simulation": 1, "smoke": 1}
      and all(i["run_id"] not in ("r" + "4" * 31, "r" + "5" * 31) for i in r_def["items"]),
      f"n={r_def['n_closed_runs']} excl={r_def['excluded_by_origin']}")
r_inc = precedent.search("wt1a pronephros development", k=5, include_origins=["production", "smoke"])
check("ADR-0079d: include_origins=['production','smoke'] amplia el alcance de forma EXPLICITA — la smoke "
      "entra, la simulation sigue excluida y declarada; el alcance viaja en la respuesta",
      r_inc["n_closed_runs"] == 3 and r_inc["origins_included"] == ["production", "smoke"]
      and r_inc["excluded_by_origin"] == {"simulation": 1}
      and any(i["run_id"] == "r" + "4" * 31 and i["origin"] == "smoke" for i in r_inc["items"]),
      f"n={r_inc['n_closed_runs']} excl={r_inc['excluded_by_origin']}")
check("ADR-0079e: dos alcances = dos indices (la cache lleva el alcance en su llave; jamas se mezclan)",
      precedent.search("wt1a pronephros development", k=5)["n_closed_runs"] == 2
      and precedent.search("wt1a pronephros development", k=5,
                           include_origins="production,smoke,simulation")["n_closed_runs"] == 4)
check("ADR-0079f: el endpoint por default sigue acotado a production + NULL y declara el alcance",
      app.precedent_search("wt1a pronephros", k=5, authorization=AUTH)["origins_included"] == ["production"]
      and app.precedent_search("wt1a pronephros", k=5, authorization=AUTH)["excluded_by_origin"]
      == {"simulation": 1, "smoke": 1})

# ---- 6. ADR-0079: el turno padre es PRECEDENTE en LETRAS (kind 'turn') — jamas un numero ---------------
parent_row = {"run_id": "r" + "1" * 31, "question": "Is wt1a required for zebrafish pronephros development?",
              "run_no": 1, "turn_no": 1}
ser_t = precedent.serialize_disjoint(ev, [precedent.turn_item(parent_row)])
pc = ser_t["precedent"][0]
check("ADR-0079g: turn_item -> serialize_disjoint da 'l':'A', kind 'turn', run_no/turn_no, "
      "admissible_as_evidence False, why_not_admissible en palabras y SIN 'n'",
      pc["l"] == "A" and pc["kind"] == "turn" and pc["run_no"] == 1 and pc["turn_no"] == 1
      and pc["admissible_as_evidence"] is False and pc["why_not_admissible"] == precedent.WHY_NOT_ADMISSIBLE
      and "n" not in pc and precedent.validate_disjoint(ser_t) is True, json.dumps(pc)[:160])
hand_made = {"evidence": ev, "precedent": [{"label": "A", "run_id": "x", "admissible_as_evidence": False}]}
check("ADR-0079h: una cita de precedente hecha a mano con 'label' en vez de 'l' NO pasa validate_disjoint",
      precedent.validate_disjoint(hand_made) is False)
check("ADR-0079i: sin padre, serialize_disjoint([]) da precedent=[] y valida (la lista vacia se declara)",
      precedent.serialize_disjoint(ev, [])["precedent"] == [] and precedent.validate_disjoint(
          precedent.serialize_disjoint(ev, [])) is True)

# ---- 7. ADR-0079: el PDF imprime el precedente en LETRAS y declara los tres estados --------------------
import record_pdf  # noqa: E402

# Costura de prueba: fpdf parte las lineas largas al ancho de pagina, asi que buscar frases en los bytes
# del PDF es fragil. Se envuelven _p/_h/_band para capturar el TEXTO que la plantilla mando a imprimir
# (el PDF se genera igual — la captura es solo lectura).
_PDF_TEXT = []
for _fn_name in ("_p", "_h", "_band"):
    _orig = getattr(record_pdf, _fn_name)

    def _capturing(pdf, text, *a, __orig=_orig, **kw):
        _PDF_TEXT.append(record_pdf._t(text))
        return __orig(pdf, text, *a, **kw)

    setattr(record_pdf, _fn_name, _capturing)


def _pdf_text(record):
    del _PDF_TEXT[:]
    raw = record_pdf.build_pdf(record, compress=False)
    return raw, "\n".join(_PDF_TEXT)


_base_rec = {"run_id": "r" + "9" * 31, "render_contract_version": "1.8", "question": "child q",
             "decision_state": {"state": "AUDIT_APPROVED", "may_answer_now": True},
             "retrieval_summary": {"mode": "semantic", "retrievals": 3, "aggregation": "rrf"},
             "audit": {"verdict": "APPROVE", "n_valid": 3, "panel": []},
             "answer": {"direct_answer": "child answer", "gap_flags": []},
             "confidence": {"state": "value", "final": 0.7, "source": "stated", "pass1": 0.7},
             "citations": ev, "alternatives_considered": []}
rec_child = {**_base_rec,
             "thread": {"thread_id": "r" + "1" * 31, "parent_run_id": "r" + "1" * 31, "turn_no": 2,
                        "turn_kind": "refine", "parent_state": "closed", "parent_run_no": 1,
                        "root_question_id": None,
                        "root_run_no": 1},   # corrector: la etiqueta T-N sale SOLO de aqui (cero inferencia)
             "thread_context": {"bytes": 812, "snapshot_at": "2026-09-15T00:00:00+00:00",
                                "human_comments": [], "truncated": False,
                                "kill_switch": {"WITT_THREAD_CONTEXT": "1"}},
             "thread_parent_matches_run": True, "thread_parent_matches_run_state": "checked",
             "precedent_citations": ser_t["precedent"], "precedent_citations_state": "checked",
             "origin": {"value": "production", "source": "env:WITT_RUN_ORIGIN"},
             "episode_axes": {"world": "effect-claimed", "inference": "supported", "technical": "completed",
                              "provenance": {"origin": "production",
                                             "human_gates": {"plan_declared": True, "closed": False},
                                             "turn": {"thread_id": "r" + "1" * 31, "turn_no": 2,
                                                      "turn_kind": "refine"}}}}
pdf_c, txt_c = _pdf_text(rec_child)
check("ADR-0079j: el PDF trae la seccion INVESTIGACION con T-<run_no raiz>, turno 2/refine, padre #1, "
      "la letra [A] marcada NO ADMISIBLE COMO EVIDENCIA, origen e identidad del padre",
      pdf_c[:5] == b"%PDF-" and "INVESTIGACION" in txt_c and "investigacion T-1" in txt_c
      and "turno 2 - refinamiento" in txt_c and "padre: corrida #1" in txt_c
      and "[A] turn: turno 1 - corrida #1" in txt_c and "NO ADMISIBLE COMO EVIDENCIA" in txt_c
      and "origen: production" in txt_c and "identidad del padre: COINCIDE" in txt_c)
check("ADR-0079k: el PDF trae EJES DEL EPISODIO en palabras (mundo/inferencia/tecnico/procedencia), "
      "ARRIBA de la respuesta (el orden de lectura es el orden de confianza)",
      "EJES DEL EPISODIO" in txt_c and "MUNDO: se afirma un efecto" in txt_c
      and "INFERENCIA: sostenida (APPROVE)" in txt_c and "TECNICO: completada" in txt_c
      and "PROCEDENCIA: origen production" in txt_c and "derived-at-freeze" in txt_c
      and txt_c.index("EJES DEL EPISODIO") < txt_c.index("RESPUESTA"))
pdf_old, txt_old = _pdf_text(_base_rec)
check("ADR-0079l: un registro SIN las llaves (contrato < 1.8) imprime NO INSTRUMENTADO en ambas secciones "
      "— jamas se rellena con 'raiz' ni con 'production'",
      txt_old.count("NO INSTRUMENTADO (contrato < 1.8)") == 4 and "turno 1" not in txt_old
      and "origen: production" not in txt_old and "MUNDO:" not in txt_old,
      f"n_no_instrumentado={txt_old.count('NO INSTRUMENTADO (contrato < 1.8)')}")
rec_root = {**_base_rec,
            "thread": {"thread_id": "r" + "9" * 31, "parent_run_id": None, "turn_no": 1, "turn_kind": "root",
                       "parent_state": None, "parent_run_no": None, "root_question_id": None},
            "thread_context": None, "thread_context_skipped_reason": "root-turn",
            "thread_parent_matches_run": None, "thread_parent_matches_run_state": "no-parent",
            "precedent_citations": [], "precedent_citations_state": "no-parent",
            "origin": {"value": None, "source": "derived:offline-mask"}, "episode_axes": None}
pdf_root, txt_root = _pdf_text(rec_root)
check("ADR-0079m: raiz con null-declarados: thread_context null con razon 'root-turn', precedente vacio "
      "declarado, origen null como pre-ADR, ejes null declarados — tres estados, no dos",
      "razon: root-turn" in txt_root and "lista vacia declarada" in txt_root
      and "unknown-pre-adr-0079" in txt_root and "episode_axes: null declarado" in txt_root
      and "padre: ninguno (turno raiz)" in txt_root and "NO INSTRUMENTADO (contrato < 1.8)" not in txt_root
      and "identidad del padre: no aplica" in txt_root)
# corrector ADR-0079: los TRES estados del null — un hijo con kill-switch ('no-snapshot') o con padre failed
# ('parent-without-frozen-record') NO es 'turno raiz'; el precedente vacio dice POR QUE; sin _state = 'no consta'
rec_ksw = {**rec_child, "thread_context": None, "thread_context_skipped_reason": "kill-switch WITT_THREAD_CONTEXT=0",
           "thread_parent_matches_run": None, "thread_parent_matches_run_state": "no-snapshot",
           "precedent_citations": [], "precedent_citations_state": "parent-not-closed"}
_, txt_ksw = _pdf_text(rec_ksw)
rec_dead = {**rec_ksw, "thread_parent_matches_run_state": "parent-without-frozen-record",
            "precedent_citations_state": "parent-without-frozen-record"}
_, txt_dead = _pdf_text(rec_dead)
rec_nost = {k: v for k, v in rec_ksw.items() if k not in ("thread_parent_matches_run_state", "precedent_citations_state")}
_, txt_nost = _pdf_text(rec_nost)
check("ADR-0079n (corrector): thread_parent_matches_run null se pinta por su _state — 'no-snapshot' -> 'no verificable: el "
      "snapshot no viajo', 'parent-without-frozen-record' -> 'el padre no tiene registro congelado', sin _state -> 'estado no "
      "consta'; NINGUNO dice 'turno raiz'; el precedente vacio declara su razon ('no esta cerrado' / 'sin registro' / 'no consta')",
      "identidad del padre: no verificable: el snapshot no viajo" in txt_ksw and "turno raiz) - null" not in txt_ksw
      and "el padre no esta cerrado - no es precedente" in txt_ksw
      and "identidad del padre: no verificable: el padre no tiene registro congelado" in txt_dead
      and "el padre no tiene registro congelado (failed/cancelled)" in txt_dead and "turno raiz) - null" not in txt_dead
      and "identidad del padre: estado no consta" in txt_nost and "razon no consta" in txt_nost
      and "turno raiz) - null" not in txt_nost)
rec_noroot = {**rec_child, "thread": {k: v for k, v in rec_child["thread"].items() if k != "root_run_no"}}
_, txt_noroot = _pdf_text(rec_noroot)
check("ADR-0079o (corrector): sin thread.root_run_no el PDF declara 'T-? (el run_no de la raiz no consta …)' — jamas infiere "
      "T-1 del parent_run_no de un turno 2 (la rama que inferia se quito)",
      "T-? (el run_no de la raiz no consta" in txt_noroot and "investigacion T-1" not in txt_noroot)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
