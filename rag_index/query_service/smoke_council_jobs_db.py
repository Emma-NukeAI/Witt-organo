"""smoke_council_jobs_db.py — gate determinista de la rebanada C4 (ADR-0082 E.1 + E.2): BD del consejo + job de ronda 1.

Mide (fila `smoke_council_jobs_db.py` de la tabla NO-SPEND del ADR):
  · _migrate idempotente ×2 (columnas del consejo en plans/runs, tabla plan_events, índice) y su SQL compilado para
    postgresql (tipo fecha TIMESTAMP WITH TIME ZONE, sin DATETIME ni funciones exclusivas de SQLite);
  · planes viejos: council_state NULL se LEE 'pre-adr-0082' (tres estados: columna ausente ≠ NULL ≠ valor; jamás backfill);
  · claim_next_council_plan ATÓMICO (2 hilos → 1 gana), FIFO por created_at, filtro por origin (Context 9);
  · plan_add_event: seq monotónico + council_last_event_at refrescado; plan_events_after con la forma de events_after;
  · el worker con 17 miembros FAKEADOS (válidos, duplicados con tokens permutados, no aplicable, caídos http-529 y
    excepción, respuesta ilegible, timeout por reloj real, fuera de vocabulario, campos prohibidos, exceso sobre el tope,
    web/figure insatisfacibles, exploratorio must→should, causal-pruner hard_rule, banderas) → 'applicable',
    council_json con rounds[0] (RoundResult íntegro) + requisitos agregados + aggregation_sha REPRODUCIBLE desde lo
    persistido; eventos council.state → member ×N → round → aggregate → council.state, TODOS desde el hilo orquestador;
  · persistencia INCREMENTAL: el proceso "muere" (BaseException desde on_event) tras 9 futures → 9 filas y su usage
    quedan escritos, el plan sigue 'running' y el reaper de arranque lo sentencia 'errored (worker-lost-restart)' sin
    tocar lo persistido;
  · excepción del worker → 'errored (<Tipo>)' con council_error y lo persistido; el hilo worker_loop sigue vivo y
    procesa el siguiente job;
  · reaper: 'running' con latido viejo → 'errored (worker-lost)' + evento; latido fresco intacto; carrera → rowcount 0;
  · set_plan_ledger rechaza tras mark_plan_used; plans_council_pending (dedup); count_plans_council; plans_council_usage
    sólo planes con council_state; create_run(council_json=) → get_run y list_runs lo traen (lista == detalle);
  · kill-switch WITT_COUNCIL=0: execute_round1 → 'disabled (…)' con CERO llamadas y CERO stage.council.*;
    start_council_workers → 0 hilos, sin siega, huérfanos declarados; worker_loop no reclama;
  · start_council_workers real (1 worker + reaper propio) procesa un job encolado; urlopen REAL bloqueado y contado = 0;
    mcp_cache byte-idéntico (listado + tamaños + mtimes).

100% offline: una .db SQLite por smoke (se borra al arrancar), caller fake inyectado, cero red, cero gasto de modelo,
DATA INAMOVIBLE sólo lectura (resolve_id.resolve en el camino por default de UN job). Exit 0 = todo PASS.

Corre (con la máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr82-smoke_council_jobs_db.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_council_jobs_db.py
"""
import datetime
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_default_db = SMOKES_DIR / "smoke-council-jobs-db.db"
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{_default_db.as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()   # BD fresca por corrida del smoke: el gate no hereda estado
os.environ.pop("NEO4J_URI", None)
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")
# las 27 env del ADR-0082 fuera del proceso: el smoke mide los DEFAULTS declarados (patrón ENV_ADR_0081 de gen_fixtures)
for _k in list(os.environ):
    if _k.startswith("WITT_COUNCIL") or _k in ("WITT_MODEL_COUNCIL", "WITT_CG_COUNCIL_COMPONENT",
                                                "WITT_ANTHROPIC_MAX_INFLIGHT", "WITT_ANTHROPIC_RETRY_AFTER_CAP_S"):
        os.environ.pop(_k, None)

# ---- cero red: urlopen REAL bloqueado y contado --------------------------------------------------------------------
_URLOPEN_CALLS = []


def _blocked_urlopen(*a, **k):
    _URLOPEN_CALLS.append(a[0] if a else None)
    raise AssertionError("smoke: urllib.request.urlopen bloqueado (cero red)")


urllib.request.urlopen = _blocked_urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
import db  # noqa: E402
import council_jobs as cj  # noqa: E402
from lib import agent_matrix, catalog_cards, council, composite_auditor, models  # noqa: E402
# El id del modelo del consejo se LEE de la tabla (rol `council`, D.2): cero literales de modelo fuera de models.py (M.4)
COUNCIL_MODEL = models.resolve_role("council")["model"]
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _mcp_cache_snapshot():
    base = ROOT / "mcp_cache"
    if not base.exists():
        return None
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            st = p.stat()
            out.append((str(p.relative_to(base)), st.st_size, st.st_mtime_ns))
    return out


MCP_BEFORE = _mcp_cache_snapshot()
NOOP_RESOLVER = lambda e: None   # noqa: E731 — sin tocar la DATA INAMOVIBLE salvo en el job con defaults (abajo)
NO_PRIOR = {"state": "empty-corpus", "items": [], "n": 0, "kinds": []}
PLAN_JSON = json.dumps({"plan_version": "4", "question": "q", "entities": ["osr1"],
                        "judgment": {"work_type": "sufficiency", "route": "evidence-run", "niches": ["N1"],
                                     "clarifying_questions": [], "state": "declared"},
                        "thread_parent_run_id": None})

# ====================================================================================================================
# 1. _migrate idempotente ×2 · esquema · SQL compilado para postgresql
# ====================================================================================================================
db.init_db()
st1 = db.council_schema_state()
db.init_db()
st2 = db.council_schema_state()
check("1a _migrate idempotente ×2: plans/runs con las columnas del consejo y plan_events presente tras dos init_db",
      st1["ready"] and st2 == st1, json.dumps(st2))
check("1b PLAN_COUNCIL_COLUMNS (13) ⊆ plans.c · runs.c.council_json · plan_events con PK (plan_id, seq) y FK a plans",
      set(db.PLAN_COUNCIL_COLUMNS) <= set(db.plans.c.keys()) and len(db.PLAN_COUNCIL_COLUMNS) == 13
      and "council_json" in db.runs.c and [c.name for c in db.plan_events.primary_key.columns] == ["plan_id", "seq"]
      and any(fk.column.table.name == "plans" for fk in db.plan_events.c.plan_id.foreign_keys))
_pg = postgresql.dialect()
stm_pg = db.council_migration_statements(_pg)
stm_dt = [s for s in stm_pg if any(c in s for c in db.PLAN_COUNCIL_DT_COLUMNS)]
check("1c SQL de la migración compilado para postgresql: 14 ALTER (1 runs + 13 plans); las 5 fechas 'TIMESTAMP WITH TIME "
      "ZONE'; ningún 'DATETIME'",
      len(stm_pg) == 14 and len(stm_dt) == 5 and all("TIMESTAMP WITH TIME ZONE" in s for s in stm_dt)
      and not any("DATETIME" in s for s in stm_pg), stm_dt[0])
ddl_pe = str(CreateTable(db.plan_events).compile(dialect=_pg))
check("1d DDL de plan_events (postgresql): TIMESTAMP WITH TIME ZONE · PRIMARY KEY (plan_id, seq) · FOREIGN KEY → plans",
      "TIMESTAMP WITH TIME ZONE" in ddl_pe and "PRIMARY KEY (plan_id, seq)" in ddl_pe
      and "REFERENCES plans (plan_id)" in ddl_pe)
sql_claim = str(db._claim_council_query(("production",)).compile(dialect=_pg))
sql_pend = str(db._plans_council_pending_query("u", "q", "", _now()).compile(dialect=_pg))
sql_list = str(db._list_select().compile(dialect=_pg))
check("1e SELECTs compilan para postgresql: claim (council_state = queued, origin IN, ORDER BY created_at, LIMIT 1) · "
      "dedup (council_state IN, created_at >=) · la LISTA de corridas trae runs.council_json",
      "plans.council_state = " in sql_claim and "plans.origin IN" in sql_claim and "ORDER BY plans.created_at ASC" in sql_claim
      and "LIMIT" in sql_claim and "plans.council_state IN" in sql_pend and "plans.created_at >=" in sql_pend
      and "runs.council_json" in sql_list)
check("1f ix_plans_council_state existe en la BD (IF NOT EXISTS, idempotente)",
      any(ix["name"] == "ix_plans_council_state" for ix in db.sa_inspect(db.engine()).get_indexes("plans")))

# ====================================================================================================================
# 2. planes viejos y los tres estados
# ====================================================================================================================
db.upsert_user("u1", "U1", "dev", "pw")
db.upsert_user("u2", "U2", "medico", "pw")
db.create_plan("p-old", "u1", "vieja?", [], "{}")                  # llamador viejo: sin origin ni council_state
row_old = db.get_plan("p-old")
check("2a plan viejo: council_state NULL en la fila (None), leído 'pre-adr-0082' por council_state_of; columna PRESENTE",
      "council_state" in row_old and row_old["council_state"] is None and row_old["origin"] is None
      and db.council_state_of(row_old) == db.COUNCIL_STATE_PRE_ADR and db.council_state_of({}) is None
      and db.council_state_of(None) is None)


def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


check("2b create_plan / update_plan_council rechazan council_state > COUNCIL_STATE_MAXLEN (96: el literal E.3 de origin mide hasta 74; "
      "Postgres lo rechazaría) y columnas ajenas (ValueError); el literal largo de E.3 SÍ entra",
      db.COUNCIL_STATE_MAXLEN == 96 and len("not-requested (origin invalid-env:xxxxxxxxxxxxxxxxxx not in WITT_COUNCIL_ORIGINS)") <= 96
      and _raises(lambda: db.create_plan("p-bad", "u1", "x", [], "{}", council_state="x" * 97), ValueError)
      and _raises(lambda: db.update_plan_council("p-old", plan_json="{}"), ValueError)
      and _raises(lambda: db.update_plan_council("p-old", council_state="e" * 97), ValueError)
      and db.get_plan("p-bad") is None)
check("2c update_plan_council devuelve False para un plan inexistente y True para uno existente (UPDATE parcial)",
      db.update_plan_council("no-such-plan", council_state="queued") is False
      and db.update_plan_council("p-old", council_error="x") is True and db.get_plan("p-old")["council_error"] == "x"
      and db.update_plan_council("p-old", council_error=None) is True)

# ====================================================================================================================
# 3. claim atómico, FIFO, filtro por origin
# ====================================================================================================================
db.create_plan("p-fifo-1", "u1", "primera?", ["osr1"], PLAN_JSON, origin="smoke", council_state="queued")
check("3a claim con origins=('production',): ninguno (el plan es smoke) — Context 9",
      db.claim_next_council_plan("w", origins=("production",)) is None)
_wins, _lock = [], threading.Lock()


def _claimer(i):
    r = db.claim_next_council_plan(f"boot:1:council-worker-{i}", origins=("smoke",))
    with _lock:
        _wins.append(r["plan_id"] if r else None)


_ths = [threading.Thread(target=_claimer, args=(i,)) for i in range(2)]
for t in _ths:
    t.start()
for t in _ths:
    t.join(10)
_got = [w for w in _wins if w]
c1 = db.get_plan("p-fifo-1")
check("3b claim atómico (2 hilos a la vez sobre el ÚNICO plan smoke queued): exactamente UNO lo reclama, el otro recibe None",
      len(_wins) == 2 and _got == ["p-fifo-1"] and c1["council_state"] == "running", f"wins={_wins}")
# la rama de la carrera, determinista: el SELECT del reclamo "leyó" un plan que YA está running (otro worker ganó entre el
# SELECT y el UPDATE) → el UPDATE WHERE council_state='queued' da rowcount 0 → None, y nada se pisa
_real_claim_q = db._claim_council_query
db._claim_council_query = lambda origins=None, plan_id=None: db.select(db.plans).where(db.plans.c.plan_id == "p-fifo-1")
perdedor = db.claim_next_council_plan("boot:1:council-worker-1", origins=("smoke",))
db._claim_council_query = _real_claim_q
check("3b-race carrera resuelta en la BD: SELECT viejo sobre un plan ya running → UPDATE optimista rowcount 0 → None; claimed_by intacto",
      perdedor is None and db.get_plan("p-fifo-1")["council_claimed_by"] == c1["council_claimed_by"])
time.sleep(0.01)
db.create_plan("p-fifo-2", "u1", "segunda?", ["osr1"], PLAN_JSON, origin="smoke", council_state="queued")
time.sleep(0.01)
db.create_plan("p-fixture", "u1", "fixture?", ["osr1"], PLAN_JSON, origin="fixture", council_state="queued")   # FIFO: después de p-fifo-2
check("3c la fila reclamada lleva claimed_by boot:pid:hilo, claimed_at == started_at == last_event_at (latido desde el reclamo)",
      c1["council_claimed_by"].startswith("boot:1:council-worker-") and c1["council_claimed_at"] is not None
      and c1["council_claimed_at"] == c1["council_started_at"] == c1["council_last_event_at"]
      and c1["council_claimed_at"].tzinfo is not None)
r2 = db.claim_next_council_plan("w2", origins=("smoke",))
check("3d siguiente claim smoke → p-fifo-2 (FIFO); otro → None (p-fixture NO es smoke); con origins=None (all) → p-fixture; "
      "claim por plan_id de uno ya running → None",
      r2 and r2["plan_id"] == "p-fifo-2" and db.claim_next_council_plan("w3", origins=("smoke",)) is None
      and (db.claim_next_council_plan("w4", origins=None) or {}).get("plan_id") == "p-fixture"
      and db.claim_next_council_plan("w5", plan_id="p-fifo-1") is None)
# devolver p-fifo-2 y p-fixture a queued para reutilizarlos (sólo el smoke: en producción nada re-encola)
db.update_plan_council("p-fifo-2", council_state="queued", council_claimed_by=None, council_claimed_at=None,
                       council_started_at=None, council_last_event_at=None)
db.update_plan_council("p-fixture", council_state="queued", council_claimed_by=None, council_claimed_at=None,
                       council_started_at=None, council_last_event_at=None)

# ====================================================================================================================
# 4. plan_add_event: seq monotónico + latido
# ====================================================================================================================
lea0 = db.get_plan("p-fifo-1")["council_last_event_at"]
time.sleep(0.01)
seqs = [db.plan_add_event("p-fifo-1", "council.state", {"state": "running"}, agent="council"),
        db.plan_add_event("p-fifo-1", "stage.council.progress", {"n_done": 0, "heartbeat": True}, agent="council"),
        db.plan_add_event("p-fifo-1", "stage.council.member", None, agent="council", tool="emit_information_requirements")]
evs = db.plan_events_after("p-fifo-1")
lea1 = db.get_plan("p-fifo-1")["council_last_event_at"]
check("4a plan_add_event: seq 1,2,3 monotónico · plan_events_after los devuelve en orden con la forma de events_after "
      "(plan_id, seq, ts ISO, type, agent, tool, level, degraded, payload dict|None) · after=2 → sólo el 3",
      seqs == [1, 2, 3] and [e["seq"] for e in evs] == [1, 2, 3]
      and set(evs[0]) == {"plan_id", "seq", "ts", "type", "agent", "tool", "level", "degraded", "payload"}
      and evs[0]["payload"] == {"state": "running"} and evs[2]["payload"] is None and evs[2]["tool"] == "emit_information_requirements"
      and [e["seq"] for e in db.plan_events_after("p-fifo-1", after_seq=2)] == [3] and db.plan_events_count("p-fifo-1") == 3)
check("4b plan_add_event refresca plans.council_last_event_at (latido)", lea1 is not None and lea1 > lea0)
check("4c run_events y plan_events no se mezclan: add_event sobre una corrida no toca plan_events",
      db.plan_events_count("p-fifo-2") == 0 and db.plan_events_after("no-plan") == [])

# ====================================================================================================================
# 5. el worker con 17 miembros FAKEADOS
# ====================================================================================================================
REQ_OK = {"gap": "phenotype of osr1 morphants at 24 hpf", "evidence_kind": "phenotype", "source_family": "zfin",
          "query_en": "osr1 pronephros phenotype 24 hpf", "entities": ["osr1"], "acceptance_test": "a ZFIN phenotype record",
          "priority": "must"}
_FAKE_CALLS = []
_FAKE_LOCK = threading.Lock()


def _req(**kw):
    return {**REQ_OK, **kw}


def _ok(reqs, usage=None, extra=None):
    out = {"applicable": True, "requirements": reqs}
    if extra:
        out.update(extra)
    return (out, usage or {"input_tokens": 100, "output_tokens": 30, "cache_read_input_tokens": 50},
            {"model_reported": COUNCIL_MODEL, "attempts": 1, "api": "fake"})


def fake_r1(req):
    a = req["agent"]
    with _FAKE_LOCK:
        _FAKE_CALLS.append(a)
    assert req["round"] == "r1" and req["tool_choice"] == {"type": "tool", "name": req["tool"]}
    assert len(req["tools"]) == 3 and req["tools_sha"] == council.TOOLS_SHA
    if a == "causal-pruner":                         # hard-rule; su requisito nace hard_rule_gate True (código)
        return _ok([REQ_OK], usage={"input_tokens": 120, "output_tokens": 40, "cache_creation_input_tokens": 600})
    if a in ("sim-orchestrator", "benchmark-designer", "fitness-curator"):   # duplicados con tokens permutados
        return _ok([_req(query_en="24 hpf pronephros phenotype osr1", gap=f"gap por {a}")])
    if a == "squidiff-in-silico-gate":               # fuera de vocabulario: el ítem se descarta y se cuenta crudo
        return _ok([_req(source_family="pubmed-central", evidence_kind="paper"), _req(query_en="squidiff osr1 in silico")])
    if a == "experiment-designer":                   # campos PROHIBIDOS en la salida → dropped_fields, no viajan
        return _ok([_req(query_en="osr1 knockdown pronephros experiment design")],
                   extra={"direct_answer": "osr1 is required", "confidence": 0.9})
    if a == "imaging-analyst":                       # 7 requisitos → 5 + n_dropped_over_cap 2
        return _ok([_req(query_en=f"imaging osr1 pronephros series {i}", priority="should") for i in range(7)])
    if a == "marker-validator":                      # caído: transporte 529 con gasto medido del intento
        raise composite_auditor.CallerError("http-529", "overloaded", usage={"input_tokens": 40, "output_tokens": 0},
                                            meta={"attempts": 2, "api": "fake"})
    if a == "scrna-seq-analyst":                     # no aplicable, emitido por el miembro: CUENTA como válido
        return ({"applicable": False, "not_applicable_reason": "no single-cell dataset is in scope for this question"},
                {"input_tokens": 90, "output_tokens": 12}, {"model_reported": COUNCIL_MODEL, "attempts": 1})
    if a == "spatial-omics-analyst":                 # excepción cualquiera del caller → errored caller-exception
        raise RuntimeError("fake transport exploded")
    if a == "histology-reviewer":                    # respuesta ILEGIBLE (no es tupla) → errored
        return {"applicable": True, "requirements": [REQ_OK]}
    if a == "cross-modality-integrator":             # lento > member_timeout_s (reloj real) → timeout, abandonado
        time.sleep(0.9)
        return _ok([_req(query_en="late answer")])
    if a == "literature-monitor":
        return _ok([_req(gap="recent papers on osr1 sufficiency", evidence_kind="paper", source_family="europepmc",
                         query_en="osr1 pronephros sufficiency", entities=["osr1", "lhx1a"], priority="should")])
    if a == "domain-knowledge-curator":              # web: unsatisfiable-by-harness (contado, no gatea — E1)
        return _ok([_req(gap="preprints", evidence_kind="web", source_family="web", query_en="osr1 preprint pronephros")])
    if a == "hypothesis-generator":                  # figure: unsatisfiable (ADR-0083)
        return _ok([_req(gap="a figure", evidence_kind="figure", source_family="europepmc", query_en="osr1 figure 24 hpf")])
    if a == "cross-field-bridge-agent":              # exploratorio: must → should con priority_downgraded_from
        return _ok([_req(gap="cross-field bridge", evidence_kind="pathway", source_family="reactome",
                         query_en="kidney development pathway osr1 mammals", entities=["OSR1"])])
    if a == "regulatory-ethics-advisor":             # sólo banderas (emit_flags); gate 'human' lo pone el código
        assert req["tool"] == council.FLAGS_TOOL_NAME
        return ({"applicable": True, "flags": [{"kind": "animal-work", "statement": "zebrafish embryos < 5 dpf"},
                                               {"kind": "compliance", "statement": "check IACUC protocol scope"}]},
                {"input_tokens": 80, "output_tokens": 20, "cache_read_input_tokens": 50},
                {"model_reported": COUNCIL_MODEL, "attempts": 1})
    raise AssertionError(f"miembro no previsto por el fake: {a}")


_EVENT_THREADS = set()
_real_plan_add_event = db.plan_add_event


def _spy_plan_add_event(*a, **k):
    _EVENT_THREADS.add(threading.get_ident())
    return _real_plan_add_event(*a, **k)


db.plan_add_event = _spy_plan_add_event
cfg_fast = council.config(os.environ, member_timeout_s=0.3, budget_s=20.0, concurrency=6)
row1 = db.get_plan("p-fifo-1")
_t = time.time()
res1 = cj.execute_round1(row1, caller=fake_r1, cfg=cfg_fast, resolver=NOOP_RESOLVER, prior=NO_PRIOR)
_elapsed = time.time() - _t
db.plan_add_event = _real_plan_add_event
P1 = db.get_plan("p-fifo-1")
CJ1 = json.loads(P1["council_json"])
U1 = json.loads(P1["council_usage_json"])
R0 = CJ1["rounds"][0]
rows_by = {r["agent"]: r for r in R0["members"]}
check("5a 17 fakes → council_state 'applicable' · n_members 17 · n_valid 13 (12 ok + 1 not-applicable) ≥ cuórum 11 · "
      "errored 3 · timeout 1 · 17 llamadas al fake, una por miembro",
      P1["council_state"] == "applicable" and res1["state"] == "applicable" and R0["n_members"] == 17
      and R0["n_valid"] == 13 and R0["n_ok"] == 12 and R0["n_not_applicable"] == 1 and R0["n_errored"] == 3
      and R0["n_timeout"] == 1 and R0["quorum"] == {**R0["quorum"], "required": 11, "met": True}
      and sorted(_FAKE_CALLS) == sorted(agent_matrix.MEMBERS) and res1["n_calls"] == 17,
      f"state={P1['council_state']} valid={R0['n_valid']} err={R0['n_errored']} to={R0['n_timeout']} calls={len(_FAKE_CALLS)}")
check("5b filas por miembro: marker-validator errored http-529 con usage MEDIDO del intento (40 in) · spatial-omics "
      "caller-exception · histology-reviewer caller-exception (respuesta ilegible) · cross-modality timeout abandonado "
      "con usage null + late_usage_state · scrna not-applicable con razón",
      rows_by["marker-validator"]["status"] == "errored" and rows_by["marker-validator"]["error_kind"] == "http-529"
      and rows_by["marker-validator"]["usage"] == {"input_tokens": 40, "output_tokens": 0}
      and rows_by["spatial-omics-analyst"]["error_kind"] == "caller-exception"
      and rows_by["histology-reviewer"]["status"] == "errored" and rows_by["histology-reviewer"]["error_kind"] == "caller-exception"
      and rows_by["cross-modality-integrator"]["status"] == "timeout" and rows_by["cross-modality-integrator"]["usage"] is None
      and rows_by["cross-modality-integrator"].get("abandoned") is True
      and rows_by["cross-modality-integrator"]["late_usage_state"].startswith("unrecoverable")
      and rows_by["scrna-seq-analyst"]["status"] == "not-applicable"
      and rows_by["scrna-seq-analyst"]["not_applicable_reason"].startswith("no single-cell"))
check("5c validación por código: squidiff off_vocabulary ['pubmed-central'] (ítem descartado, 1 kept) · experiment-designer "
      "dropped_fields ⊇ {direct_answer, confidence} (no viajan) · imaging-analyst n_dropped_over_cap 2 (5 kept)",
      [o["value"] for o in rows_by["squidiff-in-silico-gate"]["validation"]["off_vocabulary"]] == ["pubmed-central"]
      and len(rows_by["squidiff-in-silico-gate"]["output"]["requirements"]) == 1
      and {"direct_answer", "confidence"} <= set(rows_by["experiment-designer"]["validation"]["dropped_fields"])
      and "direct_answer" not in rows_by["experiment-designer"]["output"]
      and rows_by["imaging-analyst"]["validation"]["n_dropped_over_cap"] == 2
      and len(rows_by["imaging-analyst"]["output"]["requirements"]) == 5)
reqs1 = CJ1["requirements"]
by_rid = {r["requirement_id"]: r for r in reqs1}
dup = next((r for r in reqs1 if r["n_requested_by"] == 4), None)
xf = next((r for r in reqs1 if r["requested_by"] == ["cross-field-bridge-agent"]), None)
check("5d agregación (código): el requisito duplicado con tokens permutados → UNO pedido por 4 de 17 (query del 1º por tabla: "
      "causal-pruner), hard_rule_gate True (causal-pruner emite), variants 1 · cross-field must → should con "
      "priority_downgraded_from 'must' · n_unsatisfiable 2 (web + figure) · n_flags 2 con gate 'human' · n_hard_rule ≥ 1",
      dup is not None and dup["requested_by"][0] == "causal-pruner" and dup["n_members"] == 17 and dup["hard_rule_gate"] is True
      and dup["query_en"] == REQ_OK["query_en"] and dup["variants"] == ["24 hpf pronephros phenotype osr1"]
      and xf is not None and xf["priority"] == "should" and xf["priority_downgraded_from"] == "must" and xf["exploratory"] is True
      and CJ1["n_unsatisfiable"] == 2 and CJ1["n_flags"] == 2 and all(f["gate"] == "human" for f in CJ1["flags"])
      and CJ1["n_hard_rule"] >= 1 and CJ1["requirements"] == CJ1["aggregation"]["requirements"],
      f"n_req={CJ1['n_requirements']} unsat={CJ1['n_unsatisfiable']} flags={CJ1['n_flags']}")
check("5e requisitos SIN decisión (el ledger es del humano): ninguna llave decision/decided_by; council_ledger_json NULL; "
      "orden must > should, n_requested_by desc",
      all("decision" not in r and "decided_by" not in r for r in reqs1) and P1["council_ledger_json"] is None
      and [r["priority"] for r in reqs1] == sorted([r["priority"] for r in reqs1], key=lambda p: 0 if p == "must" else 1)
      and reqs1[0]["n_requested_by"] == 4)
check("5f council_json: la forma que app lee — membership_version cm-1, n_members 17, members[] (orden de tabla), full_council "
      "False, catalog_sha == catalog_cards.CATALOG_SHA, rounds[0]{round r1, n_valid, usage{in,out,cache_creation,cache_read}}, "
      f"requirements[] top-level, flags[], aggregation_sha; model {{requested {COUNCIL_MODEL} (tabla, rol council), source default:g2…}}; "
      "persisted.final",
      CJ1["membership_version"] == "cm-1" and CJ1["n_members"] == 17 and CJ1["members"] == list(agent_matrix.MEMBERS)
      and CJ1["full_council"] is False and CJ1["catalog_sha"] == catalog_cards.CATALOG_SHA
      and R0["round"] == "r1" and R0["kind"] == "requirements" and R0["phase"] == "plan"
      and {"in", "out", "cache_creation", "cache_read"} <= set(R0["usage"])
      and CJ1["aggregation_sha"] == CJ1["aggregation"]["aggregation_sha"] and len(CJ1["aggregation_sha"]) == 64
      and CJ1["model"]["requested"] == COUNCIL_MODEL and CJ1["model"]["source"].startswith("default:")
      and CJ1["persisted"]["state"] == "final" and CJ1["persisted"]["n_members_persisted"] == 17
      and CJ1["persisted"]["n_writes"] == 18 and res1["n_writes"] == 18
      and CJ1["rules_sha"] == council.RULES_SHA and CJ1["tools_sha"] == council.TOOLS_SHA
      and CJ1["prior_observations"]["state"] == "empty-corpus")
# con usage medido: causal 120 · 10 ok de 100 (sim, bench, fitness, squidiff, experiment, imaging, literature, domain,
# hypothesis, cross-field) · scrna 90 · regulatory 80 · marker 40 (CallerError.usage) = 14 miembros; SIN usage: timeout
# (abandonado), spatial (RuntimeError sin usage), histology (respuesta ilegible) = 3 → n_members_measured 14
exp_in = 120 + 100 * 10 + 90 + 80 + 40
exp_out = 40 + 30 * 10 + 12 + 20 + 0
exp_cr = 50 * 10 + 50                          # los 10 ok de 100 + regulatory
check("5g council_usage_json MEDIDO = suma de TODOS los intentos medidos (14 miembros con usage; timeout/excepción sin usage NO suman ni valen 0): "
      f"in {exp_in} · out {exp_out} · cache_creation 600 · cache_read {exp_cr} · by_model[{COUNCIL_MODEL}] · state measured",
      U1["in"] == exp_in and U1["out"] == exp_out and U1["cache_creation"] == 600 and U1["cache_read"] == exp_cr
      and U1["n_members_measured"] == 14 and U1["model"] == COUNCIL_MODEL and set(U1["by_model"]) == {COUNCIL_MODEL}
      and U1["by_model"][COUNCIL_MODEL]["in"] == exp_in and U1["state"] == "measured (round closed)" and U1["class"] == "medicion"
      and R0["usage"]["in"] == exp_in and R0["usage"]["cache_creation"] == 600,
      json.dumps({k: U1[k] for k in ("in", "out", "cache_creation", "cache_read", "n_members_measured")}))
ev1 = db.plan_events_after("p-fifo-1", after_seq=3)
types1 = [e["type"] for e in ev1]
n_done = sum(1 for e in ev1 if e["type"] == "stage.council.member" and e["payload"]["phase"] == "done")
n_start = sum(1 for e in ev1 if e["type"] == "stage.council.member" and e["payload"]["phase"] == "start")
check("5h traza del plan: council.state{running} → stage.council.member start/done ×17 → stage.council.round → "
      "stage.council.aggregate → council.state{applicable}; seq monotónico; n_invoked == start == done == 17",
      types1[0] == "council.state" and ev1[0]["payload"]["state"] == "running"
      and types1[-3:] == ["stage.council.round", "stage.council.aggregate", "council.state"]
      and ev1[-1]["payload"]["state"] == "applicable" and n_start == 17 and n_done == 17 == R0["n_invoked"]
      and [e["seq"] for e in ev1] == list(range(4, 4 + len(ev1)))
      and ev1[-2]["payload"]["aggregation_sha"] == CJ1["aggregation_sha"]
      and all(e["agent"] == "council" for e in ev1),
      f"types={types1[:3]}…{types1[-3:]} start={n_start} done={n_done}")
check("5i TODOS los eventos se escribieron desde el hilo orquestador (el que llamó execute_round1); "
      "rounds[0].events.emitted_from 'orchestrator-thread'; cache_prefix_identical_across_members True",
      _EVENT_THREADS == {threading.get_ident()} and R0["events"]["emitted_from"] == "orchestrator-thread"
      and R0["cache_prefix_identical_across_members"] is True and R0["stagger_first"]["agent"] == "causal-pruner",
      f"threads={len(_EVENT_THREADS)}")
agg_again = council.aggregate_r1(R0, members=CJ1["members"], cfg=cfg_fast, resolver=NOOP_RESOLVER)
check("5j aggregation_sha REPRODUCIBLE desde lo persistido: re-agregar rounds[0] (tras el viaje por JSON) → mismo sha y mismos ids",
      agg_again["aggregation_sha"] == CJ1["aggregation_sha"]
      and [r["requirement_id"] for r in agg_again["requirements"]] == [r["requirement_id"] for r in reqs1])
check("5k council_finished_at sellado · council_error NULL · el timeout no infló el reloj (< 8 s con member_timeout 0.3)",
      P1["council_finished_at"] is not None and P1["council_error"] is None and _elapsed < 8.0, f"{_elapsed:.2f}s")

# ====================================================================================================================
# 6. persistencia INCREMENTAL: el proceso muere tras 9 futures
# ====================================================================================================================
class _Death(BaseException):
    """Simula la muerte del PROCESO (redeploy/OOM) — BaseException: execute_round1 NO la captura."""


_dones = []


def _on_event_kill(etype, payload):
    if etype == "stage.council.member" and payload.get("phase") == "done":
        _dones.append(payload["agent"])
        if len(_dones) == 9:
            raise _Death("proceso muerto a media ronda")


def fake_all_ok(req):
    if req["tool"] == council.FLAGS_TOOL_NAME:      # regulatory-ethics-advisor sólo emite banderas
        return ({"applicable": True, "flags": []}, {"input_tokens": 10, "output_tokens": 5},
                {"model_reported": COUNCIL_MODEL, "attempts": 1})
    return _ok([_req(query_en=f"q {req['agent']}")], usage={"input_tokens": 10, "output_tokens": 5})


db.create_plan("p-die", "u1", "muere?", ["osr1"], PLAN_JSON, origin="smoke", council_state="queued")
row_die = db.claim_next_council_plan("boot:1:council-worker-0", origins=("smoke",), plan_id="p-die")   # p-fifo-2 sigue queued
died = False
try:
    cj.execute_round1(row_die, caller=fake_all_ok, cfg=cfg_fast, resolver=NOOP_RESOLVER, prior=NO_PRIOR, on_event=_on_event_kill)
except _Death:
    died = True
PD = db.get_plan("p-die")
CJD = json.loads(PD["council_json"])
UD = json.loads(PD["council_usage_json"])
check("6a la muerte sube (BaseException no se captura) y el plan queda 'running' (sin finished_at): lo sentencia el reaper",
      died and PD["council_state"] == "running" and PD["council_finished_at"] is None and row_die["plan_id"] == "p-die")
check("6b lo gastado ANTES de morir SOBREVIVE: council_json.rounds[0].members = 9 filas parciales (usage 10/5 c/u) · "
      "state 'running' · persisted 'partial (9 of 17 …)' · council_usage_json in 90 / out 45 / n_members_measured 9 · "
      "requirements [] y n_requirements null (no medido ≠ 0)",
      len(CJD["rounds"][0]["members"]) == 9 and CJD["state"] == "running"
      and CJD["persisted"]["state"].startswith("partial (9 of 17") and CJD["rounds"][0]["n_collected"] == 9
      and all(r["usage"] == {"input_tokens": 10, "output_tokens": 5} and r["status"] == "ok" for r in CJD["rounds"][0]["members"])
      and UD["in"] == 90 and UD["out"] == 45 and UD["n_members_measured"] == 9 and UD["state"].startswith("partial (9 of 17")
      and CJD["requirements"] == [] and CJD["n_requirements"] is None and CJD["aggregation"] is None,
      f"rows={len(CJD['rounds'][0]['members'])} usage={UD['in']}/{UD['out']}")
evd = db.plan_events_after("p-die")
check("6c la traza conserva 9 'done' y ningún stage.council.round/aggregate ni council.state terminal",
      sum(1 for e in evd if e["type"] == "stage.council.member" and e["payload"]["phase"] == "done") == 9
      and not any(e["type"] in ("stage.council.round", "stage.council.aggregate") for e in evd)
      and [e for e in evd if e["type"] == "council.state"][-1]["payload"]["state"] == "running")

# ====================================================================================================================
# 7. reaper: latido viejo, latido fresco, carrera, arranque con umbral 0
# ====================================================================================================================
ahora = _now()
viejo = ahora - datetime.timedelta(seconds=2000)
db.create_plan("p-stale", "u1", "huérfano?", ["osr1"], PLAN_JSON, origin="smoke", council_state="running")
db.update_plan_council("p-stale", council_claimed_by="dead:1:council-worker-0", council_claimed_at=viejo,
                       council_started_at=viejo, council_last_event_at=viejo)
db.create_plan("p-fresh", "u1", "vivo?", ["osr1"], PLAN_JSON, origin="smoke", council_state="running")
db.update_plan_council("p-fresh", council_claimed_by="live:1:council-worker-0", council_claimed_at=ahora,
                       council_started_at=ahora, council_last_event_at=ahora)
db.create_plan("p-nodate", "u1", "sin latido?", ["osr1"], PLAN_JSON, origin="smoke", council_state="running")
db.update_plan_council("p-nodate", council_claimed_at=viejo)      # sin last_event_at ni started_at: cae a claimed_at
check("7a reap_stale_council_plans(900): siega la vieja (latido viejo) y la sin latido (cae a claimed_at); NO la fresca ni "
      "p-die (latido reciente)",
      sorted(db.reap_stale_council_plans(900, now=ahora, stale_s_source="smoke")) == ["p-nodate", "p-stale"]
      and db.get_plan("p-fresh")["council_state"] == "running" and db.get_plan("p-die")["council_state"] == "running")
PS = db.get_plan("p-stale")
evs_s = db.plan_events_after("p-stale")
check("7b la segada: council_state 'errored (worker-lost)' · council_finished_at · council_error 'worker-lost: …' · UN evento "
      "council.state {state, reason 'worker-lost', stale_s 900, stale_s_source, idle_s, ref_field 'council_last_event_at', "
      "claimed_by} agent 'council-reaper' level 'error' · estado ∈ vocabulario del consejo",
      PS["council_state"] == "errored (worker-lost)" and PS["council_finished_at"] is not None
      and PS["council_error"].startswith("worker-lost:") and len(evs_s) == 1 and evs_s[0]["agent"] == "council-reaper"
      and evs_s[0]["level"] == "error" and evs_s[0]["payload"]["reason"] == "worker-lost"
      and evs_s[0]["payload"]["ref_field"] == "council_last_event_at" and evs_s[0]["payload"]["stale_s"] == 900.0
      and evs_s[0]["payload"]["stale_s_source"] == "smoke" and evs_s[0]["payload"]["idle_s"] >= 2000
      and evs_s[0]["payload"]["claimed_by"] == "dead:1:council-worker-0"
      and council.council_state_in_vocabulary(PS["council_state"])
      and db.get_plan("p-nodate")["council_error"].startswith("worker-lost:"))
check("7c segunda pasada: nada que segar (idempotente); jamás re-encola (ningún plan volvió a 'queued')",
      db.reap_stale_council_plans(900, now=ahora) == []
      and db.count_plans_council(states=("queued",)) == 2)   # p-fifo-2, p-fixture (devueltos por el smoke) — y ninguno más
# carrera: el SELECT del reaper leyó un latido VIEJO pero el worker latió (la BD tiene uno fresco) → rowcount 0
_real_rows = db._council_running_rows
db._council_running_rows = lambda: [{"plan_id": "p-fresh", "council_last_event_at": viejo, "council_started_at": viejo,
                                     "council_claimed_at": viejo, "created_at": viejo, "council_claimed_by": "live"}]
carrera = db.reap_stale_council_plans(900, now=ahora)
db._council_running_rows = _real_rows
check("7d carrera reaper ↔ worker vivo: el UPDATE exige <ref_field> == lo leído → rowcount 0, no se toca, sin evento",
      carrera == [] and db.get_plan("p-fresh")["council_state"] == "running" and db.plan_events_count("p-fresh") == 0)
check("7e reason fuera de COUNCIL_REAP_REASONS → ValueError", _raises(lambda: db.reap_stale_council_plans(0, reason="x"), ValueError))
# arranque: umbral 0 → todo 'running' del proceso anterior es huérfano (p-die y p-fresh) → 'errored (worker-lost-restart)'
boot = cj.start_council_workers(n=0, reaper=False, env={**os.environ, "WITT_COUNCIL_ORIGINS": "smoke"})
PD2 = db.get_plan("p-die")
CJD2 = json.loads(PD2["council_json"])
check("7f start_council_workers: siega al arranque con umbral 0 ('worker-lost-restart') → p-die y p-fresh; 0 hilos con n=0; "
      "reaper=False (C5 lo integra en run-reaper); declaración con origins, REAP_STALE_S 900 y fuente",
      sorted(boot["reaped_at_boot"]) == ["p-die", "p-fresh"] and boot["n_workers"] == 0 and boot["threads"] == []
      and boot["reaper"] is False and boot["enabled"] is True and boot["origins"] == ["smoke"]
      and boot["reap_stale_s"] == 900 and boot["reap_stale_s_source"].startswith("default-unset")
      and PD2["council_state"] == "errored (worker-lost-restart)", json.dumps({k: boot[k] for k in ("reaped_at_boot", "origins")}))
check("7g la siega NO toca lo persistido: p-die conserva sus 9 filas y su usage (lo gastado antes de morir sigue en el registro)",
      len(CJD2["rounds"][0]["members"]) == 9 and json.loads(PD2["council_usage_json"])["in"] == 90
      and db.plan_events_after("p-die")[-1]["payload"]["reason"] == "worker-lost-restart")

# --- 7g. corrector ADR-0082 (E.2): el worker SOBREVIVE al veredicto del reaper (solape de contenedores en un redeploy) ------------
db.create_plan("p-race", "u1", "carrera worker↔reaper?", ["osr1"], PLAN_JSON, origin="smoke", council_state="queued")
row_race = db.claim_next_council_plan("boot:2:council-worker-0", origins=("smoke",), plan_id="p-race")
_reaped_mid = []


def _on_event_reap_mid(etype, payload):
    # a mitad de la ronda el proceso "nuevo" siega con umbral 0 ('worker-lost-restart') mientras este hilo sigue vivo
    if etype == "stage.council.member" and payload.get("phase") == "done" and not _reaped_mid:
        _reaped_mid.extend(db.reap_stale_council_plans(0, reason="worker-lost-restart", stale_s_source="smoke"))


res_race = cj.execute_round1(row_race, caller=fake_all_ok, cfg=cfg_fast, resolver=NOOP_RESOLVER, prior=NO_PRIOR,
                             on_event=_on_event_reap_mid)
PR = db.get_plan("p-race")
CJR = json.loads(PR["council_json"])
evr = db.plan_events_after("p-race")
check("7g corrector (E.2): el reaper sentenció 'errored (worker-lost-restart)' a media ronda y el worker TERMINÓ después → el cierre "
      "es CONDICIONAL a council_state='running' (rowcount 0): el estado terminal NO se pisa (sigue 'errored (worker-lost-restart)', "
      "council_error del reaper), council_json/council_usage_json SÍ se escriben (17 filas: lo gastado es medición), y queda UN "
      "evento council.state.conflict {attempted 'applicable', found 'errored (worker-lost-restart)', found_error, ignored True} — sin "
      "segundo council.state terminal; el resumen dice state_written False + conflict",
      _reaped_mid == ["p-race"] and PR["council_state"] == "errored (worker-lost-restart)"
      and PR["council_error"].startswith("worker-lost:") and len(CJR["rounds"][0]["members"]) == 17
      and res_race["state"] == "applicable" and res_race["state_written"] is False
      and res_race["conflict"]["attempted"] == "applicable" and res_race["conflict"]["found"] == "errored (worker-lost-restart)"
      and res_race["conflict"]["ignored"] is True
      and [e["type"] for e in evr].count("council.state.conflict") == 1
      and [e for e in evr if e["type"] == "council.state.conflict"][0]["payload"]["found"] == "errored (worker-lost-restart)"
      and [e for e in evr if e["type"] == "council.state.conflict"][0]["level"] == "warning"
      and [e for e in evr if e["type"] == "council.state"][-1]["payload"]["state"] == "errored (worker-lost-restart)"
      and not any(e["type"] == "council.state" and e["payload"]["state"] == "applicable" for e in evr),
      json.dumps({"state": PR["council_state"], "written": res_race["state_written"], "conflict": res_race["conflict"]}, default=str))
check("7h corrector (E.2): update_plan_council(expected_state=) es el UPDATE condicional — con el estado esperado equivocado rowcount 0 "
      "(False) y la fila NO cambia; con el correcto True",
      db.update_plan_council("p-race", expected_state="running", council_error="x") is False
      and db.get_plan("p-race")["council_error"].startswith("worker-lost:")
      and db.update_plan_council("p-race", expected_state="errored (worker-lost-restart)", council_error=PR["council_error"]) is True)

# ====================================================================================================================
# 8. excepción del worker → errored, hilo vivo (worker_loop procesa el siguiente)
# ====================================================================================================================
_real_agg = council.aggregate_r1
_agg_calls = []


def _agg_boom_once(round_result, **kw):
    _agg_calls.append(1)
    if len(_agg_calls) == 1:
        raise RuntimeError("agg boom (smoke)")
    return _real_agg(round_result, **kw)


council.aggregate_r1 = _agg_boom_once
stop_ev = threading.Event()
env_smoke = {**os.environ, "WITT_COUNCIL_ORIGINS": "smoke,fixture"}   # p-fixture (origin fixture) también entra a ESTE worker
th = threading.Thread(target=cj.worker_loop, name="council-worker-9",
                      kwargs={"poll_seconds": 0.05, "caller": fake_all_ok, "env": env_smoke, "stop": stop_ev, "max_jobs": 2,
                              "job_kwargs": {"resolver": NOOP_RESOLVER, "prior": NO_PRIOR, "cfg": cfg_fast}},
                      daemon=True)
th.start()          # en la cola (FIFO): p-fifo-2 (created antes) → agg boom; luego p-fixture → ok
th.join(30)
council.aggregate_r1 = _real_agg
stop_ev.set()
PE = db.get_plan("p-fifo-2")
CJE = json.loads(PE["council_json"])
PF = db.get_plan("p-fixture")
check("8a excepción del worker (aggregate_r1 lanza) → council_state 'errored (RuntimeError)' · council_error con el mensaje · "
      "council_json parcial con las 17 filas y usage medido · council_finished_at · evento council.state level error",
      PE["council_state"] == "errored (RuntimeError)" and "agg boom" in PE["council_error"]
      and len(CJE["rounds"][0]["members"]) == 17 and CJE["persisted"]["state"].startswith("partial (17 of 17")
      and CJE["error"].startswith("RuntimeError") and PE["council_finished_at"] is not None
      and json.loads(PE["council_usage_json"])["in"] == 170
      and db.plan_events_after("p-fifo-2")[-1]["level"] == "error"
      and db.plan_events_after("p-fifo-2")[-1]["payload"]["state"] == "errored (RuntimeError)"
      and council.council_state_in_vocabulary(PE["council_state"]), f"state={PE['council_state']!r}")
check("8b el hilo NO cayó: worker_loop siguió y procesó el siguiente job (p-fixture → 'applicable', claimed_by boot:pid:hilo, "
      "17 miembros) y terminó por max_jobs=2",
      not th.is_alive() and PF["council_state"] == "applicable" and PF["council_claimed_by"].endswith(":council-worker-9")
      and json.loads(PF["council_json"])["n_requirements"] == 16)
check("8c 'errored (<Tipo>)' se acota a la columna (40 chars): _errored_state con un tipo largo",
      len(cj._errored_state(type("X" * 60, (Exception,), {})())) <= 40)

# ====================================================================================================================
# 9. ledger, dedup, conteos, usage, create_run(council_json=)
# ====================================================================================================================
led = json.dumps({"state": "approved", "decisions": []})
check("9a set_plan_ledger antes del sello → True, council_ledger_json íntegro, council_approved_by/at (hora del servidor); "
      "con council_state='skipped-by-human' escribe la columna",
      db.set_plan_ledger("p-fixture", led, approved_by="u2") is True
      and db.get_plan("p-fixture")["council_ledger_json"] == led and db.get_plan("p-fixture")["council_approved_by"] == "u2"
      and db.get_plan("p-fixture")["council_approved_at"] is not None
      and db.set_plan_ledger("p-fifo-1", json.dumps({"state": "skipped-by-human"}), approved_by="u1",
                             council_state="skipped-by-human") is True
      and db.get_plan("p-fifo-1")["council_state"] == "skipped-by-human")
db.create_run("r-sealed", "u1", "q", [], council_json=json.dumps({"plan_id": "p-fixture", "r1_state": "applicable",
                                                                  "r1": json.loads(PF["council_json"]), "ledger": json.loads(led)}))
check("9b mark_plan_used sella; set_plan_ledger DESPUÉS del sello → False (409 plan_already_used en app) y no escribe",
      db.mark_plan_used("p-fixture", "r-sealed") is True and db.set_plan_ledger("p-fixture", "{}", approved_by="u1") is False
      and db.get_plan("p-fixture")["council_ledger_json"] == led and db.set_plan_ledger("no-plan", "{}") is False)
RR = db.get_run("r-sealed")
LR = {r["run_id"]: r for r in db.list_runs(limit=50)}
check("9c create_run(council_json=) persiste runs.council_json; get_run Y list_runs lo traen (lista == detalle); una corrida "
      "sin consejo lo trae NULL",
      RR["council_json"] is not None and json.loads(RR["council_json"])["r1_state"] == "applicable"
      and LR["r-sealed"]["council_json"] == RR["council_json"]
      and (db.create_run("r-plain", "u1", "q2", []) or True) and db.get_run("r-plain")["council_json"] is None
      and "council_json" in {r["run_id"]: r for r in db.list_runs(limit=50)}["r-plain"])
since = _now() - datetime.timedelta(seconds=600)
db.create_plan("p-dedup", "u1", "¿misma pregunta?", ["osr1", "lhx1a"], PLAN_JSON, origin="production", council_state="queued")
hit = db.plans_council_pending("u1", "¿misma pregunta?", "osr1,lhx1a", None, since)
check("9d plans_council_pending (dedup del doble clic): mismo usuario+pregunta+entities_csv+padre None y ventana → el plan "
      "vivo; otra entidad / otro usuario / otro padre / ventana futura / estado terminal → None",
      hit is not None and hit["plan_id"] == "p-dedup"
      and db.plans_council_pending("u1", "¿misma pregunta?", "osr1", None, since) is None
      and db.plans_council_pending("u2", "¿misma pregunta?", "osr1,lhx1a", None, since) is None
      and db.plans_council_pending("u1", "¿misma pregunta?", "osr1,lhx1a", "r-x", since) is None
      and db.plans_council_pending("u1", "¿misma pregunta?", "osr1,lhx1a", None, _now() + datetime.timedelta(seconds=5)) is None
      and db.plans_council_pending("u1", "muere?", "osr1", None, since) is None)   # p-die ya es errored
check("9e count_plans_council: u1 queued 1 (p-dedup) · u1 total con consejo 9 (incl. p-race del corrector 7g) · states None = "
      "council_state NOT NULL (el plan viejo p-old NO cuenta)",
      db.count_plans_council(user_id="u1", states=("queued",)) == 1 and db.count_plans_council(user_id="u1") == 9
      and db.count_plans_council() == 9 and db.count_plans_council(user_id="u2") == 0,
      f"{db.count_plans_council(user_id='u1')}")
use = db.plans_council_usage(None, None, None)
by_pid = {u["plan_id"]: u for u in use}
check("9f plans_council_usage: sólo planes con council_state (p-old fuera) · llaves {plan_id, user_id, created_at tz, origin, "
      "council_state, council_usage_json, run_id} · el consumido lleva run_id (app lo separa) · sin usage → NULL (no 0) · "
      "include_origins filtra y conserva NULL",
      "p-old" not in by_pid and set(by_pid["p-fifo-1"]) == {"plan_id", "user_id", "created_at", "origin", "council_state",
                                                              "council_usage_json", "run_id"}
      and by_pid["p-fifo-1"]["created_at"].tzinfo is not None and by_pid["p-fixture"]["run_id"] == "r-sealed"
      and by_pid["p-dedup"]["council_usage_json"] is None and json.loads(by_pid["p-fifo-1"]["council_usage_json"])["in"] == exp_in
      and {u["plan_id"] for u in db.plans_council_usage(None, None, ("production",))} == {"p-dedup"}
      and db.plans_council_usage(_now() + datetime.timedelta(seconds=5), None) == [])
pwc = db.plans_with_council(include_origins=None)
crc = db.closed_runs_with_council()
check("9g plans_with_council: los planes con council_json (5, incl. p-race: lo gastado se conservó tras la siega) con sus blobs; "
      "closed_runs_with_council: sólo corridas closed con runs.council_json (0 aquí: r-sealed sigue queued)",
      {p["plan_id"] for p in pwc} == {"p-fifo-1", "p-die", "p-fifo-2", "p-fixture", "p-race"}
      and all(p["council_json"] for p in pwc) and crc == [] and (db.update_run("r-sealed", state="closed") or True)
      and [r["run_id"] for r in db.closed_runs_with_council()] == ["r-sealed"], f"{sorted(p['plan_id'] for p in pwc)}")

# ====================================================================================================================
# 10. kill-switch WITT_COUNCIL=0
# ====================================================================================================================
env_off = {**os.environ, "WITT_COUNCIL": "0", "WITT_COUNCIL_ORIGINS": "smoke"}
_KS_CALLS = []


def fake_counting(req):
    _KS_CALLS.append(req["agent"])
    return fake_all_ok(req)


db.create_plan("p-ks", "u1", "apagado?", ["osr1"], PLAN_JSON, origin="smoke", council_state="queued")
n_before = db.plan_events_count("p-dedup")
ks_stop = threading.Event()
th_ks = threading.Thread(target=cj.worker_loop, kwargs={"poll_seconds": 0.02, "caller": fake_counting, "env": env_off,
                                                        "stop": ks_stop}, daemon=True)
th_ks.start()
time.sleep(0.25)
ks_stop.set()
th_ks.join(5)
check("10a worker_loop bajo kill-switch NO reclama: p-ks y p-dedup siguen 'queued', 0 llamadas, 0 eventos nuevos",
      db.get_plan("p-ks")["council_state"] == "queued" and db.get_plan("p-dedup")["council_state"] == "queued"
      and _KS_CALLS == [] and db.plan_events_count("p-dedup") == n_before and not th_ks.is_alive())
boot_off = cj.start_council_workers(env=env_off, caller=fake_counting)
check("10b start_council_workers bajo kill-switch: enabled False · 0 hilos · sin siega (reaped_at_boot []) · huérfanos "
      "DECLARADOS {queued 2, running 0} · regla declarada",
      boot_off["enabled"] is False and boot_off["n_workers"] == 0 and boot_off["threads"] == [] and boot_off["reaper"] is False
      and boot_off["reaped_at_boot"] == [] and boot_off["orphans"] == {"queued": 2, "running": 0}
      and boot_off["rule"].startswith("WITT_COUNCIL=0"), json.dumps(boot_off["orphans"]))
row_ks = db.claim_next_council_plan("boot:1:council-worker-0", origins=("smoke",), plan_id="p-ks")   # A MANO (el loop no lo haría)
res_ks = cj.execute_round1(row_ks, caller=fake_counting, env=env_off)
PK = db.get_plan("p-ks")
evk = db.plan_events_after("p-ks")
check("10c execute_round1 bajo kill-switch: 'disabled (kill-switch WITT_COUNCIL=0)' · CERO llamadas · CERO stage.council.* · "
      "un council.state con la razón · finished_at · council_json NULL (no se inventa ronda)",
      row_ks["plan_id"] == "p-ks" and res_ks["state"] == cj.STATE_DISABLED and res_ks["n_calls"] == 0 and _KS_CALLS == []
      and PK["council_state"] == "disabled (kill-switch WITT_COUNCIL=0)" and PK["council_finished_at"] is not None
      and PK["council_json"] is None and [e["type"] for e in evk] == ["council.state"]
      and evk[0]["payload"]["reason"].startswith("kill-switch") and council.council_state_in_vocabulary(PK["council_state"]))

# ====================================================================================================================
# 11. start_council_workers REAL (1 worker + reaper propio) procesa un job encolado; camino por DEFAULT de un job
# ====================================================================================================================
env_on = {**os.environ, "WITT_COUNCIL_ORIGINS": "production,smoke", "WITT_COUNCIL_WORKERS": "1"}
boot_on = cj.start_council_workers(env=env_on, caller=fake_all_ok, poll_seconds=0.05,
                                   job_kwargs={"resolver": NOOP_RESOLVER, "prior": NO_PRIOR, "cfg": cfg_fast})
alive0 = cj.status()["threads_alive"]
deadline = time.time() + 15
while time.time() < deadline and db.get_plan("p-dedup")["council_state"] in ("queued", "running"):
    time.sleep(0.05)
PDD = db.get_plan("p-dedup")
cj.stop_council_workers()
time.sleep(0.15)
check("11a start_council_workers(env WORKERS=1, ORIGINS production,smoke): hilos 'council-worker-0' + 'council-reaper' vivos; "
      "el job p-dedup (origin production) pasa a 'applicable' con claimed_by <boot>:<pid>:council-worker-0",
      boot_on["n_workers"] == 1 and boot_on["threads"] == ["council-worker-0", "council-reaper"] and boot_on["reaper"] is True
      and set(alive0) >= {"council-worker-0", "council-reaper"} and PDD["council_state"] == "applicable"
      and PDD["council_claimed_by"] == f"{cj.boot_id()}:{os.getpid()}:council-worker-0"
      and boot_on["origins"] == ["production", "smoke"] and boot_on["n_workers_source"].startswith("env:"),
      f"state={PDD['council_state']} claimed_by={PDD['council_claimed_by']}")
check("11b council_origins: default 'production' con fuente · 'all' → None (sin filtro declarado) · CSV tolerante · "
      "council_workers_n basura → default 1 declarado · reap_stale_s_of basura → 900 declarado",
      cj.council_origins({}) == (["production"], "default-unset:WITT_COUNCIL_ORIGINS")
      and cj.council_origins({"WITT_COUNCIL_ORIGINS": "ALL"})[0] is None
      and cj.council_origins({"WITT_COUNCIL_ORIGINS": " smoke , fixture,"})[0] == ["smoke", "fixture"]
      and cj.council_workers_n({"WITT_COUNCIL_WORKERS": "abc"}) == (1, "default-invalid-env:WITT_COUNCIL_WORKERS")
      and cj.council_workers_n({"WITT_COUNCIL_WORKERS": "0"})[0] == 0
      and cj.reap_stale_s_of({"WITT_REAP_STALE_S": "-5"}) == (900, "default-invalid-env:WITT_REAP_STALE_S")
      and cj.reap_stale_s_of({"WITT_REAP_STALE_S": "600"}) == (600, "env:WITT_REAP_STALE_S"))
# el camino por DEFAULT de un job (prior via council_index, resolver resolve_id — DATA INAMOVIBLE sólo lectura, inherited del padre)
db.create_plan("p-default", "u1", "Is osr1 required for pronephros?", ["osr1", "notagene"], PLAN_JSON, origin="smoke",
               council_state="queued")
row_def = db.claim_next_council_plan("boot:1:council-worker-0", origins=("smoke",), plan_id="p-default")
res_def = cj.execute_round1(row_def, caller=lambda req: _ok([_req(entities=["osr1", "notagene"])], usage={"input_tokens": 1, "output_tokens": 1})
                            if req["tool"] != council.FLAGS_TOOL_NAME else ({"applicable": True, "flags": []}, {"input_tokens": 1, "output_tokens": 1}, {}),
                            cfg=cfg_fast)
CJDEF = json.loads(db.get_plan("p-default")["council_json"])
import council_index  # noqa: E402
check("11c camino por default: prior_observations via council_index {state ∈ PRIOR_STATES, n == len(items), kinds sin 'comment'} · "
      "inherited_criteria_state 'not-applicable (root turn: no parent)' · entidades por resolve_id: osr1 resuelta, notagene "
      "sin resolver (jamás afirmada) · entities_resolution_state 'checked (resolve_id.resolve)'",
      res_def["state"] == "applicable" and CJDEF["prior_observations"]["state"] in council_index.PRIOR_STATES
      and isinstance(CJDEF["prior_observations"]["n"], int) and "comment" not in CJDEF["prior_observations"]["kinds"]
      and CJDEF["inherited_criteria_state"] == "not-applicable (root turn: no parent)"
      and CJDEF["requirements"][0]["entities_resolved"] == ["osr1"] and CJDEF["requirements"][0]["entities_unresolved"] == ["notagene"]
      and CJDEF["entities_resolution_state"] == "checked (resolve_id.resolve)", json.dumps(CJDEF["prior_observations"]))

# ====================================================================================================================
# 12. cero red · mcp_cache intacto · vocabulario
# ====================================================================================================================
check("12a urllib.request.urlopen REAL: 0 llamadas en todo el smoke", len(_URLOPEN_CALLS) == 0, f"{len(_URLOPEN_CALLS)}")
check("12b mcp_cache byte-idéntico (listado, tamaños y mtimes) antes y después", _mcp_cache_snapshot() == MCP_BEFORE)
estados = {db.get_plan(p)["council_state"] for p in ("p-fifo-1", "p-die", "p-stale", "p-fifo-2", "p-fixture", "p-ks", "p-dedup", "p-race")}
check("12c todos los council_state escritos por db/council_jobs ∈ vocabulario de lib.council (exactos + prefijos): "
      + ", ".join(sorted(estados)),
      all(council.council_state_in_vocabulary(s) for s in estados) and cj.STATE_DISABLED in council.COUNCIL_STATES_EXACT
      and cj.MODULE_VERSION == "council-jobs-1" and db.COUNCIL_PENDING_STATES == ("queued", "running"))

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
