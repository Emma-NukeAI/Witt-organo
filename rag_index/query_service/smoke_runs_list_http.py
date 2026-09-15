"""
smoke_runs_list_http.py — gate de la lista enriquecida de /runs (2026-08-29): los códigos
de nicho del plan (`plan_niches`, derivados del plan_json guardado) y el veredicto del
panel (`epistemic_summary.verdict`, congelado al freeze — LOTE-02·3) viajan POR RENGLÓN.

Vía HTTP con TestClient (lección ADR-0075: el gate VE los campos sobre el stack completo,
el mismo camino de la webapp). Fija además las ausencias declaradas (corrida sin plan ⇒
plan_niches null · corrida sin registro congelado ⇒ epistemic_summary null), que la lista
y el detalle sirven la MISMA vista (LOTE-01·A1), y que los blobs (plan_json /
frozen_record_json) JAMÁS se filtran al renglón.

2026-09-05 (ADR-0076): el NÚMERO de corrida — nace con la corrida, es único, crece con la
creación, viaja idéntico en lista y detalle, y el backfill numera por orden de creación a las
que nacieron antes de la columna.

2026-09-15 (ADR-0081 (F)): `root_run_no` NACE en la BD (JOIN a la raíz del hilo en db._list_select /
db.get_run) y fluye por _run_view como passthrough: POST /runs == lista == detalle; la raíz vale su
run_no, el hijo el run_no de la raíz, y una corrida pre-ADR-0079 (thread_id NULL) trae la llave con
null DECLARADO — jamás rellenado. Los blobs siguen fuera del renglón.

NO-SPEND: sin red, sin modelo. BD sqlite temporal fuera del repo.
Uso:  python smoke_runs_list_http.py
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
_tmp = Path(tempfile.gettempdir()) / f"witt_runs_list_{uuid.uuid4().hex[:8]}.db"
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"          # ADR-0079 (F): procedencia de las corridas encoladas aquí
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"      # dev sparse siempre está OFFLINE (LOTE-01·A5 override)

import db  # noqa: E402
import app as app_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")

# r1: CON plan (nichos N3+N1 en el juicio) y CON resumen epistémico congelado (verdict)
PLAN = {"plan_version": "3",
        "judgment": {"state": "declared",
                     "niches": [{"code": "N3", "name": "Embriología"}, {"code": "N1", "name": "X"}]}}
db.create_plan("p1", "natalia", "¿q1?", ["osr1"], json.dumps(PLAN, ensure_ascii=False))
db.create_run("r1", "natalia", "¿q1?", entities=["osr1"], plan_json=json.dumps(PLAN, ensure_ascii=False))
with db.engine().begin() as cx:
    cx.execute(text("UPDATE runs SET epistemic_summary_json = :s WHERE run_id = 'r1'"),
               {"s": json.dumps({"retrieval_mode": "graph", "verdict": "APPROVE",
                                 "confidence_state": "value", "panel_n_valid": 4})})

# r2: SIN plan y SIN registro congelado — las ausencias se declaran, no se rellenan
db.create_run("r2", "natalia", "¿q2?")

client = TestClient(app_mod.app)
r = client.post("/login", json={"username": "natalia", "password": "pw-natalia"})
assert r.status_code == 200, r.text
AUTH = {"Authorization": "Bearer " + r.json()["token"]}

check("HTTP sin token -> 401", client.get("/runs").status_code == 401)

resp = client.get("/runs", headers=AUTH)
check("GET /runs -> 200", resp.status_code == 200, f"status={resp.status_code}")
filas = {row["run_id"]: row for row in resp.json()["runs"]}

f1 = filas.get("r1") or {}
check("plan_niches viaja por renglón con los CÓDIGOS del juicio", f1.get("plan_niches") == ["N3", "N1"],
      f"plan_niches={f1.get('plan_niches')}")
check("entities_csv viaja en la LISTA (misma-vista restaurada — la lista lo omitía)",
      f1.get("entities_csv") == "osr1", f"entities_csv={f1.get('entities_csv')!r}")
check("plan_declared sigue siendo el bool (el plan completo va al registro)",
      f1.get("plan_declared") is True)
check("el veredicto del panel viaja en epistemic_summary (congelado al freeze)",
      (f1.get("epistemic_summary") or {}).get("verdict") == "APPROVE")

f2 = filas.get("r2") or {}
check("corrida SIN plan: plan_niches null (ausencia declarada, no lista vacía inventada)",
      f2.get("plan_niches") is None and f2.get("plan_declared") is False)
check("corrida SIN registro congelado: epistemic_summary null",
      f2.get("epistemic_summary") is None)

check("los blobs jamás se filtran al renglón (plan_json / frozen_record_json / usage_json fuera)",
      all(k not in f1 for k in ("plan_json", "frozen_record_json", "usage_json", "bundle_json")))

det = client.get("/runs/r1", headers=AUTH).json()
check("la lista y el detalle sirven la MISMA vista (LOTE-01·A1): plan_niches idéntico",
      det.get("plan_niches") == f1.get("plan_niches")
      and (det.get("epistemic_summary") or {}).get("verdict") == "APPROVE")

# ---- ADR-0076: el número de corrida --------------------------------------------------------------------
check("ADR-0076: cada renglón trae run_no entero",
      isinstance(f1.get("run_no"), int) and isinstance(f2.get("run_no"), int),
      f"r1={f1.get('run_no')!r} r2={f2.get('run_no')!r}")
check("ADR-0076: r1 nació antes que r2 ⇒ su número es menor (1 y 2 en BD nueva)",
      f1.get("run_no") == 1 and f2.get("run_no") == 2)
check("ADR-0076: la lista y el detalle sirven el MISMO número", det.get("run_no") == f1.get("run_no"))
check("ADR-0076: la corrida NUEVA recibe el siguiente número",
      db.create_run("r3", "natalia", "¿q3?") == 3 and db.get_run("r3")["run_no"] == 3)

# backfill: corridas que nacieron ANTES de la columna (run_no NULL) se numeran por creación
with db.engine().begin() as cx:
    cx.execute(text("UPDATE runs SET run_no = NULL WHERE run_id IN ('r1', 'r2')"))
db._migrate()
with db.engine().begin() as cx:
    numeros = dict(cx.execute(text("SELECT run_id, run_no FROM runs")).all())
check("ADR-0076: el backfill numera por ORDEN DE CREACIÓN después del máximo vigente (r3=3 ⇒ r1=4, r2=5)",
      numeros == {"r1": 4, "r2": 5, "r3": 3}, f"numeros={numeros}")

# el índice único es el árbitro: un número repetido NO entra
dup = False
try:
    with db.engine().begin() as cx:
        cx.execute(text("UPDATE runs SET run_no = 3 WHERE run_id = 'r1'"))
except Exception:
    dup = True
check("ADR-0076: el índice único rechaza un número repetido", dup)
db._migrate()
with db.engine().begin() as cx:
    numeros2 = dict(cx.execute(text("SELECT run_id, run_no FROM runs")).all())
check("ADR-0076: _migrate es idempotente (una segunda pasada no renumera)",
      numeros2 == {"r1": 4, "r2": 5, "r3": 3}, f"numeros={numeros2}")

# ---- ADR-0081 (F): root_run_no en la vista — lista == detalle == POST /runs; pre-ADR null declarado -----------
f1b = client.get("/runs/r1", headers=AUTH).json()
lst1 = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
check("ADR-0081 (F): corrida pre-ADR (db.create_run directo, thread_id NULL): la llave root_run_no está PRESENTE con null "
      "DECLARADO en lista y detalle (jamás rellenada con su run_no)",
      "root_run_no" in f1b and f1b["root_run_no"] is None and "root_run_no" in lst1.get("r1", {})
      and lst1["r1"]["root_run_no"] is None, f"det={f1b.get('root_run_no', 'AUSENTE')!r} lista={lst1.get('r1', {}).get('root_run_no', 'AUSENTE')!r}")
rz = client.post("/runs", json={"question": "¿raíz ADR-0081?", "entities": ["osr1"]}, headers=AUTH)
check("ADR-0081 (F): POST /runs raíz -> 200 y root_run_no == run_no (la raíz apunta a sí misma por el JOIN)",
      rz.status_code == 200 and rz.json().get("root_run_no") == rz.json().get("run_no") is not None, rz.text[:160])
RZ = rz.json()
db.update_run(RZ["run_id"], state="closed")     # el padre debe ser terminal para apilar un turno (ADR-0079)
hj = client.post("/runs", json={"question": "¿turno 2 sobre la raíz?", "entities": ["osr1"],
                                 "parent_run_id": RZ["run_id"]}, headers=AUTH)
HJ = hj.json()
det_hj = client.get(f"/runs/{HJ.get('run_id', 'x')}", headers=AUTH).json()
lst2 = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
check("ADR-0081 (F): hijo (turn_no 2): root_run_no == run_no de la raíz en POST /runs, en el detalle y en la lista — "
      "misma-vista (LOTE-01·A1) por construcción (misma consulta)",
      hj.status_code == 200 and HJ.get("turn_no") == 2 and HJ.get("root_run_no") == RZ["run_no"]
      and det_hj.get("root_run_no") == RZ["run_no"] and lst2.get(HJ.get("run_id"), {}).get("root_run_no") == RZ["run_no"]
      and lst2.get(RZ["run_id"], {}).get("root_run_no") == RZ["run_no"],
      f"post={HJ.get('root_run_no')} det={det_hj.get('root_run_no')} lista={lst2.get(HJ.get('run_id'), {}).get('root_run_no')} raiz={RZ['run_no']}")
check("ADR-0081 (F): los blobs siguen fuera del renglón tras el JOIN (usage_json / plan_json / frozen_record_json / "
      "thread_context_json / bundle_json) y no aparece ninguna columna cruda de la raíz salvo root_run_no",
      all(k not in det_hj for k in ("plan_json", "frozen_record_json", "usage_json", "bundle_json", "thread_context_json"))
      and not any(k.startswith("root_") and k not in ("root_run_no", "root_question_id") for k in det_hj),
      f"{sorted(k for k in det_hj if k.startswith('root_'))}")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
