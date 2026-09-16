"""
smoke_council_http.py — gate HTTP de las puertas del consejo de criterio (ADR-0082 (E.3), (F.1–F.4), (I), (H); rebanada C6).

Lo que MIDE, vía ASGI TestClient SIN lifespan (el mismo camino que la webapp — lección ADR-0075), con planner FAKE y
el worker de la ronda 1 hecho A MANO (sin lib.council ni red: escribe lo que el worker de C4 escribiría):
  · POST /runs/plan encola la ronda 1 SÓLO cuando aplica (route evidence-run ∧ niches ≠ [] ∧ judgment declared ∧ origin ∈
    WITT_COUNCIL_ORIGINS) → council.state 'queued' + poll/events/stream + evento council.state en la traza del plan;
    store-consultation / niches [] / origen fuera / kill-switch → 'not-requested (…)' | 'disabled (…)' y CERO jobs
  · dedup del doble clic: 2º POST idéntico en la ventana → 200 con plan_response 'reused' + reused_from_plan_id, planner
    llamado UNA vez; tope WITT_COUNCIL_MAX_QUEUED_PER_USER → 'not-requested (queue-cap per user)' (el plan sí se crea)
  · GET /plans/{id} 401/404/200 con council_state, run_gate y latido; /events?after= monotónico; SSE cierra con event: end
  · POST /runs {plan_id}: 409 council_round1_pending mientras r1 corre; 409 council_ledger_unapproved con r1 'applicable'
    sin aprobar ni saltar; 200 tras aprobar/saltar; runs.council_json compuesto SERVER-SIDE (plan_json byte-igual)
  · ledger: 400 hard_rule_requirements_undecided (causal-pruner, §7.1) · discard sin razón · aporto sin texto · id desconocido
    · decisión inválida · texto sobre el tope; borrador conserva decisiones humanas; approve → default-keep declarado,
    approved_by_is_author false con OTRA sesión; knowledge_now clase atestiguada; 409 tras el sello
  · skip: 400 sin razón; 200 → 'skipped-by-human' + eventos council.skip / council.state; la corrida sale con ledger vacío
  · WITT_COUNCIL=0 → 'disabled (kill-switch WITT_COUNCIL=0)' y POST /runs sin 409
  · GET /council/membership == agent_matrix.membership_view(os.environ) + catalog_sha de catalog_cards + vocabulary (C2)
  · GET /council/search: 400 sin q · 503 con WITT_COUNCIL_INDEX=0 · 503/200 según council_index (C7); GET /council/demand
    (ADR-0084 W6 — F.3: += web_locator_provider_state {provider, provider_source, available, unavailable_reason} — bajo la
    máscara `off` derivado con el literal byte-idéntico de 7d9ce15 —, unsatisfiable_families derivadas en la llamada +
    unsatisfiable_families_source, n_requirements_unsatisfiable_by_family con las 3 familias ESTÁTICAS; sin ruta nueva)
  · GET /usage.plans_council: sólo planes NO consumidos suman; by_state; totals de siempre intacto
  · /plans/* no captura /runs/{run_id} ni /runs/plan · urlopen bloqueado y contado == 0

DEPENDENCIAS EN PARALELO (ADR-0082 §Plan): la superficie de db.py es de C4, lib.council de C2, council_index de C7. Cuando
db.py aún no expone la superficie E.1, este smoke instala un FAKE en memoria con las firmas DECLARADAS por C6 (banner
[FAKE C4 ACTIVO]; jamás toca el esquema) para medir la lógica HTTP; tres checks quedan ROJOS a propósito hasta que C4/C2/C7
aterricen ("C4 real", "C2 importable", "C7 importable") — C9 retira el fake y los pone en verde.

NO-SPEND: sin red, sin modelo. BD sqlite temporal fuera del repo (una por smoke).
Uso (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr82-smoke_council_http.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_council_http.py
"""
import datetime
import inspect
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{(SMOKES_DIR / 'adr82-smoke_council_http.db').as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"       # dev sparse siempre está OFFLINE (LOTE-01·A5 override)
# ADR-0082 (E.3) / Context 9: el origen 'smoke' NO encola por default; este gate lo autoriza EXPLÍCITAMENTE (la ronda 1 aquí
# es un worker a mano, sin llamadas) y mide también el caso sin autorización.
os.environ["WITT_COUNCIL_ORIGINS"] = "smoke"
os.environ["WITT_COUNCIL"] = "1"
os.environ["WITT_COUNCIL_MAX_QUEUED_PER_USER"] = "3"
for _var in ("WITT_MODEL_GENERATION", "OPENAI_EMBED_MODEL", "WITT_COUNCIL_INDEX", "WITT_COUNCIL_EFFORT", "WITT_COUNCIL_FULL",
             "WITT_COUNCIL_DEDUP_S"):
    os.environ.pop(_var, None)

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------
import urllib.request as _urlreq  # noqa: E402

_URLOPEN_CALLS = []


def _urlopen_blocked(*a, **kw):
    _URLOPEN_CALLS.append(a[0] if a else kw.get("url"))
    raise RuntimeError("smoke_council_http: red bloqueada")


_urlreq.urlopen = _urlopen_blocked

import db  # noqa: E402
import app as app_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import agent_matrix, catalog_cards, models, search_harness  # noqa: E402
# el id del modelo del consejo se LEE de la tabla (rol `council`, D.2): cero literales de modelo fuera de models.py (M.4)
COUNCIL_MODEL = models.resolve_role("council")["model"]
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _fin():
    n_pass = sum(CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} PASS")
    sys.exit(0 if n_pass == len(CHECKS) else 1)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


# ---- la superficie E.1 de db.py (C4) y runs.new_run(council_json=) (C5) son REALES: C9 retiró el FAKE en memoria ------
# Lo que app.py invoca (firmas medidas abajo en el check "superficie E.1 real"):
#   db.create_plan(plan_id, user_id, question, entities, plan_json, origin=None, council_state=None)
#   db.get_plan(plan_id) -> fila con las columnas council_* (None cuando no hay) · db.update_plan_council(plan_id, **values)
#   db.plan_add_event(plan_id, type, payload=None, agent=None, tool=None, level='info'[, degraded]) -> seq
#   db.plan_events_after(plan_id, after_seq=0, limit=500) · db.set_plan_ledger(plan_id, ledger_json, approved_by=None,
#   council_state=None) -> bool · db.plans_council_pending(...) · db.count_plans_council(...) · db.plans_council_usage(...)
#   runs.new_run(..., council_json=<str>) y runs.council_json en db.get_run / db._list_select
_C4_SURFACE = ("update_plan_council", "plan_add_event", "plan_events_after", "set_plan_ledger", "plans_council_pending",
               "count_plans_council", "plans_council_usage", "council_schema_state", "plans_with_council")
C4_FALTANTES = [n for n in _C4_SURFACE if not callable(getattr(db, n, None))]
if "council_state" not in inspect.signature(db.create_plan).parameters:
    C4_FALTANTES.append("create_plan(origin=, council_state=)")
C5_NEW_RUN_SIN_COUNCIL = "council_json" not in inspect.signature(runs_mod.new_run).parameters

# ---- planner FAKE: el juicio que decide si el plan encola (route / niches) ------------------------------------------
PLANNER_CALLS = []
NICHE = agent_matrix.NICHE_ENUM[0]


def _planner(route="evidence-run", niches=(NICHE,)):
    def fake(question, entities, thread_context=None):
        PLANNER_CALLS.append(question)
        return ({"work_type": "sufficiency", "route": route, "niches": list(niches),
                 "agents_applicable": [{"agent": a, "reason": "smoke"}
                                       for a in ("causal-pruner", "hypothesis-generator", "composite-auditor")],
                 "clarifying_questions": []},
                {"input_tokens": 400, "output_tokens": 120})
    return fake


runs_mod._default_planner = _planner()

db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
client = TestClient(app_mod.app)
NAT = {"Authorization": "Bearer " + client.post("/login", json={"username": "natalia", "password": "pw-natalia"}).json()["token"]}
EMM = {"Authorization": "Bearer " + client.post("/login", json={"username": "emmanuel", "password": "pw-emmanuel"}).json()["token"]}

# ---- 0. las costuras que este smoke ejerce son REALES (C9): superficie E.1 en db.py Y en la BD del gate, módulos hermanos ---
check("superficie E.1 real: db.py expone toda la superficie ADR-0082 (sin fake), runs.new_run acepta council_json= y la BD del "
      "gate la tiene migrada (db.council_schema_state ready; app._council_db_missing() == [])",
      not C4_FALTANTES and not C5_NEW_RUN_SIN_COUNCIL and db.council_schema_state()["ready"] is True
      and app_mod._council_db_missing() == [], f"faltan={C4_FALTANTES} new_run_sin_council={C5_NEW_RUN_SIN_COUNCIL}")
check("lib.council y council_index cargados en app por import DIRECTO (COUNCIL_MODULE_STATE / COUNCIL_INDEX_MODULE_STATE 'loaded'; "
      "los mismos objetos que importa este smoke)",
      app_mod.council_mod is not None and app_mod.council_index_mod is not None
      and app_mod.COUNCIL_MODULE_STATE == "loaded" and app_mod.COUNCIL_INDEX_MODULE_STATE == "loaded",
      f"{app_mod.COUNCIL_MODULE_STATE} · {app_mod.COUNCIL_INDEX_MODULE_STATE}")

# ---- 1. POST /runs/plan encola la ronda 1 cuando aplica (E.3) --------------------------------------------------------
Q1 = "¿osr1 es suficiente para inducir el pronefros?"
r = client.post("/runs/plan", json={"question": Q1, "entities": ["osr1"]}, headers=NAT)
P1R = r.json() if r.status_code == 200 else {}
P1 = P1R.get("plan_id")
C1 = P1R.get("council") or {}
check("POST /runs/plan (evidence-run, nichos, juicio declarado, origen autorizado) -> 200 · council.state 'queued' · "
      "plan_response 'created'",
      r.status_code == 200 and C1.get("state") == "queued" and P1R.get("plan_response") == "created", r.text[:300])
check("council: poll/events/stream = /plans/{id}[/events|/stream] · membership_version 'cm-1' · n_members 17 · full_council false"
      " · catalog_sha == catalog_cards.CATALOG_SHA · matrix v1.3",
      C1.get("poll") == f"/plans/{P1}" and C1.get("events") == f"/plans/{P1}/events" and C1.get("stream") == f"/plans/{P1}/stream"
      and C1.get("membership_version") == agent_matrix.MEMBERSHIP_VERSION == "cm-1" and C1.get("n_members") == 17
      and C1.get("full_council") is False and C1.get("catalog_sha") == catalog_cards.CATALOG_SHA
      and C1.get("matrix_version") == agent_matrix.MATRIX_VERSION,
      f"{ {k: C1.get(k) for k in ('poll', 'membership_version', 'n_members', 'full_council', 'catalog_sha')} }")
check("council.budget {member_timeout_s, round_budget_s, concurrency, quorum, quorum_required 11, source} · council.model {model, "
      "source, generation, effort 'medium' (E2), effort_source} · estimate.class 'PROJECTION' con supuestos (usd null ⇔ modelo sin precio)",
      set(C1.get("budget", {})) >= {"member_timeout_s", "round_budget_s", "concurrency", "quorum", "quorum_required", "source"}
      and C1["budget"]["quorum_required"] == 11
      and set(C1.get("model", {})) >= {"model", "source", "generation", "effort", "effort_source"}
      and C1["model"]["effort"] == "medium"
      and C1.get("estimate", {}).get("class") == "PROJECTION" and len(C1["estimate"].get("assumptions") or []) >= 4
      and ((C1["estimate"]["usd_low"] is None) == (C1["model"]["model"] is None or C1["estimate"]["state"] != "projected")),
      f"budget={C1.get('budget')} model={C1.get('model')} estimate={ {k: C1.get('estimate', {}).get(k) for k in ('usd_low', 'usd_high', 'state')} }")
check("origin del plan = runs.run_origin() ({value 'smoke', source 'env:WITT_RUN_ORIGIN'}) · gates declaran origins_allowed ['smoke'],"
      " dedup_window_s 600 (default), max_queued_per_user 3 (env), kill_switch enabled",
      P1R.get("origin") == {"value": "smoke", "source": "env:WITT_RUN_ORIGIN"}
      and C1.get("gates", {}).get("origins_allowed") == ["smoke"] and C1["gates"]["dedup_window_s"] == 600
      and C1["gates"]["max_queued_per_user"] == 3 and C1["gates"]["kill_switch"]["enabled"] is True,
      f"{P1R.get('origin')} {C1.get('gates')}")
ev0 = client.get(f"/plans/{P1}/events", headers=NAT)
check("la traza del PLAN nace con council.state {state 'queued', plan_id, origin, n_members, membership_version, catalog_sha} (agent 'council')",
      ev0.status_code == 200 and len(ev0.json().get("events", [])) == 1 and ev0.json()["events"][0]["type"] == "council.state"
      and ev0.json()["events"][0]["payload"]["state"] == "queued" and ev0.json()["events"][0]["agent"] == "council"
      and ev0.json()["events"][0]["payload"]["catalog_sha"] == catalog_cards.CATALOG_SHA
      and ev0.json().get("council_state") == "queued", ev0.text[:300])

# ---- 2. dedup del doble clic (E.3) --------------------------------------------------------------------------------------
n_calls = len(PLANNER_CALLS)
r2 = client.post("/runs/plan", json={"question": Q1, "entities": ["osr1"]}, headers=NAT)
check("2º POST idéntico (mismo usuario, misma question+entities, sin padre) en la ventana -> 200 plan_response 'reused', "
      "reused_from_plan_id == plan 1, reused_reason con 'queued', el planner NO se llamó",
      r2.status_code == 200 and r2.json().get("plan_response") == "reused" and r2.json().get("reused_from_plan_id") == P1
      and r2.json().get("plan_id") == P1 and "queued" in (r2.json().get("reused_reason") or "")
      and len(PLANNER_CALLS) == n_calls and r2.json().get("council", {}).get("state") == "queued", r2.text[:300])
r2b = client.post("/runs/plan", json={"question": Q1, "entities": ["osr1"]}, headers=EMM)
check("OTRO usuario con la misma pregunta NO reutiliza (el dedup es por usuario): plan nuevo 'queued'",
      r2b.status_code == 200 and r2b.json().get("plan_response") == "created" and r2b.json()["plan_id"] != P1
      and r2b.json()["council"]["state"] == "queued", r2b.text[:200])
P_EMM = r2b.json()["plan_id"]
r2c = client.post("/runs/plan", json={"question": Q1, "entities": ["osr1", "wt1a"]}, headers=NAT)
check("entidades distintas NO reutilizan: plan nuevo (dedup exacto por question+entities_csv+parent)",
      r2c.status_code == 200 and r2c.json().get("plan_response") == "created" and r2c.json()["plan_id"] != P1, r2c.text[:200])
P2 = r2c.json()["plan_id"]

# ---- 3. compuertas: ruta, nichos, origen, kill-switch → 'not-requested (…)' | 'disabled (…)' y CERO jobs ----------------
n_queued_antes = db.count_plans_council(states=("queued",))
runs_mod._default_planner = _planner(route="store-consultation")
rs = client.post("/runs/plan", json={"question": "¿cuántos registros tiene el store?", "entities": []}, headers=NAT)
runs_mod._default_planner = _planner(niches=())
rn = client.post("/runs/plan", json={"question": "¿pregunta sin nicho?", "entities": []}, headers=NAT)
runs_mod._default_planner = _planner()
os.environ["WITT_COUNCIL_ORIGINS"] = "production"
ro = client.post("/runs/plan", json={"question": "¿pregunta con origen no autorizado?", "entities": []}, headers=NAT)
os.environ["WITT_COUNCIL_ORIGINS"] = "smoke"
check("route store-consultation -> 'not-requested (route store-consultation)'",
      rs.status_code == 200 and rs.json()["council"]["state"] == "not-requested (route store-consultation)",
      rs.json().get("council", {}).get("state"))
check("niches [] -> 'not-requested (niches empty)'",
      rn.status_code == 200 and rn.json()["council"]["state"] == "not-requested (niches empty)", rn.json().get("council", {}).get("state"))
check("WITT_RUN_ORIGIN=smoke sin 'smoke' en WITT_COUNCIL_ORIGINS -> 'not-requested (origin smoke not in WITT_COUNCIL_ORIGINS)'",
      ro.status_code == 200 and ro.json()["council"]["state"] == "not-requested (origin smoke not in WITT_COUNCIL_ORIGINS)",
      ro.json().get("council", {}).get("state"))
check("ninguna de las tres encoló (CERO jobs nuevos) y sus planes SÍ existen con el estado declarado",
      db.count_plans_council(states=("queued",)) == n_queued_antes
      and all(client.get(f"/plans/{x.json()['plan_id']}", headers=NAT).json()["council_state"].startswith("not-requested (")
              for x in (rs, rn, ro))
      and all(client.get(f"/plans/{x.json()['plan_id']}/events", headers=NAT).json()["events"] == [] for x in (rs, rn, ro)))
check("planes 'not-requested (…)' NO bloquean POST /runs (run_gate.allowed true, sin 409 del consejo)",
      client.get(f"/plans/{rn.json()['plan_id']}", headers=NAT).json()["run_gate"]
      == {"allowed": True, "reason": None, "council_state": "not-requested (niches empty)", "kill_switch": False})

# ---- 4. tope de jobs queued por usuario -------------------------------------------------------------------------------
r3 = client.post("/runs/plan", json={"question": "¿tercera pregunta distinta?", "entities": []}, headers=NAT)
P3 = r3.json()["plan_id"]
r4 = client.post("/runs/plan", json={"question": "¿cuarta pregunta distinta?", "entities": []}, headers=NAT)
check("natalia con 3 jobs 'queued' (P1, P2, P3): el 4º nace 'not-requested (queue-cap per user)' — el plan SÍ se crea",
      r3.json()["council"]["state"] == "queued" and r4.status_code == 200
      and r4.json()["council"]["state"] == "not-requested (queue-cap per user)" and bool(r4.json().get("plan_id")),
      f"P3={r3.json()['council']['state']} P4={r4.json().get('council', {}).get('state')}")

# ---- 5. GET /plans/{id}: 401/404/200 y la puerta de la corrida mientras r1 corre ------------------------------------------
check("GET /plans/{id} sin token -> 401", client.get(f"/plans/{P1}").status_code == 401)
check("GET /plans/nope -> 404 plan_not_found", client.get("/plans/nope", headers=NAT).status_code == 404
      and client.get("/plans/nope", headers=NAT).json()["detail"]["state"] == "plan_not_found")
pv = client.get(f"/plans/{P1}", headers=NAT).json()
check("GET /plans/{id} -> 200 {plan_id, plan, origin 'smoke', council_state 'queued', council null, ledger null, run_id null, "
      "heartbeat_age_s, heartbeat_stale false, heartbeat_stale_after_s 300, run_gate {allowed false, reason council_round1_pending}}",
      pv.get("plan_id") == P1 and pv.get("plan", {}).get("judgment", {}).get("state") == "declared" and pv.get("origin") == "smoke"
      and pv.get("council_state") == "queued" and pv.get("council") is None and pv.get("ledger") is None and pv.get("run_id") is None
      and isinstance(pv.get("heartbeat_age_s"), (int, float)) and pv.get("heartbeat_stale") is False
      and pv.get("heartbeat_stale_after_s") == app_mod.HEARTBEAT_STALE_S
      and pv.get("run_gate") == {"allowed": False, "reason": "council_round1_pending", "council_state": "queued", "kill_switch": False},
      f"{ {k: pv.get(k) for k in ('council_state', 'origin', 'heartbeat_age_s', 'heartbeat_stale', 'run_gate')} }")
rr = client.post("/runs", json={"question": Q1, "entities": ["osr1"], "plan_id": P1}, headers=NAT)
check("POST /runs {plan_id} con r1 'queued' -> 409 council_round1_pending {plan_id, council_state, poll}",
      rr.status_code == 409 and rr.json()["detail"]["state"] == "council_round1_pending"
      and rr.json()["detail"]["plan_id"] == P1 and rr.json()["detail"]["council_state"] == "queued"
      and rr.json()["detail"]["poll"] == f"/plans/{P1}", rr.text[:300])
check("ledger y skip con r1 'queued' -> 409 council_not_terminal {council_state}",
      client.post(f"/plans/{P1}/council/ledger", json={"decisions": [], "approve": True}, headers=NAT).status_code == 409
      and client.post(f"/plans/{P1}/council/ledger", json={"decisions": [], "approve": True}, headers=NAT).json()["detail"]["state"]
      == "council_not_terminal"
      and client.post(f"/plans/{P1}/council/skip", json={"reason": "x"}, headers=NAT).json()["detail"]["state"] == "council_not_terminal")

# ---- 6. el worker A MANO (lo que C4 escribe con lib.council): running → member × 3 → applicable + requisitos ----------------
REQS = [
    {"requirement_id": "req-a1b2c3d4e5f6", "gap": "phenotype of osr1 morphants at 24 hpf", "evidence_kind": "phenotype",
     "source_family": "zfin", "query_en": "osr1 pronephros phenotype", "entities": ["osr1"], "priority": "must",
     "requested_by": ["causal-pruner"], "n_requested_by": 1, "n_members": 17, "hard_rule_gate": True, "exploratory": False,
     "from_operative": False, "harness_state": "satisfiable"},
    {"requirement_id": "req-0f0f0f0f0f0f", "gap": "expression of lhx1a in intermediate mesoderm", "evidence_kind": "expression",
     "source_family": "zfin_expression", "query_en": "lhx1a expression 18 somites", "entities": ["lhx1a"], "priority": "should",
     "requested_by": ["literature-monitor", "scrna-seq-analyst"], "n_requested_by": 2, "n_members": 17, "hard_rule_gate": False,
     "exploratory": False, "from_operative": False, "harness_state": "satisfiable"},
    {"requirement_id": "req-9999aaaabbbb", "gap": "preprints on osr1 sufficiency", "evidence_kind": "web", "source_family": "web",
     "query_en": "osr1 sufficiency pronephros preprint", "entities": [], "priority": "must", "requested_by": ["hypothesis-generator"],
     "n_requested_by": 1, "n_members": 17, "hard_rule_gate": False, "exploratory": False, "from_operative": False,
     # ADR-0084 (F.1): el literal que council.harness_state_for produce bajo off — importado, no copiado (UNA verdad)
     "harness_state": search_harness.WEB_UNSATISFIABLE_LITERAL},
]
assert REQS[2]["harness_state"] == "unsatisfiable-by-harness (tool-unavailable (ADR-0084))"


def _worker_a_mano(pid, reqs, n_valid=17, usage=None, state="applicable"):
    db.update_plan_council(pid, council_state="running", council_claimed_by="smoke:0:council-worker-0", council_started_at=_now())
    db.plan_add_event(pid, "council.state", payload={"state": "running", "plan_id": pid, "claimed_by": "smoke:0:council-worker-0"},
                      agent="council")
    for m in agent_matrix.MEMBERS[:3]:
        # corrector ADR-0082 (F20): la MISMA forma que emite council.run_round en phase 'done' (round, error_kind, attempts,
        # attempt, cache_read) — el fixture plan-eventos-consejo.json nace del job REAL (sección 16e mide la paridad de forma)
        db.plan_add_event(pid, "stage.council.member", payload={"round": "r1", "agent": m, "tool": "emit_information_requirements",
                                                                "phase": "done", "status": "ok", "error_kind": None, "elapsed_s": 1.0,
                                                                "attempts": 1, "attempt": 1, "max_attempts": 2, "cache_read": 2400,
                                                                "heartbeat": True}, agent="council", tool="emit_information_requirements")
    cj = {"module_version": "council-1", "membership_version": agent_matrix.MEMBERSHIP_VERSION, "n_members": 17,
          "members": list(agent_matrix.MEMBERS), "full_council": False, "catalog_sha": catalog_cards.CATALOG_SHA,
          "rounds": [{"round": "r1", "kind": "requirements", "phase": "plan", "n_invoked": 17, "n_valid": n_valid,
                      "usage": usage or {"in": 0, "out": 0, "cache_creation": 0, "cache_read": 0}}],
          "requirements": reqs, "flags": [], "aggregation_sha": "smoke-aggregation-sha", "state": state}
    db.update_plan_council(pid, council_state=state, council_json=json.dumps(cj, ensure_ascii=False),
                           council_usage_json=json.dumps(usage) if usage else None, council_finished_at=_now())
    # corrector ADR-0082 (F20): las 15 llaves REALES de stage.council.aggregate (council_jobs.execute_round1), contadas de `reqs`
    db.plan_add_event(pid, "stage.council.aggregate", payload={
        "n_raw": len(reqs), "n_dedup": len(reqs), "n_requirements": len(reqs),
        "n_must": sum(1 for r in reqs if r["priority"] == "must"), "n_should": sum(1 for r in reqs if r["priority"] == "should"),
        "n_truncated": 0, "n_unsatisfiable": sum(1 for r in reqs if str(r.get("harness_state", "")).startswith("unsatisfiable")),
        "n_hard_rule": sum(1 for r in reqs if r.get("hard_rule_gate")), "n_flags": 0, "n_valid": n_valid, "n_members": 17,
        "catalog_sha": catalog_cards.CATALOG_SHA, "aggregation_sha": "smoke-aggregation-sha", "state": state,
        "decided_by": "code (council.aggregate_r1)"}, agent="council")
    db.plan_add_event(pid, "council.state", payload={"state": state, "plan_id": pid}, agent="council")


_worker_a_mano(P1, REQS, usage={"in": 71400, "out": 25500, "cache_creation": 2400, "cache_read": 38400, "model": COUNCIL_MODEL})
evs = client.get(f"/plans/{P1}/events", headers=NAT).json()["events"]
seqs = [e["seq"] for e in evs]
check("GET /plans/{id}/events: seq monotónico (1..7) · tipos council.state → stage.council.member ×3 → stage.council.aggregate → "
      "council.state · council_state 'applicable' en el sobre",
      seqs == list(range(1, 8)) and [e["type"] for e in evs][:2] == ["council.state", "council.state"]
      and [e["type"] for e in evs].count("stage.council.member") == 3 and evs[-1]["payload"]["state"] == "applicable"
      and client.get(f"/plans/{P1}/events", headers=NAT).json()["council_state"] == "applicable", f"seqs={seqs}")
check("?after=5 devuelve sólo seq > 5 (cursor exclusivo, como /runs/{id}/events)",
      [e["seq"] for e in client.get(f"/plans/{P1}/events?after=5", headers=NAT).json()["events"]] == [6, 7])
with client.stream("GET", f"/plans/{P1}/stream?after=0", headers=NAT) as sr:
    sse = "".join(sr.iter_text())
_data_lines = [ln for ln in sse.split("\n") if ln.startswith("data: ")]
check("GET /plans/{id}/stream (SSE, el MISMO generador que /runs/{id}/stream): 7 eventos `data:` + el del cierre, y cierra con "
      "`event: end` + {council_state 'applicable'}",
      len(_data_lines) == 8 and json.loads(_data_lines[0][6:])["seq"] == 1 and json.loads(_data_lines[6][6:])["seq"] == 7
      and "event: end\ndata: {\"council_state\": \"applicable\"}" in sse, sse[-160:].replace("\n", "\\n"))
pv2 = client.get(f"/plans/{P1}", headers=NAT).json()
check("GET /plans/{id} tras r1: council_state 'applicable' · council.requirements 3 · council.catalog_sha · council_usage con caché · "
      "run_gate {allowed false, reason council_ledger_unapproved} · council_finished_at/claimed_by servidos",
      pv2["council_state"] == "applicable" and len(pv2["council"]["requirements"]) == 3
      and pv2["council"]["catalog_sha"] == catalog_cards.CATALOG_SHA and pv2["council_usage"]["cache_read"] == 38400
      and pv2["run_gate"]["allowed"] is False and pv2["run_gate"]["reason"] == "council_ledger_unapproved"
      and pv2["council_claimed_by"] == "smoke:0:council-worker-0" and isinstance(pv2["council_finished_at"], str),
      f"{ {k: pv2.get(k) for k in ('council_state', 'run_gate', 'council_claimed_by')} }")
rr2 = client.post("/runs", json={"question": Q1, "entities": ["osr1"], "plan_id": P1}, headers=NAT)
check("POST /runs {plan_id} con r1 'applicable' sin ledger aprobado -> 409 council_ledger_unapproved {plan_id, council_state}",
      rr2.status_code == 409 and rr2.json()["detail"]["state"] == "council_ledger_unapproved"
      and rr2.json()["detail"]["council_state"] == "applicable", rr2.text[:200])

# ---- 7. el ledger (F.1): las 400 tipadas ---------------------------------------------------------------------------------
L = f"/plans/{P1}/council/ledger"


def _400(body, headers=NAT):
    r_ = client.post(L, json=body, headers=headers)
    return (r_.status_code, r_.json().get("detail", {}))


st, det = _400({"decisions": [], "approve": True})
check("approve sin decidir el requisito de causal-pruner -> 400 hard_rule_requirements_undecided [req-a1b2…] con la regla §7.1",
      st == 400 and det.get("state") == "hard_rule_requirements_undecided" and det.get("ids") == ["req-a1b2c3d4e5f6"]
      and "§7.1" in det.get("rule", ""), f"{st} {det}")
st, det = _400({"decisions": [{"requirement_id": "req-nope", "decision": "keep"}], "approve": False})
check("requirement_id desconocido -> 400 unknown_requirement_id [ids] (+ known[])",
      st == 400 and det.get("state") == "unknown_requirement_id" and det.get("ids") == ["req-nope"] and len(det.get("known", [])) == 3)
st, det = _400({"decisions": [{"requirement_id": "req-0f0f0f0f0f0f", "decision": "discard"}], "approve": False})
check("discard sin razón -> 400 discard_without_reason [ids]", st == 400 and det.get("state") == "discard_without_reason"
      and det.get("ids") == ["req-0f0f0f0f0f0f"])
st, det = _400({"decisions": [{"requirement_id": "req-9999aaaabbbb", "decision": "aporto", "attested_text": "  "}], "approve": False})
check("aporto sin texto -> 400 aporto_without_text [ids]", st == 400 and det.get("state") == "aporto_without_text"
      and det.get("ids") == ["req-9999aaaabbbb"])
st, det = _400({"decisions": [{"requirement_id": "req-0f0f0f0f0f0f", "decision": "maybe"}], "approve": False})
check("decisión fuera de keep|discard|aporto -> 400 invalid_decision [ids] + allowed",
      st == 400 and det.get("state") == "invalid_decision" and det.get("allowed") == ["keep", "discard", "aporto"])
st, det = _400({"decisions": [{"requirement_id": "req-9999aaaabbbb", "decision": "aporto", "attested_text": "x" * 4001}], "approve": False})
check("attested_text > WITT_COUNCIL_ATTESTATION_CHARS (4000 default) -> 400 attested_text_too_long con el tope y su fuente",
      st == 400 and det.get("state") == "attested_text_too_long" and det.get("max_chars") == 4000
      and det.get("max_chars_source") == "default-unset:WITT_COUNCIL_ATTESTATION_CHARS", f"{st} {det}")
st, det = _400({"decisions": [], "knowledge_now": "k" * 4001, "approve": False})
check("knowledge_now > tope -> 400 knowledge_now_too_long", st == 400 and det.get("state") == "knowledge_now_too_long")
st, det = _400({"decisions": [{"requirement_id": "req-0f0f0f0f0f0f", "decision": "keep"},
                              {"requirement_id": "req-0f0f0f0f0f0f", "decision": "discard", "reason": "dup"}], "approve": False})
check("el mismo requirement_id dos veces en un cuerpo -> 400 duplicated_requirement_id",
      st == 400 and det.get("state") == "duplicated_requirement_id")

# ---- 8. borrador → aprobación por OTRA sesión ---------------------------------------------------------------------------
rd = client.post(L, json={"decisions": [{"requirement_id": "req-0f0f0f0f0f0f", "decision": "discard",
                                          "reason": "ya cubierto por la DI"}], "approve": False}, headers=NAT)
LD = rd.json().get("ledger", {}) if rd.status_code == 200 else {}
dd = {d["requirement_id"]: d for d in LD.get("decisions", [])}
check("borrador (approve false) -> 200 ledger.state 'draft' · 3 filas en el orden del agregado · req-a1b2 pending decided_by "
      "'gate-human-pending' · req-0f0f discard decided_by 'human:natalia' con razón · req-9999 pending decided_by null · n_pending 2",
      rd.status_code == 200 and LD.get("state") == "draft" and [d["requirement_id"] for d in LD["decisions"]] == [r_["requirement_id"] for r_ in REQS]
      and dd["req-a1b2c3d4e5f6"]["decision"] == "pending" and dd["req-a1b2c3d4e5f6"]["decided_by"] == "gate-human-pending"
      and dd["req-a1b2c3d4e5f6"]["hard_rule_gate"] is True
      and dd["req-0f0f0f0f0f0f"]["decision"] == "discard" and dd["req-0f0f0f0f0f0f"]["decided_by"] == "human:natalia"
      and dd["req-0f0f0f0f0f0f"]["reason"] == "ya cubierto por la DI"
      and dd["req-9999aaaabbbb"]["decision"] == "pending" and dd["req-9999aaaabbbb"]["decided_by"] is None
      and LD.get("n_pending") == 2 and LD.get("approved_by") is None and LD.get("n_saves") == 1, rd.text[:400])
check("el borrador queda en GET /plans/{id}.ledger y la corrida sigue bloqueada (run_gate council_ledger_unapproved)",
      client.get(f"/plans/{P1}", headers=NAT).json()["ledger"]["state"] == "draft"
      and client.get(f"/plans/{P1}", headers=NAT).json()["run_gate"]["reason"] == "council_ledger_unapproved")
ra = client.post(L, json={"decisions": [{"requirement_id": "req-a1b2c3d4e5f6", "decision": "keep"},
                                          {"requirement_id": "req-9999aaaabbbb", "decision": "aporto",
                                           "attested_text": "Preprint bioRxiv 2026 muestra osr1 suficiente; gen ENSDARG00000099999"}],
                            "knowledge_now": "Sabemos que osr1 es necesario; suficiencia sin demostrar.", "approve": True}, headers=EMM)
LA = ra.json().get("ledger", {}) if ra.status_code == 200 else {}
da = {d["requirement_id"]: d for d in LA.get("decisions", [])}
check("approve por emmanuel (OTRA sesión) -> 200 ledger.state 'approved' · approved_by 'emmanuel' · approved_by_is_author FALSE · "
      "req-a1b2 keep human:emmanuel · req-0f0f conserva el discard humano del borrador · req-9999 aporto con attested_text/chars/"
      "attested_class 'attested' · n_default_keep 0 · n_pending 0 · n_saves 2",
      ra.status_code == 200 and LA.get("state") == "approved" and LA.get("approved_by") == "emmanuel"
      and LA.get("approved_by_is_author") is False
      and da["req-a1b2c3d4e5f6"]["decision"] == "keep" and da["req-a1b2c3d4e5f6"]["decided_by"] == "human:emmanuel"
      and da["req-0f0f0f0f0f0f"]["decision"] == "discard" and da["req-0f0f0f0f0f0f"]["decided_by"] == "human:natalia"
      and da["req-9999aaaabbbb"]["decision"] == "aporto" and da["req-9999aaaabbbb"]["attested_class"] == "attested"
      and da["req-9999aaaabbbb"]["attested_chars"] == len(da["req-9999aaaabbbb"]["attested_text"])
      and LA.get("n_default_keep") == 0 and LA.get("n_pending") == 0 and LA.get("n_saves") == 2
      and LA.get("n_keep") == 1 and LA.get("n_discard") == 1 and LA.get("n_aporto") == 1, ra.text[:500])
check("knowledge_now {text, class 'attested', by 'emmanuel', at, chars, truncated false} — clase atestiguada, jamás evidencia (F.5)",
      LA.get("knowledge_now", {}).get("class") == "attested" and LA["knowledge_now"]["by"] == "emmanuel"
      and LA["knowledge_now"]["chars"] == len(LA["knowledge_now"]["text"]) and LA["knowledge_now"]["truncated"] is False
      and LA.get("permissions_rule") == app_mod.COUNCIL_PERMISSIONS_RULE)
evs2 = client.get(f"/plans/{P1}/events", headers=NAT).json()["events"]
check("evento council.ledger {approved_by, n_keep, n_discard, n_aporto, knowledge_now_present true} en la traza del plan (sólo al aprobar)",
      [e["type"] for e in evs2].count("council.ledger") == 1
      and evs2[-1]["type"] == "council.ledger" and evs2[-1]["payload"]["approved_by"] == "emmanuel"
      and evs2[-1]["payload"]["knowledge_now_present"] is True and evs2[-1]["payload"]["n_discard"] == 1, f"{[e['type'] for e in evs2]}")
pv3 = client.get(f"/plans/{P1}", headers=NAT).json()
check("GET /plans/{id} tras aprobar: approved_by 'emmanuel' (columna) · approved_at · approved_by_is_author false · run_gate allowed",
      pv3["approved_by"] == "emmanuel" and isinstance(pv3["approved_at"], str) and pv3["approved_by_is_author"] is False
      and pv3["run_gate"] == {"allowed": True, "reason": None, "council_state": "applicable", "kill_switch": False},
      f"{ {k: pv3.get(k) for k in ('approved_by', 'approved_at', 'run_gate')} }")

# ---- 9. POST /runs tras aprobar: la copia SERVER-SIDE (F.4) y la vista (plan_council_state) ------------------------------
rr3 = client.post("/runs", json={"question": Q1, "entities": ["osr1"], "plan_id": P1}, headers=NAT)
RUN1 = rr3.json().get("run_id") if rr3.status_code == 200 else None
check("POST /runs {plan_id} con ledger aprobado -> 200 · plan_declared true · plan_council_state 'applicable' · council_n_valid 17 · "
      "sin blob council_json en la vista",
      rr3.status_code == 200 and rr3.json().get("plan_declared") is True and rr3.json().get("plan_council_state") == "applicable"
      and rr3.json().get("council_n_valid") == 17 and "council_json" not in rr3.json(), rr3.text[:300])
run_row = db.get_run(RUN1) if RUN1 else {}
RCJ = json.loads(run_row["council_json"]) if (run_row or {}).get("council_json") else None
check("runs.council_json compuesto en el SERVIDOR: {plan_id, r1_state 'applicable', r1 == plans.council_json, ledger.state 'approved', "
      "membership_version 'cm-1', n_members 17, members[17], catalog_sha, membership_source 'plan.council (frozen at r1)', composed_at, source}",
      isinstance(RCJ, dict) and RCJ.get("plan_id") == P1 and RCJ.get("r1_state") == "applicable"
      and RCJ.get("r1") == json.loads(db.get_plan(P1)["council_json"]) and RCJ.get("ledger", {}).get("state") == "approved"
      and RCJ.get("membership_version") == "cm-1" and RCJ.get("n_members") == 17 and len(RCJ.get("members") or []) == 17
      and RCJ.get("catalog_sha") == catalog_cards.CATALOG_SHA and RCJ.get("membership_source") == "plan.council (frozen at r1)"
      and RCJ.get("source") == "plans.council_json + plans.council_ledger_json (copied at enqueue)",
      f"keys={sorted(RCJ) if isinstance(RCJ, dict) else RCJ}")
check("runs.plan_json sigue BYTE-IGUAL a plans.plan_json (plan_question_matches_run intacto) y el plan quedó sellado (run_id)",
      bool(run_row) and run_row.get("plan_json") == db.get_plan(P1)["plan_json"] and db.get_plan(P1)["run_id"] == RUN1)
lst = {r_["run_id"]: r_ for r_ in client.get("/runs", headers=NAT).json()["runs"]}
det = client.get(f"/runs/{RUN1}", headers=NAT).json()
check("_run_view.plan_council_state: lista == detalle == 'applicable' (misma-vista, LOTE-01·A1) y council_n_valid 17 en ambos",
      lst.get(RUN1, {}).get("plan_council_state") == det.get("plan_council_state") == "applicable"
      and lst[RUN1].get("council_n_valid") == det.get("council_n_valid") == 17, f"lista={lst.get(RUN1, {}).get('plan_council_state')} det={det.get('plan_council_state')}")
check("ledger y skip tras el sello -> 409 plan_already_used {run_id}",
      client.post(L, json={"decisions": [], "approve": True}, headers=NAT).status_code == 409
      and client.post(L, json={"decisions": [], "approve": True}, headers=NAT).json()["detail"]["state"] == "plan_already_used"
      and client.post(f"/plans/{P1}/council/skip", json={"reason": "tarde"}, headers=NAT).json()["detail"]["state"] == "plan_already_used")

# ---- 10. skip (F.2) -------------------------------------------------------------------------------------------------------
_worker_a_mano(P2, REQS[:2])
check("skip sin razón -> 400 skip_without_reason",
      client.post(f"/plans/{P2}/council/skip", json={"reason": "  "}, headers=NAT).status_code == 400
      and client.post(f"/plans/{P2}/council/skip", json={"reason": ""}, headers=NAT).json()["detail"]["state"] == "skip_without_reason")
rk = client.post(f"/plans/{P2}/council/skip", json={"reason": "urge; el consejo pidió lo que ya sé"}, headers=NAT)
LK = rk.json().get("ledger", {}) if rk.status_code == 200 else {}
check("skip con razón -> 200 council_state 'skipped-by-human' · ledger {state 'skipped-by-human', decisions [], n_requirements 2 "
      "(medido), skipped_by 'natalia', skipped_at, reason, approved_by_is_author true}",
      rk.status_code == 200 and rk.json().get("council_state") == "skipped-by-human" and LK.get("state") == "skipped-by-human"
      and LK.get("decisions") == [] and LK.get("n_requirements") == 2 and LK.get("skipped_by") == "natalia"
      and LK.get("reason") == "urge; el consejo pidió lo que ya sé" and LK.get("approved_by_is_author") is True, rk.text[:300])
evk = client.get(f"/plans/{P2}/events", headers=NAT).json()["events"]
check("traza del plan: council.skip {by, reason} + council.state {state 'skipped-by-human'}; GET /plans/{id}.council_state y run_gate allowed",
      [e["type"] for e in evk][-2:] == ["council.skip", "council.state"] and evk[-2]["payload"]["by"] == "natalia"
      and evk[-1]["payload"]["state"] == "skipped-by-human"
      and client.get(f"/plans/{P2}", headers=NAT).json()["council_state"] == "skipped-by-human"
      and client.get(f"/plans/{P2}", headers=NAT).json()["run_gate"]["allowed"] is True)
check("un segundo skip / un ledger sobre un plan saltado -> 409 council_ledger_not_applicable (sin requisitos que decidir)",
      client.post(f"/plans/{P2}/council/skip", json={"reason": "otra"}, headers=NAT).json()["detail"]["state"] == "council_ledger_not_applicable"
      and client.post(f"/plans/{P2}/council/ledger", json={"decisions": [], "approve": True}, headers=NAT).json()["detail"]["state"]
      == "council_ledger_not_applicable")
rr4 = client.post("/runs", json={"question": Q1, "entities": ["osr1", "wt1a"], "plan_id": P2}, headers=NAT)
RUN2 = rr4.json().get("run_id")
RCJ2 = json.loads(db.get_run(RUN2)["council_json"]) if RUN2 and db.get_run(RUN2).get("council_json") else None
check("POST /runs con consejo saltado -> 200; runs.council_json.r1_state 'skipped-by-human' y ledger vacío DECLARADO viajan a la corrida",
      rr4.status_code == 200 and rr4.json().get("plan_council_state") == "skipped-by-human"
      and isinstance(RCJ2, dict) and RCJ2["r1_state"] == "skipped-by-human" and RCJ2["ledger"]["decisions"] == [], rr4.text[:200])

# ---- 11. kill-switch WITT_COUNCIL=0 (L.2): sin job, sin puerta ---------------------------------------------------------------
os.environ["WITT_COUNCIL"] = "0"
rk0 = client.post("/runs/plan", json={"question": "¿pregunta bajo kill-switch?", "entities": []}, headers=NAT)
rr5 = client.post("/runs", json={"question": "¿tercera pregunta distinta?", "entities": [], "plan_id": P3}, headers=NAT)
os.environ["WITT_COUNCIL"] = "1"
check("WITT_COUNCIL=0: POST /runs/plan -> council.state 'disabled (kill-switch WITT_COUNCIL=0)' · gates.kill_switch.enabled false",
      rk0.status_code == 200 and rk0.json()["council"]["state"] == "disabled (kill-switch WITT_COUNCIL=0)"
      and rk0.json()["council"]["gates"]["kill_switch"]["enabled"] is False, rk0.json().get("council", {}).get("state"))
check("WITT_COUNCIL=0: POST /runs con un plan 'queued' sin aprobar -> 200 (la puerta del consejo NO existe bajo kill-switch) y la vista "
      "lo declara plan_council_state 'queued'",
      rr5.status_code == 200 and rr5.json().get("plan_council_state") == "queued", rr5.text[:200])
check("estado 'incomplete' también exige ledger (COUNCIL_LEDGER_STATES) y 'running' también bloquea (COUNCIL_PENDING_STATES)",
      app_mod.COUNCIL_LEDGER_STATES == ("applicable", "incomplete") and app_mod.COUNCIL_PENDING_STATES == ("queued", "running"))

# ---- 12. GET /council/membership (NO-SPEND, sin BD) -------------------------------------------------------------------------
check("GET /council/membership sin token -> 401", client.get("/council/membership").status_code == 401)
mm = client.get("/council/membership", headers=NAT)
MM = mm.json() if mm.status_code == 200 else {}
esperado = json.loads(json.dumps(agent_matrix.membership_view(os.environ), default=str))   # tuplas → listas (JSON)
check("GET /council/membership -> 200 == agent_matrix.membership_view(os.environ) en TODAS sus llaves (17 miembros, 8 not_applicable, "
      "9 substrate, rows_without_card 3, cards_without_row [] medido) + catalog_sha == catalog_cards.CATALOG_SHA",
      mm.status_code == 200 and all(MM.get(k) == v for k, v in esperado.items()) and len(MM.get("members", [])) == 17
      and len(MM.get("not_applicable", [])) == 8 and len(MM.get("substrate", [])) == 9 and len(MM.get("rows_without_card", [])) == 3
      and MM.get("cards_without_row") == [] and MM.get("catalog_sha") == catalog_cards.CATALOG_SHA,
      f"diff={[k for k, v in esperado.items() if MM.get(k) != v]}")
check("membership += rules_sha (catalog_cards.RULES_SHA) · shared_block_sha · cache {enabled, ttl, ttl_shared, min_cacheable_tokens 512} · "
      "council_module_state · vocabulary (dict)",
      MM.get("rules_sha") == catalog_cards.RULES_SHA and MM.get("shared_block_sha") == catalog_cards.SHARED_BLOCK_SHA
      and MM.get("cache", {}).get("min_cacheable_tokens") == 512 and MM["cache"]["enabled"] is True and MM["cache"]["ttl"] == "5m"
      and isinstance(MM.get("vocabulary"), dict) and "council_module_state" in MM)
voc = MM.get("vocabulary") or {}
if app_mod.council_mod is not None:
    exact = set(getattr(app_mod.council_mod, "COUNCIL_STATES_EXACT", ()))
    en_voc = getattr(app_mod.council_mod, "council_state_in_vocabulary", lambda s: False)
    check("vocabulario (C2): los literales que app emite ∈ council.COUNCIL_STATES_EXACT y los 'not-requested (…)' pasan "
          "council_state_in_vocabulary; membership.vocabulary == runs.council_vocabulary_full() (corrector: lib.council + "
          "competence_component_states + usage_stage_states — la MISMA función que frozen.council.vocabulary)",
          {"queued", "running", "applicable", "incomplete", app_mod.COUNCIL_STATE_SKIPPED, app_mod.COUNCIL_STATE_DISABLED,
           app_mod.COUNCIL_STATE_PRE_ADR} <= exact
          and en_voc(app_mod.COUNCIL_STATE_DB_UNAVAILABLE) and en_voc("not-requested (niches empty)")
          and voc == runs_mod.council_vocabulary_full() and "competence_component_states" in voc and "usage_stage_states" in voc
          and voc["competence_component_states"]["prefixes"] == ["incomplete (", "errored (", "not-applicable (", "vacuous ("],
          f"exact={sorted(exact)}")
else:
    check("vocabulario (C2): membership.vocabulary declara la ausencia del módulo (rojo declarado hasta C2: aquí se comparan "
          "los literales de app con council.COUNCIL_STATES_EXACT)", False, voc.get("state"))

# ---- 13. GET /council/search y /council/demand (C7) ---------------------------------------------------------------------------
check("GET /council/search sin q -> 400 · k=0 -> 400 (antes de cualquier índice)",
      client.get("/council/search", headers=NAT).status_code == 400
      and client.get("/council/search?q=osr1&k=0", headers=NAT).status_code == 400)
os.environ["WITT_COUNCIL_INDEX"] = "0"
r503 = client.get("/council/search?q=osr1", headers=NAT)
os.environ.pop("WITT_COUNCIL_INDEX", None)
check("WITT_COUNCIL_INDEX=0 -> 503 council-index-disabled {kill_switch 'WITT_COUNCIL_INDEX=0'}",
      r503.status_code == 503 and r503.json()["detail"]["state"] == "council-index-disabled"
      and r503.json()["detail"]["kill_switch"] == "WITT_COUNCIL_INDEX=0", r503.text[:200])
check("include_origins fuera del enum -> 400 invalid-origin (misma regla que /precedent/search)",
      client.get("/council/search?q=osr1&include_origins=marte", headers=NAT).status_code == 400)
rsq = client.get("/council/search?q=osr1%20pronephros&k=3", headers=NAT)
rdm = client.get("/council/demand", headers=NAT)
if app_mod.council_index_mod is not None:
    SQ = rsq.json() if rsq.status_code == 200 else {}
    check("GET /council/search (C7) -> 200 con el sobre de precedent.search: scorer, items[] (admissible_as_evidence false en TODOS), "
          "corpus_state ∈ indexed|empty-corpus, origins_included",
          rsq.status_code == 200 and "scorer" in SQ and all(i.get("admissible_as_evidence") is False for i in SQ.get("items", []))
          and SQ.get("corpus_state") in ("indexed", "empty-corpus") and "origins_included" in SQ, rsq.text[:300])
    check("kinds fuera del enum -> 400 invalid-kind",
          client.get("/council/search?q=osr1&kinds=poema", headers=NAT).status_code == 400)
    DM = rdm.json() if rdm.status_code == 200 else {}
    check("GET /council/demand (C7) -> 200 {n_runs_scanned, n_plans_scanned, n_requirements_unsatisfiable_by_family, threshold, fired, class}",
          rdm.status_code == 200 and {"n_runs_scanned", "n_plans_scanned", "n_requirements_unsatisfiable_by_family", "threshold", "fired",
                                       "class"} <= set(DM), rdm.text[:300])
    check("GET /council/demand (ADR-0084 F.3) += web_locator_provider_state {provider, provider_source, available, unavailable_reason}: bajo "
          "la máscara (BRAVE_API_KEY vacía, WITT_WEB_LOCATOR unset) provider 'off' derivado por ausencia de llave, available False y el "
          "literal byte-idéntico de 7d9ce15 'tool-unavailable (ADR-0084)' (== SEARCH_DISPATCH['web'].unavailable_reason); sin ruta nueva",
          rdm.status_code == 200 and os.environ.get("BRAVE_API_KEY", "") == "" and not os.environ.get("WITT_WEB_LOCATOR")
          and DM.get("web_locator_provider_state") == {"provider": "off", "provider_source": "default-derived:BRAVE_API_KEY absent",
                                                        "available": False, "unavailable_reason": "tool-unavailable (ADR-0084)"}
          and DM["web_locator_provider_state"]["unavailable_reason"] == search_harness.SEARCH_DISPATCH["web"]["unavailable_reason"],
          json.dumps(DM.get("web_locator_provider_state")))
    check("GET /council/demand (ADR-0084 F.3) — conteo ESTÁTICO y disponibilidad DINÁMICA lado a lado: n_requirements_unsatisfiable_by_family "
          "con EXACTAMENTE {figure, tooluniverse, web} (la web se cuenta aunque llegue la llave), unsatisfiable_families == ['tooluniverse', "
          "'web'] bajo off con unsatisfiable_families_source 'derived: SEARCH_DISPATCH fn None ∪ web_locator.provider_state not available', "
          "demand_families estáticas + demand_families_rule; provider_source es el literal declarado (sólo el NOMBRE de la variable viaja, "
          "jamás un valor: la máscara no tiene llave)",
          rdm.status_code == 200 and set(DM.get("n_requirements_unsatisfiable_by_family", {})) == {"figure", "tooluniverse", "web"}
          and DM.get("unsatisfiable_families") == ["tooluniverse", "web"]
          and DM.get("unsatisfiable_families_source") == "derived: SEARCH_DISPATCH fn None ∪ web_locator.provider_state not available"
          and DM.get("demand_families") == ["figure", "tooluniverse", "web"] and isinstance(DM.get("demand_families_rule"), str)
          and "ADR-0084" in DM.get("rule", "")
          and DM.get("web_locator_provider_state", {}).get("provider_source") == "default-derived:BRAVE_API_KEY absent",
          json.dumps({k: DM.get(k) for k in ("unsatisfiable_families", "unsatisfiable_families_source", "demand_families")}))
else:
    check("GET /council/search sin council_index -> 503 council-index-unavailable declarado (rojo declarado hasta C7: entonces 200 con el sobre)",
          False, f"{rsq.status_code} {rsq.json().get('detail', {}).get('state')}")
    check("GET /council/demand sin council_index -> 503 council-index-unavailable declarado (rojo declarado hasta C7)",
          False, f"{rdm.status_code} {rdm.json().get('detail', {}).get('state')}")
    check("(mientras C7 no aterriza) las dos puertas EXISTEN y responden 503 tipado, no 404 ni 500",
          rsq.status_code == 503 and rsq.json()["detail"]["state"] == "council-index-unavailable"
          and rdm.status_code == 503 and rdm.json()["detail"]["state"] == "council-index-unavailable")

# ---- 14. GET /usage.plans_council (H): rondas 1 de planes NUNCA corridos --------------------------------------------------------
_worker_a_mano(P_EMM, REQS[:1], usage={"in": 68000, "out": 20000, "cache_creation": 2400, "cache_read": 36000, "model": COUNCIL_MODEL})
U = client.get("/usage", headers=NAT).json()
PC = U.get("plans_council") or {}
n_planes_consejo = db.count_plans_council()
check("GET /usage.plans_council {state 'measured', n_plans (todos con council_state), n_unconsumed, n_consumed 3 (P1, P2, P3 corridos), "
      "input_tokens/output_tokens/cache SÓLO de los no consumidos con usage (P_EMM: 68000/20000, cache 2400/36000; P1 consumido NO suma), "
      "by_state, rule, class}",
      PC.get("state") == "measured" and PC.get("n_plans") == n_planes_consejo and PC.get("n_consumed") == 3
      and PC.get("n_unconsumed") == n_planes_consejo - 3 and PC.get("n_unconsumed_with_usage") == 1
      and PC.get("input_tokens") == 68000 and PC.get("output_tokens") == 20000
      and PC.get("cache", {}).get("creation_input_tokens") == 2400 and PC["cache"]["read_input_tokens"] == 36000
      and PC.get("by_state", {}).get("applicable") == 2 and PC["by_state"].get("skipped-by-human") == 1
      and PC["by_state"].get("queued") == 1 and PC["by_state"].get("disabled (kill-switch WITT_COUNCIL=0)") == 1
      and PC.get("rule") == app_mod.PLANS_COUNCIL_RULE, f"{ {k: PC.get(k) for k in ('state', 'n_plans', 'n_unconsumed', 'n_consumed', 'input_tokens', 'cache', 'by_state')} }")
check(f"plans_council.by_model[{COUNCIL_MODEL}] con in/out/cache_creation/cache_read y USD [E] por precios de la tabla + "
      "models.CACHE_MULTIPLIERS (cache.priced True, multipliers declarados; price_state 'priced')",
      PC.get("by_model", {}).get(COUNCIL_MODEL, {}).get("in") == 68000 and PC["by_model"][COUNCIL_MODEL]["cache_read"] == 36000
      and isinstance(PC["by_model"][COUNCIL_MODEL]["estimated_cost_usd"], float)
      and PC["by_model"][COUNCIL_MODEL]["price_state"] == "priced"
      and PC["cache"]["priced"] is True and PC["cache"]["multipliers"] == {"write_5m": models.CACHE_MULTIPLIERS["write_5m"],
                                                                          "read": models.CACHE_MULTIPLIERS["read"]}
      and PC.get("estimated_cost_usd") == PC["by_model"][COUNCIL_MODEL]["estimated_cost_usd"] and PC.get("price_state") == "priced",
      f"{PC.get('by_model')} cache={PC.get('cache')}")
check("totals de /usage sigue siendo la suma de usage_json por CORRIDA (las 3 corridas de este gate no tienen usage → 0) — plans_council va APARTE",
      U.get("totals") == {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0, "estimated_cost_usd": 0.0}
      and U.get("n_runs_with_usage") == 0, f"{U.get('totals')}")

# ---- 16. corrector ADR-0082 (F5 / F6 / F9 / F10 / F11 / F20): carreras y estados que los revisores midieron ------------------------
import threading as _th  # noqa: E402
import time as _time  # noqa: E402
import council_jobs as _cj_http  # noqa: E402
_council = app_mod.council_mod
LE = f"/plans/{P_EMM}/council/ledger"
# (a) F10: un BORRADOR guardado DESPUÉS de una aprobación limpia approved_by/at en el MISMO UPDATE
ra1 = client.post(LE, json={"decisions": [{"requirement_id": "req-a1b2c3d4e5f6", "decision": "keep"}], "approve": True}, headers=EMM)
pv_ap = client.get(f"/plans/{P_EMM}", headers=EMM).json()
rd1 = client.post(LE, json={"decisions": [], "approve": False}, headers=EMM)
pv_dr = client.get(f"/plans/{P_EMM}", headers=EMM).json()
check("16a corrector (F.1): approve → GET approved_by 'emmanuel' + run_gate allowed; luego un BORRADOR (approve false) → ledger.state "
      "'draft', approved_by null, approved_at null, run_gate council_ledger_unapproved — UNA verdad (antes la columna conservaba al "
      "aprobador anterior junto a ledger 'draft')",
      ra1.status_code == 200 and pv_ap["approved_by"] == "emmanuel" and pv_ap["run_gate"]["allowed"] is True
      and rd1.status_code == 200 and rd1.json()["ledger"]["state"] == "draft"
      and pv_dr["ledger"]["state"] == "draft" and pv_dr["approved_by"] is None and pv_dr["approved_at"] is None
      and pv_dr["run_gate"]["allowed"] is False and pv_dr["run_gate"]["reason"] == "council_ledger_unapproved",
      f"{ {k: pv_dr.get(k) for k in ('approved_by', 'approved_at', 'run_gate')} }")

# (b) F5: dos POST /runs/plan idénticos CONCURRENTES (ambos dentro del planner a la vez) → UN solo job queued
Q_CC = "¿lhx1a es necesario para el pronefros? (concurrente)"
_bar = _th.Barrier(2, timeout=15)
_cc_calls = []
_cc_before = db.count_plans_council(user_id="emmanuel", states=("queued",))


def _planner_cc(question, entities, thread_context=None):
    _cc_calls.append(question)
    idx = len(_cc_calls)
    _bar.wait()          # los DOS requests están DENTRO del planner: ninguno ha insertado su fila (la 1ª consulta del dedup no vio nada)
    if idx == 2:         # el 2º espera a que el 1º inserte: la carrera se resuelve en la re-consulta POSTERIOR al planner
        for _ in range(500):
            if db.count_plans_council(user_id="emmanuel", states=("queued",)) > _cc_before:
                break
            _time.sleep(0.01)
    return _planner()(question, entities)


runs_mod._default_planner = _planner_cc
_cc_res = [None, None]


def _post_cc(i):
    _cc_res[i] = client.post("/runs/plan", json={"question": Q_CC, "entities": ["lhx1a"]}, headers=EMM)


_cc_threads = [_th.Thread(target=_post_cc, args=(i,)) for i in range(2)]
for t_ in _cc_threads:
    t_.start()
for t_ in _cc_threads:
    t_.join(30)
runs_mod._default_planner = _planner()
_cc_json = [r_.json() if r_ is not None and r_.status_code == 200 else {} for r_ in _cc_res]
_cc_created = [j for j in _cc_json if j.get("plan_response") == "created"]
_cc_reused = [j for j in _cc_json if j.get("plan_response") == "reused"]
check("16b corrector (E.3): dos POST /runs/plan IDÉNTICOS concurrentes (barrera: ambos dentro del planner) → el planner se llamó 2 veces "
      "(gasto declarado) pero se creó UN solo plan 'queued': 1 'created' + 1 'reused' con el MISMO plan_id, reused_after_planner True y "
      "reused_reason 'concurrent request … already spent'; la cola del usuario creció exactamente en 1",
      all(r_ is not None and r_.status_code == 200 for r_ in _cc_res) and len(_cc_calls) == 2
      and len(_cc_created) == 1 and len(_cc_reused) == 1 and _cc_reused[0]["plan_id"] == _cc_created[0]["plan_id"]
      and _cc_reused[0]["reused_from_plan_id"] == _cc_created[0]["plan_id"] and _cc_reused[0]["reused_after_planner"] is True
      and "concurrent request" in _cc_reused[0]["reused_reason"] and "already spent" in _cc_reused[0]["reused_reason"]
      and _cc_created[0]["council"]["state"] == "queued" and _cc_created[0].get("reused_after_planner") is None
      and db.count_plans_council(user_id="emmanuel", states=("queued",)) == _cc_before + 1,
      json.dumps({"calls": len(_cc_calls), "responses": [j.get("plan_response") for j in _cc_json],
                  "reason": (_cc_reused[0].get("reused_reason") if _cc_reused else None)}))

# (c) F9: dos POST /runs con el MISMO plan_id — el sello lo gana otro: la corrida perdedora se cancela con razón y 409 con el ganador
ra2 = client.post(LE, json={"decisions": [{"requirement_id": "req-a1b2c3d4e5f6", "decision": "keep"}], "approve": True}, headers=EMM)
_real_mpu = db.mark_plan_used
_mpu_calls = []


def _mpu_false_once(plan_id, run_id):
    _mpu_calls.append(run_id)
    return False if len(_mpu_calls) == 1 else _real_mpu(plan_id, run_id)   # simula que OTRA corrida selló el plan en medio


db.mark_plan_used = _mpu_false_once
try:
    rr_race = client.post("/runs", json={"question": Q1, "entities": ["osr1"], "plan_id": P_EMM}, headers=EMM)
finally:
    db.mark_plan_used = _real_mpu
_race_det = rr_race.json().get("detail", {}) if rr_race.status_code == 409 else {}
_race_run = db.get_run(_race_det.get("cancelled_run_id")) if _race_det.get("cancelled_run_id") else None
check("16c corrector (F.3): mark_plan_used devuelve False (otra corrida selló el plan entre la lectura y el UPDATE) → 409 "
      "plan_already_used {plan_id, run_id (ganador), cancelled_run_id}; la corrida recién encolada queda 'cancelled' por 'server' con "
      "razón 'plan_already_used race' (traza de la carrera, no se borra); el plan sigue sin sello (nadie lo consumió en la simulación)",
      ra2.status_code == 200 and rr_race.status_code == 409 and _race_det.get("state") == "plan_already_used"
      and _race_det.get("plan_id") == P_EMM and _race_det.get("cancelled_run_id") and len(_mpu_calls) == 1
      and _race_run is not None and _race_run["state"] == "cancelled" and _race_run["cancelled_by"] == "server"
      and "plan_already_used race" in (_race_run.get("cancel_reason") or "")
      and db.get_plan(P_EMM)["run_id"] is None,
      f"{rr_race.status_code} {_race_det} run_state={_race_run and _race_run['state']}")

# (d) F11: BD SIN migrar (simulada por council_schema_state) → create_plan/create_run OMITEN las columnas E.1 en vez de fallar
_real_css = db.council_schema_state
db.council_schema_state = lambda: {"plans_missing": list(db.PLAN_COUNCIL_COLUMNS), "runs_missing": list(db.RUN_COUNCIL_COLUMNS),
                                   "plan_events_table": False, "ready": False}
db._COUNCIL_SCHEMA_READY.update(plans=False, runs=False)
try:
    db.create_plan("p-nomig", "emmanuel", "¿sin migrar?", ["osr1"], json.dumps({"entities": ["osr1"]}), origin="smoke",
                   council_state="queued")
    _nomig_run_no = db.create_run("r-nomig", "emmanuel", "¿sin migrar?", ["osr1"], thread_id="r-nomig", turn_no=1, turn_kind="root",
                                  origin="smoke", council_json=json.dumps({"plan_id": "p-nomig"}))
    _nomig_err = None
except Exception as e:  # noqa: BLE001
    _nomig_err = f"{type(e).__name__}: {e}"
finally:
    db.council_schema_state = _real_css
    db._COUNCIL_SCHEMA_READY.update(plans=False, runs=False)
_nomig_plan = db.get_plan("p-nomig") or {}
_nomig_run = db.get_run("r-nomig") or {}
check("16d corrector (E.1/LG8): con la superficie E.1 AUSENTE (council_schema_state simulado, caché reseteada) create_plan(origin=, "
      "council_state=) y create_run(council_json=) NO fallan — las columnas del consejo se OMITEN del INSERT (quedan NULL aquí; "
      "ausentes en una BD real) — y los lectores declaran: council_state_of(fila sin columna) → None, app._plan_council_state → "
      "'not-requested (council db unavailable)' (antes: 500 y estado inalcanzable); el estado se sirve, no se oculta",
      _nomig_err is None and _nomig_plan.get("plan_id") == "p-nomig" and _nomig_plan.get("origin") is None
      and _nomig_plan.get("council_state") is None and _nomig_run.get("run_id") == "r-nomig" and _nomig_run.get("council_json") is None
      and db.council_state_of({"plan_id": "x"}) is None
      and app_mod._plan_council_state({"plan_id": "x"}) == app_mod.COUNCIL_STATE_DB_UNAVAILABLE
      and _council.council_state_in_vocabulary(app_mod.COUNCIL_STATE_DB_UNAVAILABLE), f"err={_nomig_err}")

# (e) F20: el job REAL (council_jobs.execute_round1 con caller fake) sobre un plan encolado — las FORMAS que el fixture debe copiar
P_SHAPE = "p-shape-real"
db.create_plan(P_SHAPE, "natalia", "¿forma real de la traza del plan?", ["osr1"],
               json.dumps({"entities": ["osr1"], "judgment": {"work_type": "QA", "route": "evidence-run", "niches": ["N3"], "state": "declared"}}),
               origin="smoke", council_state="queued")
_shape_row = db.claim_next_council_plan("smoke:shape:council-worker-0", origins=("smoke",), plan_id=P_SHAPE)


def _fake_r1_shape(req):
    usage = {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 2400}
    meta = {"model_reported": COUNCIL_MODEL, "attempts": 1, "stop_reason": "tool_use", "api": "fake"}
    if req["tool"] == _council.FLAGS_TOOL_NAME:
        return {"applicable": True, "flags": []}, usage, meta
    return {"applicable": True, "requirements": [{"gap": f"{req['agent']} needs", "evidence_kind": "paper", "source_family": "europepmc",
                                                   "query_en": f"osr1 pronephros {req['agent']}", "entities": ["osr1"],
                                                   "acceptance_test": ">=1 paper", "priority": "should"}]}, usage, meta


_shape_res = _cj_http.execute_round1(_shape_row, caller=_fake_r1_shape, cfg=_council.config(os.environ, member_timeout_s=5, budget_s=30),
                                     resolver=lambda e: None, prior={"state": "empty-corpus", "items": [], "n": 0, "kinds": []})
_shape_ev = db.plan_events_after(P_SHAPE)
_shape_types = [e["type"] for e in _shape_ev]
_shape_done = [e["payload"] for e in _shape_ev if e["type"] == "stage.council.member" and e["payload"]["phase"] == "done"]
_shape_start = [e["payload"] for e in _shape_ev if e["type"] == "stage.council.member" and e["payload"]["phase"] == "start"]
_shape_agg = next(e["payload"] for e in _shape_ev if e["type"] == "stage.council.aggregate")
_shape_round = next(e["payload"] for e in _shape_ev if e["type"] == "stage.council.round")
_mano_ev = client.get(f"/plans/{P1}/events", headers=NAT).json()["events"]
_mano_done = next(e["payload"] for e in _mano_ev if e["type"] == "stage.council.member")
_mano_agg = next(e["payload"] for e in _mano_ev if e["type"] == "stage.council.aggregate")
check("16e corrector (F20): el job REAL deja en plan_events council.state{running} → stage.council.member start ×17 + done ×17 (llaves ⊇ "
      "{round, agent, tool, phase, status, error_kind, elapsed_s, attempts, attempt, max_attempts, cache_read, heartbeat}) → "
      "stage.council.round {phase 'plan', quorum {required, n_eligible 17, …}} → stage.council.aggregate (15 llaves) → council.state "
      "{applicable}; los payloads del worker A MANO de este smoke tienen las MISMAS llaves (member done y aggregate ⊆ reales) — el fixture "
      "plan-eventos-consejo.json debe nacer de execute_round1, no de la receta a mano",
      _shape_res["state"] == "applicable" and _shape_res["state_written"] is True and _shape_types[0] == "council.state"
      and len(_shape_done) == 17 and len(_shape_start) == 17
      and all({"round", "agent", "tool", "phase", "status", "error_kind", "elapsed_s", "attempts", "attempt", "max_attempts",
               "cache_read", "heartbeat"} <= set(p) for p in _shape_done)
      and all({"round", "agent", "tool", "phase", "attempt", "max_attempts", "heartbeat"} <= set(p) for p in _shape_start)
      and _shape_round["phase"] == "plan" and _shape_round["quorum"]["n_eligible"] == 17 and _shape_round["quorum"]["required"] == 11
      and set(_shape_agg) >= {"n_raw", "n_dedup", "n_requirements", "n_must", "n_should", "n_truncated", "n_unsatisfiable",
                              "n_hard_rule", "n_flags", "n_valid", "n_members", "catalog_sha", "aggregation_sha", "state", "decided_by"}
      and _shape_types[-1] == "council.state" and _shape_ev[-1]["payload"]["state"] == "applicable"
      and set(_mano_done) <= set(_shape_done[0]) and set(_mano_agg) <= set(_shape_agg),
      json.dumps({"types": sorted(set(_shape_types)), "mano_missing_in_real": sorted(set(_mano_done) - set(_shape_done[0])),
                  "agg_missing": sorted(set(_mano_agg) - set(_shape_agg))}))

# ---- 15. sin colisión de rutas + 401 en las 8 puertas + cero red --------------------------------------------------------------------
check("/plans/{id} NO captura /runs/{run_id} ni al revés: GET /runs/<plan_id> -> 404 'no such run'; GET /plans/<run_id> -> 404 plan_not_found;"
      " POST /runs/plan sigue vivo",
      client.get(f"/runs/{P1}", headers=NAT).status_code == 404 and client.get(f"/runs/{P1}", headers=NAT).json()["detail"] == "no such run"
      and client.get(f"/plans/{RUN1}", headers=NAT).status_code == 404
      and client.get(f"/plans/{RUN1}", headers=NAT).json()["detail"]["state"] == "plan_not_found"
      and client.post("/runs/plan", json={"question": "¿viva?", "entities": []}, headers=NAT).status_code == 200)
sin_token = [("GET", f"/plans/{P1}"), ("GET", f"/plans/{P1}/events"), ("GET", f"/plans/{P1}/stream"),
             ("POST", f"/plans/{P1}/council/ledger"), ("POST", f"/plans/{P1}/council/skip"),
             ("GET", "/council/membership"), ("GET", "/council/search?q=x"), ("GET", "/council/demand")]
codigos = [client.request(m, u, json={} if m == "POST" else None).status_code for m, u in sin_token]
check("autorización DECLARADA y MEDIDA: las 8 rutas nuevas -> 401 sin sesión", codigos == [401] * 8, f"{codigos}")
check("cero red: urllib.request.urlopen bloqueado y contado == 0", len(_URLOPEN_CALLS) == 0, f"{_URLOPEN_CALLS}")

_fin()
