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

2026-09-15 (ADR-0082 (J), rebanada C6): `plan_council_state` y `council_n_valid` viajan por renglón derivados de
runs.council_json (la copia server-side del consejo, F.4) como plan_niches de plan_json: llave PRESENTE con null
declarado cuando no hay consejo; lista == detalle == POST /runs; el blob council_json jamás al renglón. El check de
igualdad con el council.state del plan queda ROJO declarado hasta las costuras C4 (columna) y C5 (new_run(council_json=)).

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

# ---- ADR-0082 (J, vista; rebanada C6): plan_council_state / council_n_valid en la vista — lista == detalle ----------------
# Derivados de runs.council_json (la copia server-side de F.4) como plan_niches lo hace de plan_json. None = corrida sin plan,
# sin consejo o anterior al contrato: ausencia DECLARADA con la llave PRESENTE (jamás rellenada; 0 medido ≠ null).
import runs as runs_mod  # noqa: E402

lst3 = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
det_r1 = client.get("/runs/r1", headers=AUTH).json()
det_r2 = client.get("/runs/r2", headers=AUTH).json()
check("ADR-0082: plan_council_state y council_n_valid PRESENTES con null declarado en lista y detalle para una corrida con plan sin "
      "consejo (r1) y para una sin plan (r2); el blob council_json JAMÁS viaja al renglón",
      all(k in v and v[k] is None for v in (det_r1, det_r2, lst3.get("r1", {}), lst3.get("r2", {}))
          for k in ("plan_council_state", "council_n_valid"))
      and all("council_json" not in v for v in (det_r1, det_r2, lst3.get("r1", {}))),
      f"det_r1={det_r1.get('plan_council_state', 'AUSENTE')!r} lista_r1={lst3.get('r1', {}).get('plan_council_state', 'AUSENTE')!r}")


def _planner_fake(question, entities, thread_context=None):
    return ({"work_type": "sufficiency", "route": "evidence-run", "niches": [agent_matrix.NICHE_ENUM[0]],
             "agents_applicable": [], "clarifying_questions": []}, {"input_tokens": 1, "output_tokens": 1})


from lib import agent_matrix  # noqa: E402
runs_mod._default_planner = _planner_fake      # sin red: el juicio del plan lo da un fake (WITT_RUN_ORIGIN=smoke no encola)
pc = client.post("/runs/plan", json={"question": "¿plan con estado de consejo?", "entities": ["osr1"]}, headers=AUTH)
PC_STATE = (pc.json().get("council") or {}).get("state")
rc = client.post("/runs", json={"question": "¿plan con estado de consejo?", "entities": ["osr1"], "plan_id": pc.json()["plan_id"]},
                 headers=AUTH)
RC = rc.json()
# C9: la costura es REAL — runs.council_json en la fila (db.get_run / _list_select, E.1) y runs.new_run(council_json=) (F.4)
det_c = client.get(f"/runs/{RC['run_id']}", headers=AUTH).json()
lst4 = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
check("ADR-0082 (F.4): la fila de la corrida trae runs.council_json (la copia server-side, E.1) y el blob NO viaja al renglón",
      "council_json" in (db.get_run(RC["run_id"]) or {}) and (db.get_run(RC["run_id"]) or {}).get("council_json")
      and "council_json" not in RC and "council_json" not in det_c, f"keys={sorted(RC)[:6]}…")
check(f"ADR-0082: corrida con plan → plan_council_state == el council.state del plan ({PC_STATE!r}) en POST /runs, detalle y lista "
      "(misma consulta, misma llave — LOTE-01·A1)",
      pc.status_code == 200 and rc.status_code == 200 and PC_STATE is not None
      and RC.get("plan_council_state") == det_c.get("plan_council_state") == lst4.get(RC["run_id"], {}).get("plan_council_state") == PC_STATE,
      f"post={RC.get('plan_council_state')!r} det={det_c.get('plan_council_state')!r} lista={lst4.get(RC.get('run_id'), {}).get('plan_council_state')!r}")

# ---- ADR-0083 (L, vista; rebanada F5): epistemic_summary.figures_state / figures_n_verified / figures_n_cited — lista == detalle -----
# El resumen epistémico es passthrough del blob congelado al freeze (LOTE-02·3): las tres llaves nacen en runs (F4) y fluyen por
# _run_view SIN código nuevo. Se mide: (a) un resumen pre-1.12 (el de r1 arriba) NO gana las llaves en lista ni detalle (ausencia
# declarada, jamás rellenada con null); (b) sembradas, lista == detalle valor a valor; (c) r2 sin resumen sigue null.
_pre = det.get("epistemic_summary") or {}
with db.engine().begin() as cx:
    cx.execute(text("UPDATE runs SET epistemic_summary_json = :s WHERE run_id = 'r1'"),
               {"s": json.dumps({"retrieval_mode": "graph", "verdict": "APPROVE", "confidence_state": "value", "panel_n_valid": 4,
                                 "figures_state": "attached", "figures_n_verified": 9, "figures_n_cited": 2})})
det_f = client.get("/runs/r1", headers=AUTH).json()
lst5 = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
_es_f, _el_f = det_f.get("epistemic_summary") or {}, lst5.get("r1", {}).get("epistemic_summary") or {}
check("ADR-0083: epistemic_summary.figures_state/figures_n_verified/figures_n_cited — resumen pre-1.12: las llaves AUSENTES en lista y detalle "
      "(no se rellenan); sembradas ('attached', 9, 2): lista == detalle valor a valor; r2 sin resumen sigue null",
      all(k not in _pre and k not in (f1.get("epistemic_summary") or {}) for k in ("figures_state", "figures_n_verified", "figures_n_cited"))
      and _es_f.get("figures_state") == "attached" and _es_f.get("figures_n_verified") == 9 and _es_f.get("figures_n_cited") == 2
      and all(_es_f.get(k) == _el_f.get(k) for k in ("figures_state", "figures_n_verified", "figures_n_cited"))
      and _es_f == _el_f and lst5.get("r2", {}).get("epistemic_summary") is None,
      f"det={ {k: _es_f.get(k) for k in ('figures_state', 'figures_n_verified', 'figures_n_cited')} } lista={ {k: _el_f.get(k) for k in ('figures_state', 'figures_n_verified', 'figures_n_cited')} }")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
