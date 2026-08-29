"""
smoke_m5v2_http.py — verificación END-TO-END de M5 v2 (ADR-0075) sobre el stack HTTP REAL.

POR QUÉ EXISTE, aparte de smoke_ratings_calibration.py: ese gate llama `app.add_rating(...)` como
FUNCIÓN de Python, así que salta el parseo del cuerpo por Pydantic, el ruteo y la serialización a
JSON. Un campo nuevo puede persistir perfecto por la vía directa y no llegar nunca por HTTP (cuerpo
mal tipado, campo no declarado en el modelo, o serializado fuera). Este gate cierra ese hueco: usa
TestClient, que ejerce el stack ASGI completo — el mismo camino que recorre la webapp.

Es la lección permanente del RIL aplicada a este cambio: un pase de gate vacuo es peor que un fallo,
así que antes de reportar verde hay que verificar que el gate VIO el campo, no sólo que no explotó.

NO-SPEND: sin red, sin modelo, sin embeddings. BD sqlite temporal fuera del repo.
Uso:  python smoke_m5v2_http.py
"""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
_tmp = Path(tempfile.gettempdir()) / f"witt_m5v2_http_{uuid.uuid4().hex[:8]}.db"
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

import db  # noqa: E402
import app as app_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


db.init_db()
for uid, role in (("natalia", "medico"), ("marcelo", "medico"), ("emmanuel", "dev")):
    db.upsert_user(uid, uid.capitalize(), role, f"pw-{uid}")

client = TestClient(app_mod.app)


def login(uid):
    r = client.post("/login", json={"username": uid, "password": f"pw-{uid}"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


H_NAT, H_MAR, H_EMM = login("natalia"), login("marcelo"), login("emmanuel")


def mk_closed_run(author, conf=0.8, verdict="AUDIT_APPROVED"):
    """Una corrida CERRADA con registro congelado, sembrada directo (crear una de verdad gastaría)."""
    rid = uuid.uuid4().hex
    db.create_run(rid, author, "¿qué marca el pronefros?")
    rec = {"run_id": rid,
           "confidence": {"state": "value", "final": conf, "source": "stated-second-elicitation"},
           "audit": {"verdict": verdict}, "retrieval_summary": {"mode": "semantic"}}
    db.update_run(rid, state="closed", frozen_record_json=json.dumps(rec), frozen_at=db._now(),
                  epistemic_summary_json=json.dumps(
                      {"retrieval_mode": "semantic", "verdict": verdict,
                       "confidence_state": "value", "panel_n_valid": 4}))
    return rid


# ── 1. el campo nuevo cruza HTTP de ida ────────────────────────────────────────────────────────────
r1 = mk_closed_run("marcelo")
resp = client.post(f"/runs/{r1}/ratings", headers=H_NAT, json={
    "rating_output": 4, "rating_input": 3,
    "note": "le faltó el glomérulo",
    "note_question": "la pregunta no cabía en una sola corrida",
})
check("HTTP 200 al calificar con las DOS notas", resp.status_code == 200, resp.text[:120])
row = resp.json()["rating"]
check("la nota de la PREGUNTA sobrevive el viaje HTTP (Pydantic la parsea, no la tira)",
      row.get("note_question") == "la pregunta no cabía en una sola corrida", repr(row.get("note_question")))
check("la nota de la RESPUESTA sigue llegando aparte (no se pisan)",
      row.get("note") == "le faltó el glomérulo")
check("la procedencia se DERIVA en el servidor, no se acepta del cliente",
      row["rated_by"] == "natalia" and row["instrument"] == "m5-consenso" and row["is_author"] is False)

# el cliente NO puede falsificar procedencia aunque la mande
r_fake = mk_closed_run("marcelo")
resp_fake = client.post(f"/runs/{r_fake}/ratings", headers=H_NAT, json={
    "rating_output": 5, "rating_input": 5, "rated_by": "emmanuel", "instrument": "m5-cierre",
    "is_author": True, "blind": True,
})
check("procedencia falsificada por el cliente se IGNORA (ADR-0056)",
      resp_fake.status_code == 200
      and resp_fake.json()["rating"]["rated_by"] == "natalia"
      and resp_fake.json()["rating"]["instrument"] == "m5-consenso"
      and resp_fake.json()["rating"]["is_author"] is False)

# ── 2. el campo nuevo cruza HTTP de vuelta, y el enmascaramiento NO lo filtra ───────────────────────
vista_emm = client.get(f"/runs/{r1}/ratings", headers=H_EMM).json()
check("quien no ha calificado ve la fila ENMASCARADA por HTTP", vista_emm["ratings_masked"] is True)
check("el enmascaramiento NO filtra note_question (allowlist, verificado sobre el JSON serializado)",
      all("note_question" not in r and "note" not in r for r in vista_emm["ratings"]),
      json.dumps(vista_emm["ratings"], ensure_ascii=False)[:110])
vista_nat = client.get(f"/runs/{r1}/ratings", headers=H_NAT).json()
check("quien ya calificó SÍ ve las dos notas por HTTP",
      vista_nat["ratings_masked"] is False
      and vista_nat["ratings"][0]["note_question"] == "la pregunta no cabía en una sola corrida")

# el registro congelado las fusiona AL LEER, sin reescribir el blob
rec_http = client.get(f"/runs/{r1}/record", headers=H_NAT).json()
check("/record fusiona las dos notas EN LECTURA",
      any(x.get("note_question") for x in (rec_http.get("ratings") or [])))
with db.engine().begin() as cx:
    blob = cx.execute(db.select(db.runs.c.frozen_record_json)
                      .where(db.runs.c.run_id == r1)).scalar()
check("el blob congelado en BD sigue SIN ratings (dos zonas intactas)", "ratings" not in json.loads(blob))

# ── 3. topes y validación por HTTP ─────────────────────────────────────────────────────────────────
r_lim = mk_closed_run("marcelo")
check("note_question de 4001 chars -> 400 por HTTP",
      client.post(f"/runs/{r_lim}/ratings", headers=H_NAT,
                  json={"rating_output": 4, "rating_input": 4, "note_question": "x" * 4001}).status_code == 400)
check("eje sin valor NI estado -> 400 por HTTP (la ausencia silenciosa no existe)",
      client.post(f"/runs/{r_lim}/ratings", headers=H_NAT,
                  json={"rating_output": 4}).status_code == 400)
check("cliente viejo (sin note_question) sigue funcionando -> 200 y la nota queda ''",
      (lambda x: x.status_code == 200 and x.json()["rating"]["note_question"] == "")(
          client.post(f"/runs/{r_lim}/ratings", headers=H_NAT,
                      json={"rating_output": 4, "rating_input": 4})))

# ── 4. /calibration: los tres cortes paralelos, por HTTP ───────────────────────────────────────────
# una corrida sólo autocalificada + una declinación honesta, para que los cortes tengan qué contar
r_auto = mk_closed_run("natalia", conf=0.9)
client.post(f"/runs/{r_auto}/ratings", headers=H_NAT, json={"rating_output": 5, "rating_input": 5})
r_dec = mk_closed_run("marcelo", conf=0.15, verdict="APPROVE_DECLINE")
client.post(f"/runs/{r_dec}/ratings", headers=H_NAT, json={"rating_output": 5, "rating_input": 4})

cal = client.get("/calibration", headers=H_EMM)
check("GET /calibration -> 200", cal.status_code == 200)
cal = cal.json()
check("axis_roles viaja DECLARADO en la respuesta (rating_input jamás entró al ECE)",
      "NUNCA" in cal["outcome_mapping"]["axis_roles"] and "rating_input" in cal["outcome_mapping"]["axis_roles"])
check("author_caveat y honest_decline viajan declarados",
      "author_caveat" in cal["outcome_mapping"] and "honest_decline" in cal["outcome_mapping"])
check("by_authorship trae los dos bloques ECE paralelos",
      set(cal["by_authorship"]) >= {"m5-consenso", "m5-cierre", "note"})
check("raters detecta el AUTOEXAMEN (la corrida que sólo calificó su autora)",
      cal["raters"]["n_runs_author_only"] >= 1, f"author_only={cal['raters']['n_runs_author_only']}")
check("raters cuenta las corridas de UN solo calificador",
      cal["raters"]["n_runs_single_rater"] >= 1, f"single={cal['raters']['n_runs_single_rater']}")
check("ece_excluding_declines apartó la declinación honesta",
      cal["ece_excluding_declines"]["n_excluded_declines"] >= 1,
      f"apartadas={cal['ece_excluding_declines']['n_excluded_declines']}")
check("el TITULAR no se reescribió: n de `ece` == n_scored",
      cal["ece"]["n"] == cal["n_scored"], f"ece.n={cal['ece']['n']} n_scored={cal['n_scored']}")
check("el bloque limpio = titular menos las apartadas",
      cal["ece_excluding_declines"]["n"] == cal["n_scored"] - cal["ece_excluding_declines"]["n_excluded_declines"])
check("el PODER se sigue declarando primero y sin poder no hay juicio",
      cal["power"]["sufficient"] is False and cal["power"]["status"] in ("case capture", "infrastructure populated"))

# ── 5. /consulta-sistema: el denominador honesto del corpus ─────────────────────────────────────────
cs = client.get("/consulta-sistema", headers=H_EMM, params={"q": "corpus"})
check("GET /consulta-sistema -> 200", cs.status_code == 200, cs.text[:100])
corpus = ((cs.json().get("snapshot") or {}).get("secciones") or {}).get("corpus") or {}
check("el corpus declara cuántos registros catalogados tiene", isinstance(corpus.get("n_records"), int),
      f"n_records={corpus.get('n_records')}")
# con el índice OFFLINE (esta corrida es sin Neo4j) el denominador NO se inventa: se declara ausente.
check("y contra cuántos documentos indexados — o dice honestamente que no consta (índice OFFLINE)",
      "cobertura_del_reparto" in corpus and "n_docs_indexados" in corpus,
      str(corpus.get("cobertura_del_reparto"))[:70])
check("el caveat dice que por_nicho reparte lo CATALOGADO, no el acervo",
      "CATALOGADO" in (corpus.get("caveat") or ""))
check("y advierte que un cero puede ser fase del proyecto, no descuido",
      "PROJECT_SCOPE" in (corpus.get("caveat") or ""))
check("/consulta-sistema sigue siendo determinista (sin modelo)",
      cs.json().get("model_consulted") is False)

# ── 6. la cola de pendientes sigue viva por HTTP ────────────────────────────────────────────────────
pend = client.get("/ratings/pending", headers=H_MAR)
check("GET /ratings/pending -> 200 con la cola personal", pend.status_code == 200)
check("la cola trae el resumen epistémico congelado (no se califica a ciegas una degradada)",
      any(p.get("epistemic_summary") for p in pend.json()["pending"]))
check("calificar JAMÁS bloquea: la nota del endpoint lo sigue diciendo",
      "JAMÁS bloquea" in pend.json()["note"])

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
try:
    _tmp.unlink(missing_ok=True)
except Exception:
    pass
sys.exit(0 if npass == len(CHECKS) else 1)
