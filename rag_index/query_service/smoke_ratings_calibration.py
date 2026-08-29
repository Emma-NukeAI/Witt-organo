"""smoke_ratings_calibration.py — gate determinista de M5 ratings + /calibration (tapón 4, ADR-0064).

Cubre: validación de ejes (el [?] explícito, nunca silencioso; 1-5 estricto), procedencia DERIVADA
(is_author/instrument/rater_profile/saw_answer, jamás del cliente), append-only (correcciones = filas
nuevas), enmascaramiento de independencia M5 aplicado en el SERVIDOR (record + ratings + eventos sin
scores), consenso que cuenta sin promediar, la cola de pendientes, y el reporte de calibración: mapeo
declarado, poder declarado con n<umbral (jamás un número ciego), la ruta n>=10 con isotonic, y la
separación médico/dev.

100% offline: BD = SQLite tmp; cero red, cero OpenAI, cero mutación de la DATA INAMOVIBLE.
Corre:  python rag_index/query_service/smoke_ratings_calibration.py   (venv del servicio, NO el del MCP)
"""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_ratings_"))
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{TMP / 'backend.db'}"
os.environ.pop("NEO4J_URI", None)
os.environ.pop("RAG_BACKEND", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
import calibration  # noqa: E402
import db  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from lib import rag_backend  # noqa: E402

os.environ.pop("NEO4J_URI", None)   # el import de app puede repoblarlo desde .secrets/deploy.env

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-nat")
db.upsert_user("marcelo", "Marcelo", "medico", "pw-mar")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emm")
AUTH_NAT = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-nat"))["token"]
AUTH_MAR = "Bearer " + app.login(app.LoginBody(username="marcelo", password="pw-mar"))["token"]
AUTH_EMM = "Bearer " + app.login(app.LoginBody(username="emmanuel", password="pw-emm"))["token"]


def mk_run(author, state="closed", conf=0.9, conf_state="value", conf_source="stated", frozen=True):
    """Corrida sintética directa a BD (el pipeline real lo cubre smoke_run_pipeline.py)."""
    rid = uuid.uuid4().hex
    db.create_run(rid, author, f"q-{rid[:8]}")
    values = {"state": state}
    if frozen:
        rec = {"run_id": rid, "confidence": {"final": conf, "state": conf_state, "source": conf_source},
               "audit": {"verdict": "APPROVE_MINOR"}}
        values.update(frozen_record_json=json.dumps(rec), frozen_at=db._now())
    db.update_run(rid, **values)
    return rid


# ---- 1. validación del POST --------------------------------------------------------------------------
r_run = mk_run("natalia", state="awaiting_closure")
r_running = mk_run("natalia", state="running", frozen=False)

check("calificar una corrida en curso -> 409 (solo corridas terminadas)",
      _http_error(app.add_rating, r_running, app.RatingBody(rating_input=4, rating_output=4),
                  authorization=AUTH_NAT) == 409)
check("corrida inexistente -> 404",
      _http_error(app.add_rating, "nope", app.RatingBody(rating_input=4, rating_output=4),
                  authorization=AUTH_NAT) == 404)
check("sin token -> 401",
      _http_error(app.add_rating, r_run, app.RatingBody(rating_input=4, rating_output=4),
                  authorization=None) == 401)
check("eje sin valor y sin estado -> 400 (la ausencia silenciosa no existe, M5)",
      _http_error(app.add_rating, r_run, app.RatingBody(rating_output=4),
                  authorization=AUTH_NAT) == 400)
check("valor fuera de 1-5 -> 400",
      _http_error(app.add_rating, r_run, app.RatingBody(rating_input=7, rating_output=4),
                  authorization=AUTH_NAT) == 400)
check("estado cannot-rate CON número -> 400 (un estado no-value no lleva número)",
      _http_error(app.add_rating, r_run,
                  app.RatingBody(rating_input=4, rating_input_state="cannot-rate", rating_output=4),
                  authorization=AUTH_NAT) == 400)
check("estado inválido -> 400",
      _http_error(app.add_rating, r_run,
                  app.RatingBody(rating_input=4, rating_output=None, rating_output_state="whatever"),
                  authorization=AUTH_NAT) == 400)

# ---- 2. procedencia derivada + append-only ------------------------------------------------------------
res = app.add_rating(r_run, app.RatingBody(rating_input=4, rating_output=3, note="ok"),
                     authorization=AUTH_NAT)
row = res["rating"]
check("autora: instrument=m5-cierre, is_author, rater_profile=medico, saw_answer (hay registro), blind=False",
      row["instrument"] == "m5-cierre" and row["is_author"] is True
      and row["rater_profile"] == "medico" and row["saw_answer_before_rating"] is True
      and row["blind"] is False and row["rated_by"] == "natalia")
res2 = app.add_rating(r_run, app.RatingBody(rating_input=4, rating_output=5),
                      authorization=AUTH_MAR)
check("no-autor: instrument=m5-consenso, is_author=False",
      res2["rating"]["instrument"] == "m5-consenso" and res2["rating"]["is_author"] is False)
res3 = app.add_rating(r_run, app.RatingBody(rating_input=5, rating_output=4, note="corrección"),
                      authorization=AUTH_NAT)
all_rows = db.ratings_for(r_run)
check("append-only: la corrección es fila NUEVA (3 filas, seq monotónico), nada se sobreescribe",
      len(all_rows) == 3 and [r["seq"] for r in all_rows] == [1, 2, 3]
      and all_rows[0]["rating_input"] == 4 and all_rows[2]["rating_input"] == 5)

# ---- 3. enmascaramiento M5 (servidor, no disciplina de UI) --------------------------------------------
view_emm = app.get_ratings(r_run, authorization=AUTH_EMM)
check("quien no ha calificado ve stubs SIN scores ni notas (ratings_masked + nota)",
      view_emm["ratings_masked"] is True and "ratings_masking_note" in view_emm
      and all("rating_output" not in r and "note" not in r and r.get("masked") for r in view_emm["ratings"]))
check("el consenso sí se ve (cuenta sin valores): invited=2, received=1 (marcelo), open, falta emmanuel",
      view_emm["consensus"]["invited"] == 2 and view_emm["consensus"]["received"] == 1
      and view_emm["consensus"]["open"] is True and view_emm["consensus"]["missing"] == ["emmanuel"])
view_nat = app.get_ratings(r_run, authorization=AUTH_NAT)
check("quien ya calificó ve todo (scores incluidos)",
      view_nat["ratings_masked"] is False
      and all("rating_output" in r for r in view_nat["ratings"]))
evs = db.events_after(r_run)
rating_evs = [e for e in evs if e["type"] == "rating.added"]
check("run_events registra rating.added SIN scores (la bitácora no perfora el enmascaramiento)",
      len(rating_evs) == 3
      and all(set(e["payload"]) == {"rated_by", "instrument", "seq", "rating_input_state",
                                    "rating_output_state"} for e in rating_evs))

# ---- 4. el registro congelado fusiona en LECTURA; el blob JAMÁS se reescribe --------------------------
rec_view = app.get_frozen_record(r_run, authorization=AUTH_EMM)
check("/record fusiona ratings (masked para emmanuel) + consensus sobre las mediciones congeladas",
      rec_view["ratings_masked"] is True and rec_view["consensus"]["received"] == 1
      and rec_view["confidence"]["final"] == 0.9)
blob = json.loads(db.get_run(r_run)["frozen_record_json"])
check("el blob congelado en BD sigue SIN llave ratings (dos zonas: mediciones inmutables, ratings aparte)",
      "ratings" not in blob and "consensus" not in blob)

# ---- 5. cola de pendientes ----------------------------------------------------------------------------
pend_emm = app.ratings_pending(authorization=AUTH_EMM)
check("pendientes de emmanuel: incluye la corrida (no ha calificado) con consenso y estado",
      any(p["run_id"] == r_run for p in pend_emm["pending"])
      and all("consensus" in p for p in pend_emm["pending"]))
pend_nat = app.ratings_pending(authorization=AUTH_NAT)
check("pendientes de natalia: la corrida ya NO aparece (ya calificó); la running jamás aparece",
      all(p["run_id"] != r_run for p in pend_nat["pending"])
      and all(p["run_id"] != r_running for p in pend_nat["pending"]))

# ---- 6. corrida muerta: calificable, sin respuesta que ver --------------------------------------------
r_dead = mk_run("marcelo", state="failed", frozen=False)
res_d = app.add_rating(r_dead, app.RatingBody(rating_input=3, rating_output=None,
                                              rating_output_state="not-applicable"),
                       authorization=AUTH_NAT)
check("corrida failed: se califica; output=not-applicable (no un 1); saw_answer=False (no hubo respuesta)",
      res_d["rating"]["rating_output_state"] == "not-applicable"
      and res_d["rating"]["rating_output"] is None
      and res_d["rating"]["saw_answer_before_rating"] is False)

# ---- 7. calibración: poder declarado con n chico ------------------------------------------------------
# Estado hasta aquí: 0 corridas CERRADAS (r_run está awaiting_closure) -> n_scored=0
cal0 = app.calibration_report(authorization=AUTH_EMM)
check("/calibration con 0 cerradas: n_scored=0, power.sufficient=False, status=infrastructure populated",
      cal0["n_scored"] == 0 and cal0["power"]["sufficient"] is False
      and cal0["power"]["status"] == "infrastructure populated" and cal0["ece"]["ece_raw"] is None)
check("/calibration declara el mapeo de outcomes y la clase NO-SPEND en la respuesta",
      "per_run" in cal0["outcome_mapping"] and "NO-SPEND" in cal0["cost_class"])

# corridas cerradas sintéticas: mapeo positivo / negativo / empate / abstención / sin confianza
r_pos = mk_run("natalia", conf=0.9)     # ratings 5,4 -> positivo
app.add_rating(r_pos, app.RatingBody(rating_input=4, rating_output=5), authorization=AUTH_NAT)
app.add_rating(r_pos, app.RatingBody(rating_input=4, rating_output=4), authorization=AUTH_MAR)
r_neg = mk_run("natalia", conf=0.8)     # ratings 2,1 -> negativo (sobre-confianza detectable)
app.add_rating(r_neg, app.RatingBody(rating_input=3, rating_output=2), authorization=AUTH_MAR)
app.add_rating(r_neg, app.RatingBody(rating_input=3, rating_output=1), authorization=AUTH_EMM)
r_tie = mk_run("marcelo", conf=0.7)     # 5 vs 1 -> empate -> excluida y contada
app.add_rating(r_tie, app.RatingBody(rating_input=3, rating_output=5), authorization=AUTH_NAT)
app.add_rating(r_tie, app.RatingBody(rating_input=3, rating_output=1), authorization=AUTH_EMM)
r_abs = mk_run("marcelo", conf=0.6)     # rating 3 -> abstención -> sin votos -> excluida
app.add_rating(r_abs, app.RatingBody(rating_input=3, rating_output=3), authorization=AUTH_NAT)
r_noc = mk_run("emmanuel", conf=None, conf_state="absent-not-calibratable", conf_source=None)
app.add_rating(r_noc, app.RatingBody(rating_input=4, rating_output=5), authorization=AUTH_NAT)
r_nor = mk_run("emmanuel", conf=0.5)    # cerrada con confianza pero SIN ratings -> excluida

cal1 = app.calibration_report(authorization=AUTH_EMM)
check("mapeo v1: 2 pares (positivo+negativo); empate/abstención/sin-confianza/sin-ratings excluidas y CONTADAS",
      cal1["n_scored"] == 2 and cal1["excluded"]["no_majority_or_tie"] == 2
      and cal1["excluded"]["no_confidence"] == 1 and cal1["excluded"]["no_ratings"] == 1,
      f"n={cal1['n_scored']} excl={cal1['excluded']}")
check("n=2 -> case capture, sin poder, ece descriptivo (jamás un número ciego)",
      cal1["power"]["status"] == "case capture" and cal1["power"]["sufficient"] is False
      and cal1["ece"]["ece_raw"] is not None and "descriptive-only" in cal1["ece"]["class"])
check("la última calificación por persona manda (append-only): corrección de natalia en r_run no rompe nada"
      " y by_instrument declara la mezcla",
      "m5-cierre" in cal1["by_instrument"] and "m5-consenso" in cal1["by_instrument"]
      and "banco" in cal1["by_instrument"]["note"])
check("confidence_sources tally la procedencia (stated)",
      cal1["confidence_sources"].get("stated", 0) >= 4)
check("separación médico/dev: en r_neg el dev también etiquetó; ambos perfiles tienen pares propios",
      cal1["by_rater_profile"]["medico"]["n"] >= 2 and cal1["by_rater_profile"]["dev"]["n"] >= 1,
      f"med={cal1['by_rater_profile']['medico']['n']} dev={cal1['by_rater_profile']['dev']['n']}")

# ---- 8. la ruta con poder (n>=10): isotonic presente --------------------------------------------------
for i in range(9):
    rid = mk_run("natalia", conf=0.55 + i * 0.05)
    app.add_rating(rid, app.RatingBody(rating_input=4, rating_output=5 if i % 3 else 2),
                   authorization=AUTH_MAR)
cal2 = app.calibration_report(authorization=AUTH_EMM)
check("con n>=10: aggregate-captured, power.sufficient=True, isotonic calculado",
      cal2["n_scored"] >= 10 and cal2["power"]["sufficient"] is True
      and cal2["power"]["status"] == "aggregate-captured"
      and cal2["ece"]["class"] == "aggregate" and "ece_after_isotonic" in cal2["ece"],
      f"n={cal2['n_scored']} ece={cal2['ece']['ece_raw']} iso={cal2['ece'].get('ece_after_isotonic')}")
check("power.note conserva la advertencia longitudinal (aggregate != satisfied, ADR-0030)",
      "satisfied" in cal2["power"]["note"])

# ---- 9. /calibration es NO-SPEND estructural ----------------------------------------------------------
_oq, _os = rag_backend.query, rag_backend.query_sparse


def _spend_trap(*a, **kw):
    raise AssertionError("NO-SPEND violado: /calibration tocó el retriever")


rag_backend.query, rag_backend.query_sparse = _spend_trap, _spend_trap
try:
    app.calibration_report(authorization=AUTH_EMM)
    nospend = True
except AssertionError:
    nospend = False
rag_backend.query, rag_backend.query_sparse = _oq, _os
check("/calibration jamás toca el retriever ni embebe (NO-SPEND)", nospend)

# ---- 9. M5 v2 (ADR-0075): la nota de la PREGUNTA + los cortes declarados ------------------------------
# El banco de calibración v1 midió que el texto libre fue lo ÚNICO que produjo diagnóstico accionable, y
# que atribuirlo sólo fue posible con DOS columnas separadas. Aquí se fija que existen las dos y que la
# nueva NO perfora el enmascaramiento.
r_v2 = mk_run("marcelo", state="closed", conf=0.8)
res_v2 = app.add_rating(r_v2, app.RatingBody(rating_input=3, rating_output=4,
                                             note="a la respuesta le faltó el glomérulo",
                                             note_question="la pregunta no cabía en una sola corrida"),
                        authorization=AUTH_NAT)
check("M5 v2: las DOS notas se persisten por separado (respuesta / pregunta)",
      res_v2["rating"]["note"] == "a la respuesta le faltó el glomérulo"
      and res_v2["rating"]["note_question"] == "la pregunta no cabía en una sola corrida")
check("M5 v2: la nota de la pregunta es OPCIONAL — sin ella la fila queda '' y se envía igual",
      app.add_rating(mk_run("marcelo", state="closed"),
                     app.RatingBody(rating_input=4, rating_output=4),
                     authorization=AUTH_NAT)["rating"]["note_question"] == "")
check("M5 v2: note_question de más de 4000 -> 400 (mismo tope que note)",
      _http_error(app.add_rating, mk_run("marcelo", state="closed"),
                  app.RatingBody(rating_input=4, rating_output=4, note_question="x" * 4001),
                  authorization=AUTH_NAT) == 400)
check("M5 v2: la fila enmascarada NO filtra note_question (allowlist, no denylist)",
      all("note_question" not in r for r in app.get_ratings(r_v2, authorization=AUTH_EMM)["ratings"]))

cal_v2 = app.calibration_report(authorization=AUTH_EMM)
check("M5 v2: /calibration declara el rol de cada eje — rating_input JAMÁS entró al ECE",
      "rating_input" in cal_v2["outcome_mapping"]["axis_roles"]
      and "NUNCA" in cal_v2["outcome_mapping"]["axis_roles"])
check("M5 v2: by_authorship trae m5-consenso y m5-cierre como bloques ECE PARALELOS",
      set(cal_v2["by_authorship"]) >= {"m5-consenso", "m5-cierre", "note"}
      and "n" in cal_v2["by_authorship"]["m5-consenso"])
check("M5 v2: raters cuenta de cuántas cabezas depende el número (autoexamen y calificador único)",
      isinstance(cal_v2["raters"]["n_runs_author_only"], int)
      and isinstance(cal_v2["raters"]["n_runs_single_rater"], int)
      and isinstance(cal_v2["raters"]["por_n_calificadores"], dict))
check("M5 v2: ece_excluding_declines existe y cuenta las declinaciones honestas apartadas",
      "n_excluded_declines" in cal_v2["ece_excluding_declines"]
      and "class" in cal_v2["ece_excluding_declines"])
check("M5 v2: el TITULAR no cambia — los cortes son paralelos, jamás reescriben `ece`",
      cal_v2["ece"]["n"] == cal_v2["n_scored"])

# una declinación honesta se APARTA del bloque paralelo, no del titular
r_dec = mk_run("marcelo", state="closed", conf=0.15)
with db.engine().begin() as _cx:
    import json as _j
    _rec = _j.loads(db.get_run(r_dec)["frozen_record_json"])
    _rec["audit"] = {"verdict": "APPROVE_DECLINE"}
    _cx.execute(db.runs.update().where(db.runs.c.run_id == r_dec)
                .values(frozen_record_json=_j.dumps(_rec)))
app.add_rating(r_dec, app.RatingBody(rating_input=4, rating_output=5), authorization=AUTH_NAT)
cal_d = app.calibration_report(authorization=AUTH_EMM)
check("M5 v2: la declinación honesta bien calificada SÍ entra al titular pero se aparta del bloque limpio",
      cal_d["ece_excluding_declines"]["n_excluded_declines"] >= 1
      and cal_d["ece_excluding_declines"]["n"] == cal_d["n_scored"]
                                                  - cal_d["ece_excluding_declines"]["n_excluded_declines"])

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
