"""
smoke_notes_http.py — gate de los APUNTES (2026-09-04, pedido del fundador): el cuaderno de
teorías que puede citar corridas, genes y nichos, y que existe ANTES de que haya corrida.

Fija lo que la PUERTA hace cumplir (no el cliente): escribir es sólo del autor · la
visibilidad es POR APUNTE con default privado · el privado ajeno responde 404 y no 403 (un
403 confirmaría que existe) · PATCH real (lo omitido no se toca, lo mandado vacío sí vacía) ·
los enlaces se guardan VERBATIM (un gen que la DI no conoce se guarda igual: es información,
no error) · el hipervínculo AL REVÉS (/runs/{id}/notes) respeta la misma visibilidad.

Vía HTTP con TestClient (lección ADR-0075: el gate ve los campos sobre el stack completo, el
mismo camino de la webapp).

NO-SPEND: sin red, sin modelo. BD sqlite temporal fuera del repo.
Uso:  python smoke_notes_http.py
"""
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
_tmp = Path(tempfile.gettempdir()) / f"witt_notes_{uuid.uuid4().hex[:8]}.db"
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
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.create_run("r-pronefros", "emmanuel", "¿aldh1a2 es requerido para el pronefros?",
              entities=["aldh1a2"])

client = TestClient(app_mod.app)


def sesion(usuario, pw):
    r = client.post("/login", json={"username": usuario, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


EMM = sesion("emmanuel", "pw-emmanuel")
NAT = sesion("natalia", "pw-natalia")

# --- la puerta existe y está cerrada sin sesión -----------------------------------------------------
check("HTTP sin token -> 401", client.get("/notes").status_code == 401)

# --- crear: el apunte NO exige corrida (existe antes que ella) --------------------------------------
r = client.post("/notes", headers=EMM, json={
    "title": "Retinoico y patterning proximo-distal",
    "body": "Si el RA sistémico ordena la nefrona, el gradiente debería verse en el ducto.",
    "entities": ["aldh1a2", "osr1"], "niches": ["N3"], "run_ids": ["r-pronefros"]})
check("POST /notes -> 200 (un apunte se crea SIN corrida obligatoria)", r.status_code == 200,
      f"status={r.status_code} body={r.text[:200]}")
n1 = r.json()
check("el apunte nace PRIVADO (default: quien escribe decide qué comparte)",
      n1.get("visibility") == "private", f"visibility={n1.get('visibility')}")
check("la procedencia la deriva el servidor (author_id de la sesión, no del cliente)",
      n1.get("author_id") == "emmanuel")
check("los enlaces viajan como LISTAS, no como CSV (el cliente no parsea CSV)",
      n1.get("entities") == ["aldh1a2", "osr1"] and n1.get("niches") == ["N3"]
      and n1.get("run_ids") == ["r-pronefros"], f"entities={n1.get('entities')}")

# un apunte SIN ningún enlace es legítimo: la teoría llega antes que la pregunta
r = client.post("/notes", headers=EMM, json={"title": "Idea suelta", "body": "sin enlaces todavía"})
check("apunte SIN enlaces -> 200 (la idea llega antes que la pregunta)", r.status_code == 200)
n_suelto = r.json()
check("sin enlaces las listas van VACÍAS, no nulas ni inventadas",
      n_suelto.get("entities") == [] and n_suelto.get("run_ids") == [])

# --- los enlaces se guardan VERBATIM ----------------------------------------------------------------
r = client.post("/notes", headers=EMM, json={
    "title": "Gen que la DI no conoce", "body": "hipótesis sobre un símbolo aún no ingerido",
    "entities": ["gen-inexistente-xyz"]})
check("un gen que la DI NO conoce se guarda igual (es información, no error)",
      r.status_code == 200 and r.json()["entities"] == ["gen-inexistente-xyz"])

# --- vacío: lo único que no se guarda ---------------------------------------------------------------
check("apunte vacío (sin título ni cuerpo) -> 400",
      client.post("/notes", headers=EMM, json={"title": "  ", "body": ""}).status_code == 400)

# --- topes declarados en el 400 ---------------------------------------------------------------------
r = client.post("/notes", headers=EMM, json={"title": "x", "body": "b" * (app_mod.NOTE_BODY_MAX + 1)})
check("cuerpo sobre el tope -> 400 CON la cifra del límite (un límite sin su cifra no se obedece)",
      r.status_code == 400 and str(app_mod.NOTE_BODY_MAX) in r.text, f"detail={r.text[:160]}")
check("visibilidad fuera del vocabulario -> 400",
      client.post("/notes", headers=EMM,
                  json={"title": "x", "visibility": "publica"}).status_code == 400)

# --- visibilidad: el privado ajeno NO EXISTE para el otro lector ------------------------------------
lista_nat = client.get("/notes", headers=NAT).json()
check("el privado ajeno no sale en la lista ajena (ni en el conteo)",
      lista_nat["n"] == 0 and lista_nat["notes"] == [], f"n={lista_nat['n']}")
check("el privado ajeno responde 404, NO 403 (un 403 confirmaría que existe)",
      client.get(f"/notes/{n1['note_id']}", headers=NAT).status_code == 404)

# --- compartir es del autor, apunte por apunte ------------------------------------------------------
r = client.patch(f"/notes/{n1['note_id']}", headers=EMM, json={"visibility": "shared"})
check("PATCH visibility -> shared (decisión POR APUNTE, no política global)",
      r.status_code == 200 and r.json()["visibility"] == "shared")
check("ya compartido, el otro lector SÍ lo ve",
      client.get(f"/notes/{n1['note_id']}", headers=NAT).status_code == 200)
check("compartido se LEE pero no se edita: PATCH ajeno -> 403",
      client.patch(f"/notes/{n1['note_id']}", headers=NAT,
                   json={"body": "me meto"}).status_code == 403)
check("compartido tampoco se borra: DELETE ajeno -> 403",
      client.delete(f"/notes/{n1['note_id']}", headers=NAT).status_code == 403)

# --- PATCH real: lo omitido no se toca, lo vacío SÍ vacía -------------------------------------------
antes = client.get(f"/notes/{n1['note_id']}", headers=EMM).json()
r = client.patch(f"/notes/{n1['note_id']}", headers=EMM, json={"title": "Título nuevo"})
despues = r.json()
check("PATCH parcial: lo OMITIDO queda intacto (el cuerpo y los enlaces sobreviven)",
      despues["body"] == antes["body"] and despues["entities"] == antes["entities"],
      f"body_igual={despues['body'] == antes['body']}")
check("PATCH toca updated_at pero conserva created_at (la traza no se reescribe)",
      despues["created_at"] == antes["created_at"] and despues["updated_at"] >= antes["updated_at"])
r = client.patch(f"/notes/{n1['note_id']}", headers=EMM, json={"entities": []})
check("mandar la lista VACÍA sí la vacía (omitir ≠ vaciar: la puerta los distingue)",
      r.json()["entities"] == [] and r.json()["niches"] == ["N3"])

# --- el hipervínculo AL REVÉS -----------------------------------------------------------------------
r = client.get("/runs/r-pronefros/notes", headers=EMM)
check("GET /runs/{id}/notes: la corrida sabe qué apuntes la citan", r.status_code == 200
      and [n["note_id"] for n in r.json()["notes"]] == [n1["note_id"]], f"body={r.text[:200]}")
r = client.post("/notes", headers=NAT, json={"title": "de natalia, privado",
                                             "body": "x", "run_ids": ["r-pronefros"]})
assert r.status_code == 200, r.text
check("el reverso respeta la MISMA visibilidad (el privado de natalia no aparece para emmanuel)",
      [n["note_id"] for n in client.get("/runs/r-pronefros/notes", headers=EMM).json()["notes"]]
      == [n1["note_id"]])
check("y natalia sí ve el suyo propio en el reverso",
      len(client.get("/runs/r-pronefros/notes", headers=NAT).json()["notes"]) == 2)

# --- orden y borrado --------------------------------------------------------------------------------
propios = client.get("/notes", headers=EMM).json()
# 3 = los que SÍ se guardaron (teoría · idea suelta · gen que la DI no conoce). Los tres POST
# rechazados con 400 (vacío, sobre el tope, visibilidad inválida) no dejaron fila: un 400 que
# de todas formas escribe sería peor que no validar.
check("la lista propia trae exactamente los apuntes que la puerta ACEPTÓ (3), no los rechazados",
      propios["n"] == 3, f"n={propios['n']}")
check("ordenados por updated_at descendente (lo último que tocaste, arriba)",
      propios["notes"][0]["note_id"] == n1["note_id"],
      f"primero={propios['notes'][0]['title']!r}")
check("DELETE propio -> borrado",
      client.delete(f"/notes/{n_suelto['note_id']}", headers=EMM).json()["deleted"] is True)
check("borrado de verdad: el GET siguiente es 404",
      client.get(f"/notes/{n_suelto['note_id']}", headers=EMM).status_code == 404)
check("404 en apunte inexistente", client.get("/notes/no-existe", headers=EMM).status_code == 404)

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
