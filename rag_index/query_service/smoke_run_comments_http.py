"""
smoke_run_comments_http.py — gate de los COMENTARIOS de corrida (ADR-0077, 2026-09-06): la
conversación del equipo SOBRE la pregunta de una corrida, como anexo append-only y público.

Fija lo que la PUERTA hace cumplir: sesión obligatoria · corrida inexistente = 404 · vacío = 400 ·
tope declarado con su cifra · autor, nombre y hora los pone el servidor · orden de llegada · otro
usuario lo lee · `n_comments` viaja idéntico en lista y detalle (misma-vista) · comentar NO toca la
corrida · no existe puerta de borrado (405).

Vía HTTP con TestClient (lección ADR-0075). NO-SPEND: sin red, sin modelo. BD sqlite temporal.
Uso:  python smoke_run_comments_http.py
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

_tmp = Path(tempfile.gettempdir()) / f"witt_run_comments_{uuid.uuid4().hex[:8]}.db"
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
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
db.create_run("r1", "natalia", "¿q1?")
db.create_run("r2", "natalia", "¿q2?")

client = TestClient(app_mod.app)


def sesion(u, pw):
    r = client.post("/login", json={"username": u, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


NAT = sesion("natalia", "pw-natalia")
EMM = sesion("emmanuel", "pw-emmanuel")

check("GET sin token -> 401", client.get("/runs/r1/comments").status_code == 401)
check("POST sin token -> 401", client.post("/runs/r1/comments", json={"body": "x"}).status_code == 401)
check("corrida inexistente -> 404", client.get("/runs/nope/comments", headers=NAT).status_code == 404)

r = client.get("/runs/r1/comments", headers=NAT)
check("sin comentarios: n=0, lista vacía y body_max DECLARADO",
      r.status_code == 200 and r.json()["n"] == 0 and r.json()["comments"] == []
      and r.json()["body_max"] == 4000, r.text[:120])

r = client.post("/runs/r1/comments", json={"body": "   \n  "}, headers=NAT)
check("vacío (solo espacios) -> 400", r.status_code == 400)
r = client.post("/runs/r1/comments", json={"body": "x" * 4001}, headers=NAT)
check("más del tope -> 400 con la cifra", r.status_code == 400 and "4000" in r.text, r.text[:100])

antes = client.get("/runs/r1", headers=NAT).json()
r = client.post("/runs/r1/comments", json={"body": "  ¿y si la pregunta abarca dos genes?\nSegunda línea.  "},
                headers=NAT)
c1 = r.json()
check("POST -> 201 con autor, NOMBRE y hora del servidor",
      r.status_code == 201 and c1["author_id"] == "natalia" and c1["author_name"] == "Natalia"
      and c1["run_id"] == "r1" and isinstance(c1["created_at"], str) and "T" in c1["created_at"], r.text[:160])
check("el cuerpo se guarda VERBATIM por dentro (saltos de línea) y recortado en los extremos",
      c1["body"] == "¿y si la pregunta abarca dos genes?\nSegunda línea.")

r = client.post("/runs/r1/comments", json={"body": "yo la partiría en dos corridas"}, headers=EMM)
check("otro usuario COMENTA la misma corrida (público, permisos planos)", r.status_code == 201
      and r.json()["author_id"] == "emmanuel")

hilo = client.get("/runs/r1/comments", headers=EMM).json()
check("el hilo va en ORDEN DE LLEGADA y otro usuario lo lee entero",
      hilo["n"] == 2 and [c["author_id"] for c in hilo["comments"]] == ["natalia", "emmanuel"])

lista = {row["run_id"]: row for row in client.get("/runs", headers=NAT).json()["runs"]}
det = client.get("/runs/r1", headers=NAT).json()
check("n_comments viaja en la LISTA (2 para r1, 0 para r2) y en el DETALLE idéntico (misma-vista)",
      lista["r1"]["n_comments"] == 2 and lista["r2"]["n_comments"] == 0 and det["n_comments"] == 2,
      f"lista={lista['r1'].get('n_comments')},{lista['r2'].get('n_comments')} detalle={det.get('n_comments')}")

despues = client.get("/runs/r1", headers=NAT).json()
mismos = {k: v for k, v in despues.items() if k not in ("n_comments", "heartbeat_age_s")}
antes_ = {k: v for k, v in antes.items() if k not in ("n_comments", "heartbeat_age_s")}
check("comentar NO toca la corrida (estado, tiempos, registro: idénticos)", mismos == antes_)

r = client.delete(f"/runs/r1/comments/{c1['comment_id']}", headers=NAT)
check("no existe puerta por comentario: DELETE /runs/{id}/comments/{cid} -> 404 (la ruta no existe)",
      r.status_code == 404, f"status={r.status_code}")
r = client.delete("/runs/r1/comments", headers=NAT)
check("la colección existe pero NO se borra: DELETE -> 405 (append-only: lo dicho queda dicho)",
      r.status_code == 405, f"status={r.status_code}")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
