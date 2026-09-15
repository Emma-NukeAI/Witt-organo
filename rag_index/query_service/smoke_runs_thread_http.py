"""
smoke_runs_thread_http.py — gate HTTP de la INVESTIGACIÓN (ADR-0079, rebanada T3 · app.py): una
investigación T-<run_no raíz> es una cadena de turnos (corridas con parent_run_id) leída como UNA unidad.

Fija lo que la PUERTA hace cumplir, sobre el stack completo vía ASGI TestClient (lección ADR-0075: el
gate VE los campos por el mismo camino que la webapp):
  · padre inexistente = 404 parent_not_found · padre queued/running = 409 parent_not_terminal
  · la raíz nace thread_id = run_id, turn_no 1, turn_kind 'root'; el hijo turn_no 2 'refine'; misma
    pregunta+entidades = 'rerun'; segundo hijo del mismo padre = 'branch'; nieto hereda thread_id
  · lista y detalle sirven las MISMAS columnas de investigación (misma-vista, ADR-0055/0076); el blob
    thread_context_json JAMÁS viaja por renglón
  · corridas anteriores al contrato: NULL en todo (ausencia declarada, sin backfill); un padre pre-ADR
    se lee como raíz VIRTUAL en GET /threads (derivación al servir, no escritura)
  · el snapshot del padre (thread_context, armado en el servidor) NO lleva valores ni notas de
    calificación (enmascaramiento M5) y trunca los comentarios al tope declarando truncated:true
  · GET /threads/{id}: gap_flags_union deduplicado por igualdad normalizada, costo sumado y ETIQUETADO
    (proyección; incompleto si un turno no tiene usage), pivot_suggested con turnos planos, orígenes
  · GET /runs?thread=&limit=&after= pagina por turn_no; `after` sin thread = 400
  · origin 'smoke' en la vista (WITT_RUN_ORIGIN=smoke); include_origins en /precedent/search,
    /calibration y /notes/questions/calibration (default = producción; smoke se pide explícito; fuera
    del enum = 400)
  · padre con identidad inválida (question_matches_run false) -> el hijo se crea, thread_context null
    con skipped_reason 'parent-identity-invalid'; padre failed sin registro -> previous_answer /
    previous_audit null-declarados
  · POST /runs/plan con parent_run_id: el planner recibe el snapshot (thread_context_passed)
  · ADR-0081 (G) GET /threads?mine=&limit=&after= — el ÍNDICE de investigaciones: 401/200/400/422, sobre exacto,
    `label`/`root_run_no`/`n_turns` IGUALES a GET /threads/{id} (misma verdad por dos puertas), raíz virtual
    (+1, root_counted false), orden root_run_no DESC, paginación con cursor exclusivo y has_more medido, tope
    declarado, `mine`, n_threads_total y n_runs_without_thread del SERVIDOR, costs 'not-aggregated'
  · ADR-0081 (F) `root_run_no` en la VISTA (POST /runs, lista, detalle): raíz == run_no, hijo == run_no de la
    raíz, hijo de raíz virtual == run_no del padre pre-ADR, corrida pre-ADR null DECLARADO

Lo que NO cubre (vive en smoke_run_pipeline.py, el integrador): frozen.thread / thread_context /
precedent_citations / episode_axes / origin al CONGELAR, el kill-switch WITT_THREAD_CONTEXT=0 y la
fuga de identificadores del padre — aquí no corre el pipeline (sin workers: TestClient sin lifespan).

PREFLIGHT: las primeras comprobaciones declaran si las interfaces de T1 (db) / T2 (runs) / T4
(precedent, calibration) ya existen. Si falta alguna, el gate se detiene ahí y lo dice — jamás
rellena con un stub lo que el stack todavía no tiene.

NO-SPEND: sin red, sin modelo (el planner falla rápido sin API key -> judgment errored, §6 no-hang).
BD sqlite temporal fuera del repo.
Uso (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-t3.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_runs_thread_http.py
(si WITT_BACKEND_DB_URL no viene, se fija a ese archivo; el archivo previo se borra al arrancar.)
"""
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
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{(SMOKES_DIR / 'smoke-t3.db').as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()   # BD fresca por corrida: el gate no hereda estado
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"          # ADR-0079 (F): la procedencia de TODA corrida de este gate
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"      # dev sparse siempre está OFFLINE (LOTE-01·A5 override)
os.environ["WITT_THREAD_COMMENTS_MAX"] = "3"     # tope chico para medir el truncado sin 9 comentarios
os.environ["WITT_PIVOT_TURNS"] = "3"

import db  # noqa: E402
import app as app_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
import precedent as precedent_mod  # noqa: E402
import calibration as calibration_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _fin():
    n_pass = sum(CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} PASS")
    sys.exit(0 if n_pass == len(CHECKS) else 1)


def _acepta(fn, *kws):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return all(k in params for k in kws)


# ---- PREFLIGHT: las interfaces de las otras rebanadas, DECLARADAS ------------------------------------
THREAD_COLS = ("parent_run_id", "thread_id", "turn_no", "turn_kind", "thread_context_json", "origin",
               "root_question_id")
check("T1 · db: las siete columnas de investigación existen en la tabla runs",
      all(c in db.runs.c for c in THREAD_COLS))
check("T1 · db.list_runs acepta thread_id/after y db.thread_turns existe",
      _acepta(db.list_runs, "thread_id", "after") and callable(getattr(db, "thread_turns", None)))
check("T1 · db.RUN_ORIGINS (enum) y db.question_calibration(include_origins)",
      isinstance(getattr(db, "RUN_ORIGINS", None), tuple) and _acepta(db.question_calibration, "include_origins"))
check("T2 · runs.new_run acepta parent_run_id y from_question_id (deriva en el servidor)",
      _acepta(runs_mod.new_run, "parent_run_id", "from_question_id"))
check("T2 · runs.plan_thread_context(parent_run_id) -> sobre {snapshot, skipped_reason}; build_plan(thread_context); ThreadError",
      callable(getattr(runs_mod, "plan_thread_context", None)) and _acepta(runs_mod.build_plan, "thread_context")
      and isinstance(getattr(runs_mod, "ThreadError", None), type))
check("T4 · precedent.search / calibration.report aceptan include_origins",
      _acepta(precedent_mod.search, "include_origins") and _acepta(calibration_mod.report, "include_origins"))
if not all(CHECKS):
    print("\nPREFLIGHT INCOMPLETO: falta(n) interfaz(ces) de otra rebanada — el resto del gate no puede "
          "correr sobre el stack real y NO se simula (ADR-0079: lo ausente se declara).")
    _fin()
# ADR-0081 (S4) · S7: las interfaces del índice de investigaciones son dependencia DURA (S4 aterrizó): se MIDEN aquí y
# la sección 13 las da por hechas — se retiraron las ramas "S4 pendiente" de la obra (nada se simula con un stub).
check("ADR-0081 · S4: db.threads_index(user_id, limit, after) y db.count_runs_without_thread existen (dependencia dura)",
      callable(getattr(db, "threads_index", None)) and callable(getattr(db, "count_runs_without_thread", None)))

# ---- datos --------------------------------------------------------------------------------------------
db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")

client = TestClient(app_mod.app)   # sin lifespan: sin workers — las corridas quedan queued a propósito


def sesion(u, pw):
    r = client.post("/login", json={"username": u, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


NAT = sesion("natalia", "pw-natalia")
EMM = sesion("emmanuel", "pw-emmanuel")

GAPS = ["Falta dato de dosis", "Sin réplica biológica"]


def congelar(run_id, gaps, cost=0.01, verdict="APPROVE", state="closed", identidad=True,
             direct_answer="wt1a marca el pronefros (evidencia [1])."):
    """Simula el freeze del pipeline (sin correrlo): registro congelado + resumen epistémico + usage,
    como smoke_precedent._mk_run. La pregunta la toma de la fila para que question_matches_run sea real."""
    fila = db.get_run(run_id)
    frozen = {"render_contract_version": runs_mod.RENDER_CONTRACT_VERSION,
              "run_id": run_id, "question": fila["question"],
              "answer": {"direct_answer": direct_answer, "stated_confidence": 0.7,
                         "absence_kind": "not-applicable", "gap_flags": gaps},
              "audit": {"verdict": verdict, "n_valid": 4, "panel": []},
              "decision_state": {"state": "AUDIT_APPROVED"},
              "confidence": {"final": 0.7, "state": "value", "source": "stated", "by_subclaim": None},
              "citations": [], "question_matches_run": identidad}
    values = {"state": state,
              "frozen_record_json": json.dumps(frozen, ensure_ascii=False),
              "epistemic_summary_json": json.dumps({"retrieval_mode": "graph", "verdict": verdict,
                                                    "confidence_state": "value", "panel_n_valid": 4}),
              "usage_json": json.dumps({"input_tokens": 100, "output_tokens": 50,
                                        "estimated_cost_usd": cost, "cost_projection_complete": True})}
    if state == "closed":
        values.update(frozen_at=db._now(), closed_by=fila["user_id"])
    db.update_run(run_id, **values)


def crear(question, parent=None, entities=("wt1a",), headers=NAT, **extra):
    body = {"question": question, "entities": list(entities), **extra}
    if parent:
        body["parent_run_id"] = parent
    return client.post("/runs", json=body, headers=headers)


def snapshot_de(run_id):
    """La columna thread_context_json (lo que el modelo VERÁ), leída de la fila. Sobre esperado:
    {snapshot, skipped_reason} — el mismo de runs.plan_thread_context; si la columna trae el snapshot
    directo, se devuelve tal cual con skipped_reason None."""
    crudo = db.get_run(run_id).get("thread_context_json")
    if not crudo:
        return None, None
    d = json.loads(crudo)
    if isinstance(d, dict) and "snapshot" in d:
        return d.get("snapshot"), d.get("skipped_reason")
    return d, None


# ---- 1. auth y padre inexistente ---------------------------------------------------------------------
check("GET /threads sin token -> 401", client.get("/threads/x").status_code == 401)

r = crear("¿wt1a marca el pronefros?", parent="nope")
check("padre inexistente -> 404 parent_not_found",
      r.status_code == 404 and (r.json().get("detail") or {}).get("state") == "parent_not_found", r.text[:120])

# ---- 2. la raíz ------------------------------------------------------------------------------------
r = crear("¿wt1a marca el pronefros?")
check("POST /runs raíz -> 200", r.status_code == 200, r.text[:200])
raiz = r.json()
ROOT = raiz["run_id"]
check("raíz: thread_id = run_id, turn_no 1, turn_kind 'root', parent_run_id null",
      raiz.get("thread_id") == ROOT and raiz.get("turn_no") == 1 and raiz.get("turn_kind") == "root"
      and raiz.get("parent_run_id") is None,
      f"thread_id={raiz.get('thread_id')} turn_no={raiz.get('turn_no')} kind={raiz.get('turn_kind')}")
check("origin 'smoke' en la vista (WITT_RUN_ORIGIN=smoke, derivado en el servidor)",
      raiz.get("origin") == "smoke", f"origin={raiz.get('origin')!r}")
check("thread_context_json JAMÁS viaja en la vista", "thread_context_json" not in raiz)

# ---- 3. padre no terminal -----------------------------------------------------------------------------
r = crear("hijo prematuro", parent=ROOT)
check("padre queued -> 409 parent_not_terminal", r.status_code == 409
      and (r.json().get("detail") or {}).get("state") == "parent_not_terminal", r.text[:120])
db.update_run(ROOT, state="running")
r = crear("hijo prematuro", parent=ROOT)
check("padre running -> 409 parent_not_terminal (con parent_state declarado)", r.status_code == 409
      and (r.json().get("detail") or {}).get("parent_state") == "running", r.text[:120])

# ---- 4. el padre termina: registro, comentarios (5 > tope 3) y una calificación con nota -----------
congelar(ROOT, GAPS, cost=0.01)
for i in range(5):
    assert client.post(f"/runs/{ROOT}/comments", json={"body": f"comentario {i}"}, headers=NAT).status_code == 201
r = client.post(f"/runs/{ROOT}/ratings", headers=NAT,
                json={"rating_input": 4, "rating_output": 5, "note": "NOTA-SECRETA-M5", "note_question": ""})
assert r.status_code == 200, r.text

# ---- 5. hijos: refine, rerun, branch, nieto ------------------------------------------------------------
r = crear("¿wt1a marca el pronefros a 24 hpf?", parent=ROOT)
check("hijo (pregunta refinada) -> 200", r.status_code == 200, r.text[:200])
c1 = r.json()
C1 = c1["run_id"]
check("hijo: turn_no 2, turn_kind 'refine', thread_id = raíz, parent_run_id = raíz",
      c1.get("turn_no") == 2 and c1.get("turn_kind") == "refine" and c1.get("thread_id") == ROOT
      and c1.get("parent_run_id") == ROOT,
      f"turn_no={c1.get('turn_no')} kind={c1.get('turn_kind')} thread_id={c1.get('thread_id')}")

snap1, skip1 = snapshot_de(C1)
check("thread_context: snapshot armado en el servidor con el padre identificado",
      isinstance(snap1, dict) and (snap1.get("parent") or {}).get("run_id") == ROOT and skip1 is None,
      f"skipped_reason={skip1!r} keys={sorted(snap1.keys()) if isinstance(snap1, dict) else snap1}")
texto1 = json.dumps(snap1, ensure_ascii=False) if snap1 else ""
check("thread_context SIN valores ni notas de calificación (M5: se declara la exclusión, no se filtra)",
      "NOTA-SECRETA-M5" not in texto1 and "rating_output" not in texto1 and "rating_input" not in texto1
      and any("ratings" in str(e) for e in (snap1 or {}).get("excluded", [])),
      f"excluded={(snap1 or {}).get('excluded')}")
com = (snap1 or {}).get("human_comments") or {}
check("comentarios: 5 en el padre, 3 incluidos (tope WITT_THREAD_COMMENTS_MAX=3), truncated:true, clase 'atestiguada'",
      isinstance(com, dict) and len(com.get("items") or []) == 3 and com.get("n_total") == 5
      and com.get("truncated") is True and com.get("class") == "atestiguada",
      f"n_included={com.get('n_included')} n_total={com.get('n_total')} truncated={com.get('truncated')} class={com.get('class')}")

r = crear("¿wt1a marca el pronefros?", parent=ROOT)       # misma pregunta + mismas entidades que la raíz
c2 = r.json()
C2 = c2["run_id"]
check("misma pregunta+entidades que el padre -> turn_kind 'rerun', turn_no 3",
      r.status_code == 200 and c2.get("turn_kind") == "rerun" and c2.get("turn_no") == 3,
      f"kind={c2.get('turn_kind')} turn_no={c2.get('turn_no')}")

r = crear("¿wt1a y pax2a co-marcan el pronefros?", parent=ROOT, entities=("wt1a", "pax2a"), headers=EMM)
c3 = r.json()
C3 = c3["run_id"]
check("tercer hijo del mismo padre (pregunta nueva) -> turn_kind 'branch', turn_no 4",
      r.status_code == 200 and c3.get("turn_kind") == "branch" and c3.get("turn_no") == 4,
      f"kind={c3.get('turn_kind')} turn_no={c3.get('turn_no')}")

# los tres hijos terminan con el MISMO conjunto de gaps (variantes de mayúsculas/espacios) -> racha plana
congelar(C1, ["falta dato de dosis ", "SIN RÉPLICA BIOLÓGICA"], cost=0.02)
congelar(C2, GAPS, cost=0.03)
congelar(C3, ["Falta dato de dosis", "sin réplica biológica", "Falta dato de dosis"], cost=0.04)

r = crear("¿y a 48 hpf?", parent=C1)                      # nieto: hereda el thread de la raíz
c4 = r.json()
C4 = c4["run_id"]
check("nieto (padre = hijo): thread_id = raíz, turn_no 5 = max(hilo)+1, parent_run_id = hijo",
      r.status_code == 200 and c4.get("thread_id") == ROOT and c4.get("turn_no") == 5
      and c4.get("parent_run_id") == C1, f"thread_id={c4.get('thread_id')} turn_no={c4.get('turn_no')}")

# ---- 6. misma-vista: lista == detalle en las columnas nuevas; blob fuera --------------------------------
VIEW_COLS = ("parent_run_id", "thread_id", "turn_no", "turn_kind", "origin", "root_question_id")
lista = {row["run_id"]: row for row in client.get("/runs", headers=NAT).json()["runs"]}
det = client.get(f"/runs/{C1}", headers=NAT).json()
check("lista y detalle sirven las MISMAS columnas de investigación (misma-vista)",
      C1 in lista and all(k in lista[C1] and k in det and lista[C1][k] == det[k] for k in VIEW_COLS),
      f"lista={[lista.get(C1, {}).get(k) for k in VIEW_COLS]} det={[det.get(k) for k in VIEW_COLS]}")
check("el blob thread_context_json no viaja ni en la lista ni en el detalle",
      all("thread_context_json" not in v for v in lista.values()) and "thread_context_json" not in det)

# ---- 7. corridas anteriores al contrato: NULL declarado; padre pre-ADR = raíz virtual ------------------
db.create_run("old-run", "natalia", "¿pregunta anterior al contrato?")   # camino viejo: sin columnas
old = client.get("/runs/old-run", headers=NAT).json()
check("corrida pre-ADR: thread_id/turn_no/turn_kind/origin NULL en la vista (sin backfill)",
      all(old.get(k) is None for k in ("thread_id", "turn_no", "turn_kind", "origin", "parent_run_id")),
      f"{[old.get(k) for k in VIEW_COLS]}")
congelar("old-run", ["gap viejo"], cost=0.05)
r = crear("¿sigue la pregunta vieja?", parent="old-run")
h_old = r.json()
snap_old, _ = snapshot_de(h_old["run_id"])
check("hijo de padre pre-ADR: thread_id = run_id del padre (raíz virtual), turn_no 2, parent_pre_adr_0079 declarado",
      r.status_code == 200 and h_old.get("thread_id") == "old-run" and h_old.get("turn_no") == 2
      and (snap_old or {}).get("parent_pre_adr_0079") is True,
      f"thread_id={h_old.get('thread_id')} turn_no={h_old.get('turn_no')} flag={(snap_old or {}).get('parent_pre_adr_0079')}")
t_old = client.get("/threads/old-run", headers=NAT)
check("GET /threads/{padre pre-ADR}: 200, root_pre_adr_0079 true, el padre entra como raíz virtual + su hijo",
      t_old.status_code == 200 and t_old.json().get("root_pre_adr_0079") is True
      and t_old.json().get("n_turns") == 2 and t_old.json()["turns"][0]["run_id"] == "old-run"
      and t_old.json()["turns"][0].get("turn_no") is None, t_old.text[:200])

# ---- 8. GET /threads/{raíz}: agregados deterministas ---------------------------------------------------
check("GET /threads inexistente -> 404", client.get("/threads/nope", headers=NAT).status_code == 404)
t = client.get(f"/threads/{ROOT}", headers=NAT)
check("GET /threads/{raíz} -> 200", t.status_code == 200, t.text[:200])
T = t.json()
check("thread: 5 turnos, 4 cerrados, raíz con run_no y etiqueta T-<run_no>, autores ordenados",
      T.get("n_turns") == 5 and T.get("n_closed") == 4 and T.get("root_run_no") == raiz["run_no"]
      and T.get("label") == f"T-{raiz['run_no']}" and T.get("authors") == ["emmanuel", "natalia"],
      f"n_turns={T.get('n_turns')} n_closed={T.get('n_closed')} label={T.get('label')} authors={T.get('authors')}")
check("turnos en orden turn_no 1..5 con veredicto congelado y origin por turno",
      [x["turn_no"] for x in T["turns"]] == [1, 2, 3, 4, 5]
      and [x["verdict"] for x in T["turns"]] == ["APPROVE"] * 4 + [None]
      and all(x["origin"] == "smoke" for x in T["turns"]),
      f"{[(x['turn_no'], x['verdict']) for x in T['turns']]}")
gfu = T.get("gap_flags_union") or []
check("gap_flags_union: 2 entradas (igualdad lower/strip), count 4 cada una, last_turn 4, texto de la 1a aparición",
      len(gfu) == 2 and all(g["count"] == 4 and g["last_turn"] == 4 for g in gfu)
      and sorted(g["text"] for g in gfu) == sorted(GAPS), f"{gfu}")
tc = T.get("total_cost_usd") or {}
check("total_cost_usd: suma 0.10 ETIQUETADA proyección e INCOMPLETA (el nieto no tiene usage)",
      abs((tc.get("value") or 0) - 0.10) < 1e-9 and tc.get("complete") is False
      and tc.get("n_turns_without_usage") == 1 and "PROJECTION" in (tc.get("cost_class") or ""), f"{tc}")
check("turno con usage congelado trae estimated_cost_usd y cost_projection_complete; el nieto null",
      T["turns"][0]["estimated_cost_usd"] == 0.01 and T["turns"][0]["cost_projection_complete"] is True
      and T["turns"][4]["estimated_cost_usd"] is None)
pv = T.get("pivot_suggested") or {}
check("pivot_suggested: 3 turnos planos consecutivos -> true, regla y turnos considerados declarados",
      pv.get("value") is True and pv.get("turns_considered") == [2, 3, 4]
      and pv.get("rule") == app_mod.PIVOT_RULE and pv.get("threshold") == 3, f"{pv}")
check("origins: {'smoke': 5} (conteo por origen; la etiqueta del NULL viaja declarada)",
      T.get("origins") == {"smoke": 5} and T.get("origin_unknown_label") == "unknown-pre-adr-0079",
      f"{T.get('origins')}")

# pivot con racha rota: un turno nuevo cuyo conjunto se REDUJO -> false con razón
congelar(C4, ["Falta dato de dosis"], cost=0.01)
pv2 = client.get(f"/threads/{ROOT}", headers=NAT).json()["pivot_suggested"]
check("pivot_suggested: el último turno REDUJO los gaps -> false con razón declarada",
      pv2.get("value") is False and pv2.get("reason") == "gap_flags-reduced-within-window"
      and pv2.get("turns_considered") == [3, 4, 5], f"{pv2}")

# ---- 9. GET /runs?thread= paginado por turn_no --------------------------------------------------------
p1 = client.get(f"/runs?thread={ROOT}&limit=2", headers=NAT).json()
check("GET /runs?thread=&limit=2: 2 turnos (1,2), has_more true, next_after 2",
      [x["turn_no"] for x in p1["runs"]] == [1, 2] and p1.get("has_more") is True and p1.get("next_after") == 2,
      f"turnos={[x.get('turn_no') for x in p1['runs']]} has_more={p1.get('has_more')} next_after={p1.get('next_after')}")
p2 = client.get(f"/runs?thread={ROOT}&after=2", headers=NAT).json()
check("GET /runs?thread=&after=2: turnos 3,4,5 sin tope, has_more false",
      [x["turn_no"] for x in p2["runs"]] == [3, 4, 5] and p2.get("has_more") is False
      and p2.get("next_after") is None, f"turnos={[x.get('turn_no') for x in p2['runs']]}")
check("GET /runs?after= sin thread -> 400 (el cursor de turno no aplica a la lista general)",
      client.get("/runs?after=1", headers=NAT).status_code == 400)
check("la lista general declara su tope (limit_cap 50) y sigue sirviendo n_comments",
      client.get("/runs", headers=NAT).json().get("limit_cap") == 50
      and lista[ROOT].get("n_comments") == 5)
check("corrector: GET /runs?limit=-1 -> 400 (antes: LIMIT -1 = sin tope en SQLite / 500 en Postgres); GET /runs?limit=500 -> "
      "limit 50 (el tope manda y se declara); GET /runs?thread=&limit=0 -> 400",
      client.get("/runs?limit=-1", headers=NAT).status_code == 400
      and client.get("/runs?limit=500", headers=NAT).json().get("limit") == 50
      and client.get(f"/runs?thread={ROOT}&limit=0", headers=NAT).status_code == 400)
_prev_pt = os.environ.get("WITT_PIVOT_TURNS")
os.environ["WITT_PIVOT_TURNS"] = ""
_pt_empty = runs_mod._env_int_tolerante("WITT_PIVOT_TURNS", app_mod.PIVOT_TURNS_DEFAULT)
os.environ["WITT_PIVOT_TURNS"] = "abc"
_pt_abc = runs_mod._env_int_tolerante("WITT_PIVOT_TURNS", app_mod.PIVOT_TURNS_DEFAULT)
os.environ["WITT_PIVOT_TURNS"] = _prev_pt if _prev_pt is not None else "3"
check("corrector: WITT_PIVOT_TURNS se lee TOLERANTE (runs._env_int_tolerante, patrón ADR-0078): '' y 'abc' -> 3 con fuente "
      "declarada (default-unset / default-invalid-env), jamás un int() que tumbe el import; GET /threads declara "
      "pivot_suggested.threshold_source",
      _pt_empty == (3, "default-unset:WITT_PIVOT_TURNS") and _pt_abc == (3, "default-invalid-env:WITT_PIVOT_TURNS")
      and pv.get("threshold_source") == app_mod.PIVOT_TURNS_SOURCE == "env:WITT_PIVOT_TURNS", f"{_pt_empty} {_pt_abc}")

# ---- 10. include_origins: precedente, calibración, tablero del agente ---------------------------------
ps = client.get("/precedent/search?q=pregunta+anterior+contrato", headers=NAT).json()
check("/precedent/search default: las 5 'smoke' cerradas NO son precedente y se CUENTAN; la pre-ADR (origin NULL) SÍ entra y se declara",
      [i["run_id"] for i in (ps.get("items") or [])] == ["old-run"]
      and (ps.get("excluded_by_origin") or {}).get("smoke") == 5
      and ps.get("origins_included") == ["production"] and ps.get("origin_unknown_included") == 1,
      f"items={[i.get('run_id') for i in (ps.get('items') or [])]} origins_included={ps.get('origins_included')} "
      f"excluded={ps.get('excluded_by_origin')} unknown_included={ps.get('origin_unknown_included')}")
ps2 = client.get("/precedent/search?q=wt1a+pronefros&include_origins=smoke", headers=NAT).json()
check("/precedent/search?include_origins=smoke: entran, origins_included ['smoke'], admissible false",
      len(ps2.get("items") or []) >= 1 and ps2.get("origins_included") == ["smoke"]
      and all(i.get("admissible_as_evidence") is False for i in ps2["items"]),
      f"n={len(ps2.get('items') or [])} origins_included={ps2.get('origins_included')}")
check("include_origins fuera del enum -> 400 con la lista permitida",
      client.get("/precedent/search?q=x&include_origins=bogus", headers=NAT).status_code == 400
      and "allowed" in client.get("/precedent/search?q=x&include_origins=bogus", headers=NAT).text)
cal = client.get("/calibration", headers=NAT).json()
cal2 = client.get("/calibration?include_origins=smoke,production", headers=NAT).json()
check("/calibration: default n_closed 1 (sólo la pre-ADR NULL, declarada) y 5 'smoke' contadas fuera; con include_origins=smoke,production n_closed 6",
      cal.get("n_closed") == 1 and (cal.get("excluded_by_origin") or {}).get("smoke") == 5
      and cal.get("origin_unknown_included") == 1
      and cal2.get("n_closed") == 6 and cal2.get("origins_included") == ["production", "smoke"],
      f"default n_closed={cal.get('n_closed')} excl={cal.get('excluded_by_origin')} unknown={cal.get('origin_unknown_included')} "
      f"| con smoke n_closed={cal2.get('n_closed')} origins_included={cal2.get('origins_included')}")
qc = client.get("/notes/questions/calibration?include_origins=smoke", headers=NAT)
check("/notes/questions/calibration?include_origins=smoke -> 200 y declara el alcance por origen",
      qc.status_code == 200 and qc.json().get("origins_included") == ["smoke"],
      qc.text[:160])
qc0 = client.get("/notes/questions/calibration", headers=NAT).json()
check("corrector: /notes/questions/calibration SIN parámetro aplica el MISMO default que precedente/calibración: "
      "origins_included ['production'] (antes: null = sin filtro)",
      qc0.get("origins_included") == ["production"] and isinstance(qc0.get("excluded_by_origin"), dict),
      f"origins_included={qc0.get('origins_included')}")

# ---- 11. identidad inválida y padre sin registro ------------------------------------------------------
r = crear("¿pregunta con identidad rota?")
BAD = r.json()["run_id"]
congelar(BAD, ["x"], identidad=False)
r = crear("¿sigo sobre la rota?", parent=BAD)
snap_bad, skip_bad = snapshot_de(r.json().get("run_id", ""))
check("padre con question_matches_run=false: el hijo SÍ se crea, thread_context null, skipped_reason 'parent-identity-invalid'",
      r.status_code == 200 and snap_bad is None and skip_bad == "parent-identity-invalid",
      f"status={r.status_code} snapshot={snap_bad} skipped_reason={skip_bad!r}")

r = crear("¿pregunta que falló?")
DEAD = r.json()["run_id"]
db.update_run(DEAD, state="failed", error="pipeline: boom (smoke)")
r = crear("¿retomo la que falló?", parent=DEAD)
snap_dead, _ = snapshot_de(r.json().get("run_id", ""))
check("padre failed sin registro: hijo creado; previous_answer y previous_audit null-declarados con razón",
      r.status_code == 200 and isinstance(snap_dead, dict) and snap_dead.get("previous_answer") is None
      and snap_dead.get("previous_audit") is None
      and "parent-without-frozen-record" in json.dumps(snap_dead, ensure_ascii=False),
      f"status={r.status_code} snapshot_keys={sorted(snap_dead.keys()) if isinstance(snap_dead, dict) else snap_dead}")

# ---- 12. POST /runs/plan con padre --------------------------------------------------------------------
check("POST /runs/plan con padre inexistente -> 404",
      client.post("/runs/plan", json={"question": "q", "parent_run_id": "nope"}, headers=NAT).status_code == 404)
pl = client.post("/runs/plan", json={"question": "¿wt1a a 72 hpf?", "entities": ["wt1a"],
                                     "parent_run_id": ROOT}, headers=NAT)
check("POST /runs/plan con padre terminado: 200, thread_context_passed true, el plan lo declara",
      pl.status_code == 200 and pl.json().get("thread_context_passed") is True
      and pl.json().get("parent_run_id") == ROOT
      and pl.json()["plan"].get("thread_context_declared") is True, pl.text[:200])
pl0 = client.post("/runs/plan", json={"question": "¿raíz nueva?", "entities": []}, headers=NAT).json()
check("POST /runs/plan sin padre: thread_context_skipped_reason 'root-turn' y el plan NO lo declara",
      pl0.get("thread_context_skipped_reason") == "root-turn" and pl0["plan"].get("thread_context_declared") is False)

# ---- 13. ADR-0081 (G): GET /threads — el índice de investigaciones; (F): root_run_no en las vistas ---------
OLD_NO = db.get_run("old-run")["run_no"]
check("ADR-0081 (G): GET /threads sin token -> 401", client.get("/threads").status_code == 401)
check("ADR-0081 (G): GET /threads?limit=0 -> 400 · ?after=abc -> 422 (tipado) · ?limit=-3 -> 400",
      client.get("/threads?limit=0", headers=NAT).status_code == 400
      and client.get("/threads?after=abc", headers=NAT).status_code == 422
      and client.get("/threads?limit=-3", headers=NAT).status_code == 400)
ti = client.get("/threads", headers=NAT)
check("ADR-0081 (G): GET /threads -> 200", ti.status_code == 200, ti.text[:200])
TI = ti.json() if ti.status_code == 200 else {}
SOBRE = {"threads", "n", "limit", "limit_cap", "after", "has_more", "next_after", "order", "cursor_rule", "mine",
         "mine_rule", "n_turns_rule", "n_threads_total", "n_runs_without_thread", "n_runs_without_thread_rule", "costs"}
FILA = {"thread_id", "root_run_id", "root_run_no", "label", "root_pre_adr_0079", "root_counted", "root_question",
        "root_user_id", "root_state", "root_question_id", "n_turns", "n_closed", "n_with_record",
        "n_turns_without_record", "last_turn_no", "first_created_at", "last_created_at", "last_turn", "authors",
        "origins", "states"}
hilos = TI.get("threads") or []
por_hilo = {h["thread_id"]: h for h in hilos}
check("ADR-0081 (G): sobre EXACTO (16 llaves) y cada fila con las 21 llaves de (G); limit 50 = limit_cap (sin limit), "
      "after null, mine false, costs 'not-aggregated (GET /threads/{id})'",
      set(TI) == SOBRE and hilos and all(set(h) == FILA for h in hilos)
      and TI.get("limit") == 50 and TI.get("limit_cap") == 50 and TI.get("after") is None and TI.get("mine") is False
      and TI.get("costs") == "not-aggregated (GET /threads/{id})",
      f"sobre-extra={sorted(set(TI) ^ SOBRE)} fila-extra={sorted(set(hilos[0]) ^ FILA) if hilos else None}")
check("ADR-0081 (G): 4 investigaciones (raíz, old-run virtual, identidad rota, fallida) = n == n_threads_total; "
      "n_runs_without_thread 1 (sólo old-run, pre-ADR) — denominadores del SERVIDOR",
      TI.get("n") == 4 and TI.get("n_threads_total") == 4 and TI.get("n_runs_without_thread") == 1
      and set(por_hilo) == {ROOT, "old-run", BAD, DEAD},
      f"n={TI.get('n')} total={TI.get('n_threads_total')} sin_hilo={TI.get('n_runs_without_thread')} ids={sorted(por_hilo)}")
iguales, detalle_dif = True, []
for h in hilos:
    d = client.get(f"/threads/{h['thread_id']}", headers=NAT).json()
    for k in ("label", "root_run_no", "n_turns", "n_closed", "root_run_id", "root_pre_adr_0079", "n_turns_without_record"):
        if h.get(k) != d.get(k):
            iguales = False
            detalle_dif.append((h["thread_id"][:8], k, h.get(k), d.get(k)))
    if sorted(h.get("authors") or []) != d.get("authors") or h.get("origins") != d.get("origins"):
        iguales = False
        detalle_dif.append((h["thread_id"][:8], "authors/origins", h.get("authors"), d.get("authors")))
check("ADR-0081 (G): MISMA VERDAD POR DOS PUERTAS — label, root_run_no, root_run_id, n_turns, n_closed, "
      "n_turns_without_record, root_pre_adr_0079, authors y origins de CADA fila == GET /threads/{id}",
      bool(hilos) and iguales, f"{detalle_dif}")
nos = [h["root_run_no"] for h in hilos]
check("ADR-0081 (G): orden root_run_no DESC NULLS LAST (aquí ninguno null: la raíz virtual toma el run_no del padre por el JOIN)",
      bool(nos) and all(n is not None for n in nos) and nos == sorted(nos, reverse=True)
      and TI.get("order") == "root_run_no DESC NULLS LAST, thread_id ASC", f"{nos}")
hv = por_hilo.get("old-run") or {}
check("ADR-0081 (G): la raíz VIRTUAL (old-run): root_pre_adr_0079 true, root_counted false, n_turns 2 (+1 como get_thread), "
      "label 'T-<run_no del padre>', root_run_id 'old-run', root_state closed, states {closed 1, queued 1}",
      hv.get("root_pre_adr_0079") is True and hv.get("root_counted") is False and hv.get("n_turns") == 2
      and hv.get("label") == f"T-{OLD_NO}" and hv.get("root_run_no") == OLD_NO and hv.get("root_run_id") == "old-run"
      and hv.get("root_state") == "closed" and hv.get("states") == {"closed": 1, "queued": 1},
      f"{ {k: hv.get(k) for k in ('root_pre_adr_0079', 'root_counted', 'n_turns', 'label', 'root_run_no', 'states')} }")
hr = por_hilo.get(ROOT) or {}
check("ADR-0081 (G): la raíz REAL: root_counted true, root_pre_adr_0079 false, n_turns 5, n_closed 5, n_with_record 5, "
      "n_turns_without_record 0, last_turn_no 5, last_turn {run_id C4, turn_no 5, state closed}, authors [emmanuel, natalia], "
      "origins {smoke: 5}, root_user_id natalia, root_question <= 120",
      hr.get("root_counted") is True and hr.get("root_pre_adr_0079") is False and hr.get("n_turns") == 5
      and hr.get("n_closed") == 5 and hr.get("n_with_record") == 5 and hr.get("n_turns_without_record") == 0
      and hr.get("last_turn_no") == 5 and (hr.get("last_turn") or {}).get("run_id") == C4
      and (hr.get("last_turn") or {}).get("turn_no") == 5 and (hr.get("last_turn") or {}).get("state") == "closed"
      and hr.get("authors") == ["emmanuel", "natalia"] and hr.get("origins") == {"smoke": 5}
      and hr.get("root_user_id") == "natalia" and len(hr.get("root_question") or "") <= 120
      and hr.get("first_created_at") <= hr.get("last_created_at"),
      f"{ {k: hr.get(k) for k in ('root_counted', 'n_turns', 'n_closed', 'n_with_record', 'last_turn_no', 'last_turn', 'authors', 'origins')} }")
p1 = client.get("/threads?limit=1", headers=NAT).json()
check("ADR-0081 (G): paginación limit=1 → n 1, has_more true (medido con limit+1), next_after == root_run_no servido",
      p1.get("n") == 1 and p1.get("has_more") is True and p1.get("next_after") == (p1.get("threads") or [{}])[0].get("root_run_no")
      and p1.get("limit") == 1, f"n={p1.get('n')} has_more={p1.get('has_more')} next_after={p1.get('next_after')}")
vistos, cursor, paginas = [], None, 0
while paginas < 10:
    pg = client.get("/threads?limit=1" + (f"&after={cursor}" if cursor is not None else ""), headers=NAT).json()
    vistos.extend(h["thread_id"] for h in pg.get("threads") or [])
    paginas += 1
    if not pg.get("has_more"):
        break
    cursor = pg.get("next_after")
check("ADR-0081 (G): recorrer con cursor EXCLUSIVO (after = next_after) da los 4 hilos sin repetir en 4 páginas y termina con "
      "has_more false / next_after null",
      paginas == 4 and len(vistos) == 4 and len(set(vistos)) == 4 and set(vistos) == set(por_hilo)
      and pg.get("has_more") is False and pg.get("next_after") is None,
      f"paginas={paginas} vistos={[v[:8] for v in vistos]}")
p2 = client.get(f"/threads?after={nos[0]}", headers=NAT).json() if nos else {}
check("ADR-0081 (G): after=<root_run_no mayor> excluye ese hilo (cursor exclusivo) y devuelve los otros 3 con after eco",
      p2.get("n") == 3 and nos[0] not in [h["root_run_no"] for h in p2.get("threads") or []] and p2.get("after") == nos[0]
      if nos else False, f"n={p2.get('n')} after={p2.get('after')}")
check("ADR-0081 (G): limit=500 → limit 50 (el tope manda y se declara: limit_cap 50)",
      client.get("/threads?limit=500", headers=NAT).json().get("limit") == 50)
me = client.get("/threads?mine=true", headers=EMM).json()
mn = client.get("/threads?mine=true", headers=NAT).json()
check("ADR-0081 (G): mine=true (emmanuel: sólo el turno C3 en la raíz) → [ROOT], mine true, n_threads_total 1 (denominador del "
      "MISMO filtro); mine=true (natalia) → los 4; mine_rule declarada",
      [h["thread_id"] for h in me.get("threads") or []] == [ROOT] and me.get("mine") is True and me.get("n_threads_total") == 1
      and mn.get("n") == 4 and mn.get("n_threads_total") == 4 and "mine" in (me.get("mine_rule") or ""),
      f"emm={[h['thread_id'][:8] for h in me.get('threads') or []]} total={me.get('n_threads_total')} nat_n={mn.get('n')}")

# (F) root_run_no en las VISTAS: POST /runs, lista, detalle — misma consulta, misma llave
det_c1 = client.get(f"/runs/{C1}", headers=NAT).json()
lst = {row["run_id"]: row for row in client.get("/runs", headers=NAT).json()["runs"]}
old_v = client.get("/runs/old-run", headers=NAT).json()
hijo_old = client.get(f"/runs/{h_old['run_id']}", headers=NAT).json()
check("ADR-0081 (F): root_run_no en la VISTA — POST /runs raíz == su run_no; hijo C1: detalle == lista == run_no de la raíz; "
      "hijo de raíz virtual == run_no del padre pre-ADR (el JOIN lo encuentra); la corrida pre-ADR: llave PRESENTE y null declarado",
      raiz.get("root_run_no") == raiz["run_no"] and det_c1.get("root_run_no") == raiz["run_no"]
      and lst.get(C1, {}).get("root_run_no") == raiz["run_no"] and h_old.get("root_run_no") == OLD_NO
      and hijo_old.get("root_run_no") == OLD_NO and "root_run_no" in old_v and old_v.get("root_run_no") is None,
      f"raiz={raiz.get('root_run_no')}/{raiz['run_no']} c1={det_c1.get('root_run_no')} lista={lst.get(C1, {}).get('root_run_no')} "
      f"h_old={h_old.get('root_run_no')}/{OLD_NO} old={old_v.get('root_run_no')!r}")
check("ADR-0081 (F): root_run_no de la vista == root_run_no de GET /threads/{id} para la raíz, el hijo y el hijo de la virtual",
      det_c1.get("root_run_no") == T.get("root_run_no") == raiz["run_no"] and hijo_old.get("root_run_no") == t_old.json().get("root_run_no"))

_fin()
