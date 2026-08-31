"""
smoke_runs_list_http.py — gate de la lista enriquecida de /runs (2026-08-29): los códigos
de nicho del plan (`plan_niches`, derivados del plan_json guardado) y el veredicto del
panel (`epistemic_summary.verdict`, congelado al freeze — LOTE-02·3) viajan POR RENGLÓN.

Vía HTTP con TestClient (lección ADR-0075: el gate VE los campos sobre el stack completo,
el mismo camino de la webapp). Fija además las ausencias declaradas (corrida sin plan ⇒
plan_niches null · corrida sin registro congelado ⇒ epistemic_summary null), que la lista
y el detalle sirven la MISMA vista (LOTE-01·A1), y que los blobs (plan_json /
frozen_record_json) JAMÁS se filtran al renglón.

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

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
