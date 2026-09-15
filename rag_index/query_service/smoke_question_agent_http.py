"""
smoke_question_agent_http.py — gate del AGENTE apunte -> pregunta (2026-09-04, pedido del
fundador) y del LAZO DE CALIBRACIÓN que lo depura.

Fija:
  · la spec viaja VERSIONADA y verbatim (la UI muestra la MISMA regla que el agente obedeció)
  · redactar es del AUTOR (un apunte compartido se lee; poner a gastar sobre teoría ajena, no)
  · §6 NO-HANG: el modelo caído devuelve 200 con borrador `errored` y la causa verbatim — un
    500 perdería el registro del intento, y el intento fallido también es dato de calibración
  · `fits_one_run` ausente se guarda como None y NO se degrada a False (sería inventar una
    afirmación que el agente no hizo)
  · la historia de borradores NO se borra al pedir otro
  · el SELLO borrador->corrida es de UNA sola corrida (409 al reusarlo), como el plan
  · el tablero de calibración enfrenta lo AFIRMADO (fits_one_run) con lo MEDIDO (rating_input =
    EJE PREGUNTA, TAMAÑO) y reporta CONTEOS por versión de spec, jamás promedios

NO-SPEND: el redactor va INYECTADO (question_agent._default_drafter monkeypatched) y el
TestClient se usa SIN context manager, así que el lifespan no arranca los workers. Sin red,
sin modelo. BD sqlite temporal fuera del repo.
Uso:  python smoke_question_agent_http.py
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

_tmp = Path(tempfile.gettempdir()) / f"witt_qagent_{uuid.uuid4().hex[:8]}.db"
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"   # el loop sparse-dev: encolar sin índice denso

import db  # noqa: E402
import question_agent  # noqa: E402
import runs as runs_mod  # noqa: E402
import app as app_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


# --- el redactor FALSO: cero gasto, salida controlada -----------------------------------------------
MODO = {"como": "ok"}


def drafter_falso(note):
    if MODO["como"] == "explota":
        raise RuntimeError("el proveedor se cayó")
    if MODO["como"] == "sin_pregunta":
        return {"question": "   ", "entities": []}, {"input_tokens": 10, "output_tokens": 1}
    if MODO["como"] == "sin_juicio":
        return ({"question": "¿aldh1a2 es requerido para el pronefros en pez cebra?",
                 "entities": ["aldh1a2"], "fits_rationale": "una sola afirmación"},
                {"input_tokens": 100, "output_tokens": 40})
    return ({"question": "¿aldh1a2 es requerido para la formación del pronefros en pez cebra?",
             "entities": ["aldh1a2"], "scope": "pez cebra · pronefros",
             "fits_one_run": True, "fits_rationale": "una afirmación, una respuesta",
             "sibling_questions": ["¿el gradiente de RA ordena el eje proximo-distal?"],
             "assumptions": ["el apunte no dijo etapa; se asume desarrollo temprano"],
             "unsupported": ["la comparación con ratón que menciona el apunte"]},
            {"input_tokens": 420, "output_tokens": 180, "estimated_cost_usd": 0.012})


# --- el redactor REAL debe poder ARMARSE (sin llamarlo: eso gastaría) -------------------------------
# Esto atrapa el defecto que el redactor inyectado esconde: si la dependencia del drafter real no
# resuelve, el §6 no-hang lo convierte en un borrador `errored` perfectamente plausible — un agente
# muerto en silencio que pasa todos los demás checks. Pasó de verdad el 2026-09-04
# (`import composite_auditor` en vez de `from lib import composite_auditor`).
try:
    from lib import composite_auditor as _ca   # la MISMA ruta que usa _default_drafter
    _dep_ok = hasattr(_ca, "_anthropic_tool_call")
    _dep_err = ""
except Exception as e:                          # noqa: BLE001
    _dep_ok, _dep_err = False, f"{type(e).__name__}: {e}"
check("la dependencia del redactor REAL resuelve en el contexto de la app (agente vivo, no "
      "'errored' silencioso)", _dep_ok, _dep_err)

question_agent._default_drafter = drafter_falso

db.init_db()
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")

client = TestClient(app_mod.app)


def sesion(u, p):
    r = client.post("/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


EMM = sesion("emmanuel", "pw-emmanuel")
NAT = sesion("natalia", "pw-natalia")

apunte = client.post("/notes", headers=EMM, json={
    "title": "Retinoico y patterning proximo-distal",
    "body": "Si el RA sistémico ordena la nefrona, el gradiente debería verse en el ducto.",
    "entities": ["aldh1a2"], "niches": ["N3"]}).json()
NID = apunte["note_id"]

# --- la spec: versionada, verbatim, legible ---------------------------------------------------------
r = client.get("/notes/questions/spec", headers=EMM)
check("GET /notes/questions/spec -> 200 (la ruta no la sombrea /notes/{id})", r.status_code == 200,
      f"status={r.status_code}")
spec = r.json()["spec"]
check("la spec viaja VERSIONADA", spec.get("version") == question_agent.QUESTION_SPEC_VERSION)
check("las 5 reglas viajan con su POR QUÉ (una regla sin razón no se puede depurar)",
      len(spec["reglas"]) == 5 and all(x.get("por_que") for x in spec["reglas"]),
      f"n_reglas={len(spec['reglas'])}")
check("R1 es el TAMAÑO — el mismo constructo del eje pregunta de M5 (ADR-0075)",
      "una corrida" in spec["reglas"][0]["nombre"].lower()
      and "kappa" in spec["reglas"][0]["por_que"].lower())

# --- redactar es del AUTOR --------------------------------------------------------------------------
client.patch(f"/notes/{NID}", headers=EMM, json={"visibility": "shared"})
check("apunte compartido: el otro lo LEE pero no puede poner a gastar sobre él -> 403",
      client.post(f"/notes/{NID}/question", headers=NAT).status_code == 403)
vacio = client.post("/notes", headers=EMM, json={"title": "x"}).json()
client.patch(f"/notes/{vacio['note_id']}", headers=EMM, json={"title": ""})
check("apunte vacío no da pregunta -> 400",
      client.post(f"/notes/{vacio['note_id']}/question", headers=EMM).status_code == 400)

# --- el camino feliz --------------------------------------------------------------------------------
MODO["como"] = "ok"
r = client.post(f"/notes/{NID}/question", headers=EMM)
check("POST /notes/{id}/question -> 200", r.status_code == 200, f"body={r.text[:200]}")
q1 = r.json()
check("el borrador guarda la VERSIÓN DE SPEC que lo produjo (depurar no reescribe historia)",
      q1["spec_version"] == question_agent.QUESTION_SPEC_VERSION)
check("state=drafted y la pregunta viaja", q1["state"] == "drafted" and q1["question"].startswith("¿"))
check("la ESTRUCTURA completa se guarda: hermanas, supuestos y lo no convertido",
      q1["draft"]["sibling_questions"] and q1["draft"]["assumptions"] and q1["draft"]["unsupported"],
      f"draft_keys={sorted(q1['draft'])}")
check("lo que el agente AGREGÓ va declarado en assumptions (no se cuela como si fuera del apunte)",
      "no dijo etapa" in q1["draft"]["assumptions"][0])
check("lo del apunte que NO cupo va declarado en unsupported (jamás se descarta callado)",
      "ratón" in q1["draft"]["unsupported"][0])
check("el GASTO se guarda con el borrador (una acción que gasta lo declara)",
      (q1.get("usage") or {}).get("estimated_cost_usd") == 0.012, f"usage={q1.get('usage')}")
check("la spec viaja DENTRO del borrador: se puede leer la regla que obedeció, años después",
      q1["draft"]["spec"]["version"] == question_agent.QUESTION_SPEC_VERSION)

# --- §6 no-hang: el agente falla sin tumbar nada ----------------------------------------------------
MODO["como"] = "explota"
r = client.post(f"/notes/{NID}/question", headers=EMM)
check("modelo caído -> 200 con borrador ERRORED (no 500: el intento fallido también es dato)",
      r.status_code == 200 and r.json()["state"] == "errored", f"status={r.status_code}")
check("la causa viaja VERBATIM", "el proveedor se cayó" in (r.json().get("error") or ""))

MODO["como"] = "sin_pregunta"
r = client.post(f"/notes/{NID}/question", headers=EMM)
check("el modelo responde SIN pregunta -> errored (no un borrador vacío disfrazado de bueno)",
      r.json()["state"] == "errored" and "no devolvió pregunta" in r.json()["error"])

# --- el juicio ausente NO se degrada a False --------------------------------------------------------
MODO["como"] = "sin_juicio"
q_sin = client.post(f"/notes/{NID}/question", headers=EMM).json()
check("fits_one_run ausente se guarda None, JAMÁS False (sería inventar una afirmación)",
      q_sin["draft"]["fits_one_run"] is None, f"fits={q_sin['draft']['fits_one_run']}")

# --- la historia no se borra ------------------------------------------------------------------------
hist = client.get(f"/notes/{NID}/questions", headers=EMM).json()
check("la historia de intentos se CONSERVA (4 borradores: ok, explota, sin_pregunta, sin_juicio)",
      hist["n"] == 4, f"n={hist['n']}")
check("el más nuevo primero", hist["questions"][0]["question_id"] == q_sin["question_id"])

# --- el sello borrador -> corrida -------------------------------------------------------------------
r = client.post("/runs", headers=EMM, json={"question": q1["question"], "entities": ["aldh1a2"],
                                            "from_question_id": q1["question_id"]})
check("POST /runs con from_question_id -> 200 y encola", r.status_code == 200, f"body={r.text[:200]}")
RUN1 = r.json()["run_id"]
check("el borrador queda SELLADO con su corrida (el lazo de calibración se cierra ahí)",
      db.get_note_question(q1["question_id"])["run_id"] == RUN1)
r = client.post("/runs", headers=EMM, json={"question": "otra", "from_question_id": q1["question_id"]})
check("reusar el borrador -> 409 (dos corridas del mismo borrador contarían dos veces)",
      r.status_code == 409 and r.json()["detail"]["state"] == "question_already_used",
      f"status={r.status_code}")
check("from_question_id inexistente -> 404",
      client.post("/runs", headers=EMM,
                  json={"question": "q", "from_question_id": "no-existe"}).status_code == 404)

# --- el tablero de calibración ----------------------------------------------------------------------
# corrector ADR-0079: la corrida que respalda a q1 nació con el origen que deriva el servidor ('smoke' bajo la
# máscara, 'dev-offline' sin ella — ∉ production). Por DEFAULT el tablero la EXCLUYE y la CUENTA; para leer el
# tablero completo el gate pide include_origins=<ese origen> explícito (mismo régimen que precedente/calibración).
_ORIGEN = runs_mod.run_origin()["value"]
assert _ORIGEN in db.RUN_ORIGINS and _ORIGEN != "production", _ORIGEN
cal0 = client.get("/notes/questions/calibration", headers=EMM).json()
v0 = next(v for v in cal0["por_version"] if v["spec_version"] == question_agent.QUESTION_SPEC_VERSION)
check("corrector ADR-0079: SIN parámetro el tablero declara origins_included ['production'] y el borrador respaldado por la "
      f"corrida '{_ORIGEN}' queda FUERA y CONTADO: excluded_by_origin {{{_ORIGEN}: 1}}, n_borradores_excluidos_por_origen 1, "
      "n_borradores 3, n_usados 0 (antes: origins_included null = sin filtro, la corrida smoke contaba)",
      cal0["origins_included"] == ["production"] and cal0["excluded_by_origin"] == {_ORIGEN: 1}
      and cal0["n_borradores_excluidos_por_origen"] == 1 and cal0["origin_unknown_included"] == 0
      and v0["n_borradores"] == 3 and v0["n_usados"] == 0,
      f"origins={cal0['origins_included']} excl={cal0['excluded_by_origin']} n={v0['n_borradores']} usados={v0['n_usados']}")
cal = client.get(f"/notes/questions/calibration?include_origins={_ORIGEN}", headers=EMM).json()
v1 = next(v for v in cal["por_version"] if v["spec_version"] == question_agent.QUESTION_SPEC_VERSION)
check("con include_origins=<origen del gate> el tablero declara ese alcance y no excluye nada",
      cal["origins_included"] == [_ORIGEN] and cal["excluded_by_origin"] == {}
      and cal["n_borradores_excluidos_por_origen"] == 0)
check("la calibración agrupa POR VERSIÓN DE SPEC", v1["n_borradores"] == 4, f"n={v1['n_borradores']}")
check("los borradores fallidos se cuentan aparte", v1["n_errored"] == 2, f"errored={v1['n_errored']}")
# los 4 pendientes: 3 sin corrida + el ya SELLADO pero todavía sin calificar. Un borrador con
# corrida pero sin nota humana NO es acierto ni fallo: sin medición no hay veredicto.
check("sin medición humana no hay veredicto: ni acierto ni fallo, ni siquiera con la corrida sellada",
      v1["cabe_vs_medido"] == {"acerto": 0, "fallo": 0, "pendiente": 4} and v1["n_usados"] == 1,
      f"cabe_vs_medido={v1['cabe_vs_medido']} n_usados={v1['n_usados']}")
check("el corte va DECLARADO en la salida (no es una verdad, es el corte que usamos)",
      "nota >= 4" in cal["corte_declarado"])
check("las anclas del eje pregunta viajan con el tablero (la escala se lee, no se recuerda)",
      cal["anclas"]["3"].startswith("hubiera salido mejor partida"))

# la corrida se califica en el EJE PREGUNTA: aquí se cierra el lazo
with db.engine().begin() as cx:
    from sqlalchemy import text
    cx.execute(text("UPDATE runs SET state='closed' WHERE run_id=:r"), {"r": RUN1})
run = db.get_run(RUN1)
db.add_rating(run, {"user_id": "emmanuel", "role": "dev"}, 3, "value", 4, "value",
              note="", note_question="se pasó de ambiciosa")
cal = client.get(f"/notes/questions/calibration?include_origins={_ORIGEN}", headers=EMM).json()
v1 = next(v for v in cal["por_version"] if v["spec_version"] == question_agent.QUESTION_SPEC_VERSION)
check("la calificación del EJE PREGUNTA entra al tablero como CONTEO por ancla",
      v1["tamano"]["3"] == 1 and v1["n_calificados"] == 1, f"tamano={v1['tamano']}")
check("el agente dijo CABE y el humano midió 3 ('mejor partida en dos') -> FALLO contado",
      v1["cabe_vs_medido"]["fallo"] == 1 and v1["cabe_vs_medido"]["acerto"] == 0,
      f"cabe_vs_medido={v1['cabe_vs_medido']}")
check("no se publica ningún PROMEDIO de la ordinal", "promedios" in cal["note"])

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
