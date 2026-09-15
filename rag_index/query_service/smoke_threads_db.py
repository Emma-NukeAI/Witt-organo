"""smoke_threads_db.py — gate determinista de la rebanada T1 (ADR-0079): la capa de DATOS de la
investigación (T-<run_no raíz>) en db.py.

Cubre: (a) migración aditiva e idempotente de las SIETE columnas (THREAD_COLUMNS) sobre una tabla runs
que YA existía sin ellas — corrida dos veces, mismo resultado; (b) las filas anteriores al ADR quedan
NULL en todas (ausencia declarada, sin backfill); (c) create_run persiste lo que el llamador deriva
(kwargs con default None: los llamadores viejos siguen funcionando) y rechaza un turn_kind fuera del
enum; (d) get_children / thread_turns / max_turn_no; (e) runs_by_thread paginable por run_no y por
created_at; (f) filtro opcional por origin en closed_runs / runs_usage / plan_history / question_calibration
con el CONTADOR de lo excluido (excluded_by_origin); (g) lista == detalle en las columnas nuevas.

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes — cero red, cero modelo, cero mutación de
la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre (con la máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-t1.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_threads_db.py
(si WITT_BACKEND_DB_URL no viene, se fija a ese archivo; el archivo previo se borra al arrancar.)
"""
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_default_db = SMOKES_DIR / "smoke-t1.db"
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def columnas_runs():
    with db.engine().begin() as cx:
        return {r[1] for r in cx.execute(text("PRAGMA table_info(runs)")).all()}


# ---- 0. Una tabla runs ANTERIOR al ADR-0079: se crea todo y se quitan las siete columnas ---------------
db.metadata.create_all(db.engine())
with db.engine().begin() as cx:
    for col in db.THREAD_COLUMNS:
        cx.execute(text(f"ALTER TABLE runs DROP COLUMN {col}"))
check("preámbulo: la tabla runs pre-ADR NO tiene ninguna de las 7 columnas",
      not (columnas_runs() & set(db.THREAD_COLUMNS)))

db.upsert_user("emmanuel", "Emmanuel", "dev", "x")
db.upsert_user("martin", "Martín", "medico", "x")

# dos corridas "viejas" insertadas con el esquema anterior (una cerrada con registro congelado)
_viejo_frozen = json.dumps({"answer": {"direct_answer": "old", "stated_confidence": 0.5},
                            "audit": {"verdict": "APPROVE", "n_valid": 3},
                            "confidence": {"state": "value", "final": 0.5}})
with db.engine().begin() as cx:
    cx.execute(text(
        "INSERT INTO runs (run_id, user_id, question, entities_csv, state, created_at, frozen_at, closed_by,"
        " cancel_requested, frozen_record_json, usage_json)"
        " VALUES ('old-closed', 'emmanuel', 'vieja cerrada', 'sox9b', 'closed',"
        " '2026-09-01 10:00:00.000000', '2026-09-01 11:00:00.000000', 'emmanuel', 0, :fr, :us)"),
        {"fr": _viejo_frozen, "us": json.dumps({"estimated_cost_usd": 0.10, "input_tokens": 10,
                                                 "output_tokens": 5, "embedding_tokens": 0})})
    cx.execute(text(
        "INSERT INTO runs (run_id, user_id, question, entities_csv, state, created_at, cancel_requested)"
        " VALUES ('old-failed', 'emmanuel', 'vieja fallida', '', 'failed',"
        " '2026-09-01 12:00:00.000000', 0)"))

# ---- 1. Migración aditiva e idempotente -----------------------------------------------------------------
db.init_db()
cols_1 = columnas_runs()
check("init_db (1a vez): las 7 columnas de THREAD_COLUMNS existen en runs",
      set(db.THREAD_COLUMNS) <= cols_1, f"faltan={set(db.THREAD_COLUMNS) - cols_1}")
db.init_db()
cols_2 = columnas_runs()
check("init_db (2a vez): idempotente — mismo conjunto de columnas, sin error", cols_1 == cols_2)
with db.engine().begin() as cx:
    idx = {r[1] for r in cx.execute(text("PRAGMA index_list(runs)")).all()}
check("índices ix_runs_thread_id / ix_runs_parent_run_id creados (IF NOT EXISTS)",
      {"ix_runs_thread_id", "ix_runs_parent_run_id"} <= idx, f"idx={sorted(idx)}")

# ---- 2. Filas viejas: NULL en las 7 = ausencia declarada, sin backfill ------------------------------------
viejo = db.get_run("old-closed")
check("fila pre-ADR: las 7 columnas son NULL en el detalle (sin backfill de hilo ni origin)",
      all(viejo.get(c) is None for c in db.THREAD_COLUMNS),
      str({c: viejo.get(c) for c in db.THREAD_COLUMNS}))
check("fila pre-ADR: run_no sí se backfilleó (ADR-0076) — el hilo NO (ADR-0079)",
      viejo["run_no"] in (1, 2) and viejo["thread_id"] is None)
en_lista = {r["run_id"]: r for r in db.list_runs()}
check("list_runs trae las 7 columnas y en la fila pre-ADR también son NULL",
      set(db.THREAD_COLUMNS) <= set(en_lista["old-closed"].keys())
      and all(en_lista["old-closed"][c] is None for c in db.THREAD_COLUMNS))

# ---- 3. create_run: llamador viejo y llamador ADR-0079 ---------------------------------------------------
no_legacy = db.create_run("legacy-1", "emmanuel", "sin kwargs nuevos", ["sox9b"])
leg = db.get_run("legacy-1")
check("create_run sin kwargs nuevos (llamador actual) sigue funcionando: devuelve run_no, 7 columnas NULL",
      isinstance(no_legacy, int) and all(leg.get(c) is None for c in db.THREAD_COLUMNS))

db.create_run("root-1", "emmanuel", "¿sox9b en cartílago?", ["sox9b"],
              thread_id="root-1", turn_no=1, turn_kind="root", origin="smoke",
              root_question_id="q-1")
raiz = db.get_run("root-1")
check("raíz: thread_id=run_id, turn_no=1, turn_kind='root', origin='smoke', root_question_id persistidos tal cual",
      raiz["thread_id"] == "root-1" and raiz["turn_no"] == 1 and raiz["turn_kind"] == "root"
      and raiz["origin"] == "smoke" and raiz["root_question_id"] == "q-1" and raiz["parent_run_id"] is None)

try:
    db.create_run("bad-kind", "emmanuel", "x", [], turn_kind="reply")
    check("turn_kind fuera de TURN_KINDS -> ValueError", False, "no levantó")
except ValueError as e:
    check("turn_kind fuera de TURN_KINDS -> ValueError", "ADR-0079" in str(e), str(e))
check("la fila con turn_kind inválido NO se insertó", db.get_run("bad-kind") is None)

# ---- 4. hijos y turnos -------------------------------------------------------------------------------------
ctx = json.dumps({"parent": {"run_id": "root-1"}, "excluded": ["ratings values and notes"]})
db.create_run("child-2", "martin", "¿sox9b en cartílago craneal?", ["sox9b"],
              parent_run_id="root-1", thread_id="root-1", turn_no=2, turn_kind="refine",
              thread_context_json=ctx, origin="smoke", root_question_id="q-1")
db.create_run("child-3", "emmanuel", "¿sox9b en cartílago?", ["sox9b"],
              parent_run_id="root-1", thread_id="root-1", turn_no=3, turn_kind="rerun",
              thread_context_json=ctx, origin="smoke", root_question_id="q-1")
db.create_run("child-4", "emmanuel", "¿sox9b y col2a1a?", ["sox9b", "col2a1a"],
              parent_run_id="child-2", thread_id="root-1", turn_no=4, turn_kind="branch",
              thread_context_json=ctx, origin="production", root_question_id="q-1")
# otro hilo, para que el filtro por thread_id se pruebe con ruido
db.create_run("root-9", "martin", "otra investigación", [], thread_id="root-9", turn_no=1,
              turn_kind="root", origin="smoke")

hijos = db.get_children("root-1")
check("get_children(root-1) = [child-2, child-3] en orden de creación (child-4 es nieto, no hijo)",
      [h["run_id"] for h in hijos] == ["child-2", "child-3"])
check("get_children de una corrida sin hijos = []", db.get_children("child-3") == [])

turnos = db.thread_turns("root-1")
check("thread_turns(root-1) = 4 turnos ordenados por turn_no; root-9 y legacy fuera",
      [t["run_id"] for t in turnos] == ["root-1", "child-2", "child-3", "child-4"]
      and [t["turn_no"] for t in turnos] == [1, 2, 3, 4])
check("max_turn_no(root-1) == 4 ; max_turn_no(hilo inexistente) is None",
      db.max_turn_no("root-1") == 4 and db.max_turn_no("no-existe") is None)
check("thread_turns trae thread_context_json (insumo del detalle) y closed_by (insumo de GET /threads)",
      turnos[1]["thread_context_json"] == ctx and "closed_by" in turnos[0])

# ---- 5. paginación --------------------------------------------------------------------------------------
p1 = db.runs_by_thread("root-1", limit=2)
check("runs_by_thread limit=2: 2 items, has_more=True, next_after = run_no del 2o (child-2)",
      p1["n"] == 2 and p1["has_more"] is True
      and [i["run_id"] for i in p1["items"]] == ["root-1", "child-2"]
      and p1["next_after"] == p1["items"][1]["run_no"], str(p1["next_after"]))
p2 = db.runs_by_thread("root-1", limit=2, after_run_no=p1["next_after"])
check("2a página (after_run_no=run_no; corrector: el cursor de biblioteca NO se llama `after` — ése es el turn_no exclusivo "
      "de GET /runs?thread=): [child-3, child-4], has_more=False, next_after=None",
      [i["run_id"] for i in p2["items"]] == ["child-3", "child-4"] and p2["has_more"] is False
      and p2["next_after"] is None)
p3 = db.runs_by_thread("root-1", after_run_no=p1["items"][1]["run_no"])
try:
    db.runs_by_thread("root-1", after_run_no=p1["items"][1]["created_at"].isoformat())
    _str_cursor_rejected = False
except ValueError:
    _str_cursor_rejected = True
check("after_run_no sin limit: los 2 posteriores a child-2, sin tope; un cursor que no es int (created_at ISO) -> ValueError "
      "(corrector: una sola semántica por función)",
      [i["run_id"] for i in p3["items"]] == ["child-3", "child-4"] and p3["limit"] is None
      and p3["has_more"] is False and _str_cursor_rejected)
todo = db.runs_by_thread("root-1")
check("runs_by_thread sin limit = los 4 turnos (con thread= no aplica el tope de la lista)",
      todo["n"] == 4 and todo["has_more"] is False)
check("runs_by_thread de un hilo inexistente = vacío declarado (n=0, has_more=False)",
      db.runs_by_thread("nada")["n"] == 0)
try:
    db.runs_by_thread("root-1", limit=0)
    check("limit=0 -> ValueError", False)
except ValueError:
    check("limit=0 -> ValueError", True)
try:
    db.list_runs(thread_id="root-1", limit=-1)
    check("corrector: db.list_runs(limit=-1) -> ValueError (LIMIT -1 = sin tope en SQLite, error en Postgres)", False)
except ValueError:
    check("corrector: db.list_runs(limit=-1) -> ValueError (LIMIT -1 = sin tope en SQLite, error en Postgres)", True)
# corrector: el índice ÚNICO (thread_id, turn_no) — dos filas con el mismo turno en el mismo hilo no caben
try:
    db.create_run("dup-turn-" + "d" * 23, "natalia", "dup", [], thread_id="root-1", turn_no=2, turn_kind="branch",
                  parent_run_id="root-1")
    check("corrector: ux_runs_thread_turn rechaza un (thread_id, turn_no) repetido (IntegrityError)", False)
except Exception as e:
    check("corrector: ux_runs_thread_turn rechaza un (thread_id, turn_no) repetido (IntegrityError)",
          type(e).__name__ == "IntegrityError" and "turn_no" in str(e).lower(), type(e).__name__)
check("corrector: db.has_children — True para root-1 (tiene hijos), False para child-4 (hoja) y para un run_id inexistente",
      db.has_children("root-1") is True and db.has_children("child-4") is False and db.has_children("nada") is False)
# la MISMA lista, vía list_runs (la forma que consume GET /runs?thread=&limit=&after=)
lt = db.list_runs(thread_id="root-1", limit=None)
check("list_runs(thread_id=, limit=None): los 4 turnos en orden turn_no ASC, sin tope",
      [r["run_id"] for r in lt] == ["root-1", "child-2", "child-3", "child-4"])
lt2 = db.list_runs(thread_id="root-1", limit=3, after=2)
check("list_runs(thread_id=, limit=3, after=2): cursor turn_no EXCLUSIVO -> [child-3, child-4]",
      [r["run_id"] for r in lt2] == ["child-3", "child-4"])
check("list_runs(thread_id=, user_id='martin') combina filtros -> [child-2]",
      [r["run_id"] for r in db.list_runs(thread_id="root-1", user_id="martin", limit=None)] == ["child-2"])
try:
    db.list_runs(after=1)
    check("list_runs(after=) sin thread_id -> ValueError (el cursor de turno no aplica a la lista general)", False)
except ValueError:
    check("list_runs(after=) sin thread_id -> ValueError (el cursor de turno no aplica a la lista general)", True)
check("list_runs() sin thread_id conserva el orden created_at DESC y el tope 50 por default",
      db.list_runs()[0]["run_id"] == "root-9" and len(db.list_runs(limit=2)) == 2)

# ---- 6. lista == detalle en las columnas nuevas ------------------------------------------------------------
lista = {r["run_id"]: r for r in db.list_runs(limit=100)}
desigual = []
for rid in ("old-closed", "old-failed", "legacy-1", "root-1", "child-2", "child-3", "child-4", "root-9"):
    det = db.get_run(rid)
    for c in db.THREAD_COLUMNS:
        if lista[rid][c] != det[c]:
            desigual.append((rid, c))
check("list_runs == get_run en las 7 columnas para las 8 corridas (paridad lista/detalle)",
      not desigual, str(desigual))
check("list_runs(user_id='martin') filtra y conserva las columnas nuevas",
      {r["run_id"] for r in db.list_runs(user_id="martin")} == {"child-2", "root-9"}
      and all(r["thread_id"] for r in db.list_runs(user_id="martin")))

# ---- 7. filtro por origin + contador de excluidos --------------------------------------------------------
# cerramos child-3 (smoke) y child-4 (production) para que el corpus de precedente tenga 3 cerradas:
# old-closed (origin NULL), child-3 (smoke), child-4 (production)
ahora = db._now()
for rid in ("child-3", "child-4"):
    db.update_run(rid, state="closed", frozen_at=ahora, closed_by="emmanuel",
                  frozen_record_json=_viejo_frozen,
                  usage_json=json.dumps({"estimated_cost_usd": 0.20, "input_tokens": 1,
                                         "output_tokens": 1, "embedding_tokens": 0}))
sin_filtro = db.closed_runs()
check("closed_runs() sin filtro = 3 cerradas y cada renglón trae origin/run_no/thread_id",
      {r["run_id"] for r in sin_filtro} == {"old-closed", "child-3", "child-4"}
      and all("origin" in r and "run_no" in r and "thread_id" in r for r in sin_filtro))
prod = db.closed_runs(include_origins=["production"])
check("closed_runs(include_origins=['production']) = child-4 + old-closed (NULL pre-ADR se INCLUYE); smoke fuera",
      {r["run_id"] for r in prod} == {"old-closed", "child-4"})
tally = db.excluded_by_origin(["production"], states=("closed",))
check("excluded_by_origin(['production'], closed): excluded={'smoke':1}, origin_unknown_included=1, n_included=2",
      tally == {"origins_included": ["production"], "excluded_by_origin": {"smoke": 1},
                "origin_unknown_included": 1, "n_included": 2}, str(tally))
tally_none = db.excluded_by_origin(None, states=("closed",))
check("excluded_by_origin(None): sin exclusión declarada (origins_included=None, excluded={}), n_included=3",
      tally_none["origins_included"] is None and tally_none["excluded_by_origin"] == {}
      and tally_none["n_included"] == 3)
with db.engine().begin() as cx:
    n_sin_unknown = cx.execute(db._origin_where(select(func.count()).select_from(db.runs)
                                                .where(db.runs.c.state == "closed"),
                                                ["production"], include_unknown=False)).scalar()
check("_origin_where(include_unknown=False) saca también las NULL: 1 cerrada (child-4)", n_sin_unknown == 1)

uso_todo = db.runs_usage()
uso_smoke = db.runs_usage(include_origins=["smoke"])
check("runs_usage: sin filtro 8 renglones con 'origin'; include_origins=['smoke'] = smoke + NULL (pre-ADR y legacy)",
      len(uso_todo) == 8 and all("origin" in r for r in uso_todo)
      and {r["run_id"] for r in uso_smoke} == {"root-1", "child-2", "child-3", "root-9",
                                                "old-closed", "old-failed", "legacy-1"},
      str(sorted(r["run_id"] for r in uso_smoke)))
ph = db.plan_history(include_origins=["production"])
check("plan_history(include_origins=['production']) = 2 (child-4 + old-closed NULL); sin filtro = 3",
      len(ph) == 2 and len(db.plan_history()) == 3)

# ---- 8. question_calibration con include_origins -----------------------------------------------------------
db.create_note("n-1", "emmanuel", "teoría", "cuerpo", "private")
for qid, rid in (("q-smoke", "child-3"), ("q-prod", "child-4"), ("q-old", "old-closed"), ("q-libre", None)):
    db.create_note_question(qid, "n-1", "emmanuel", "v1", "stub", "drafted", "p", [],
                            json.dumps({"fits_one_run": True}))
    if rid:
        db.mark_question_used(qid, rid)
qc_all = db.question_calibration()
qc_prod = db.question_calibration(include_origins=["production"])
v_all = qc_all["por_version"][0]
v_prod = qc_prod["por_version"][0]
check("question_calibration() sin filtro: 4 borradores, 3 usados, excluded_by_origin={} declarado",
      v_all["n_borradores"] == 4 and v_all["n_usados"] == 3 and qc_all["excluded_by_origin"] == {}
      and qc_all["origins_included"] is None)
check("question_calibration(['production']): 3 borradores (q-smoke fuera), 2 usados, excluded={'smoke':1}, unknown=1",
      v_prod["n_borradores"] == 3 and v_prod["n_usados"] == 2
      and qc_prod["excluded_by_origin"] == {"smoke": 1}
      and qc_prod["n_borradores_excluidos_por_origen"] == 1
      and qc_prod["origin_unknown_included"] == 1
      and qc_prod["origins_included"] == ["production"],
      json.dumps({k: qc_prod[k] for k in ("excluded_by_origin", "origin_unknown_included",
                                            "n_borradores_excluidos_por_origen")}))

# ---- 9. inmutabilidad: nada de lo anterior tocó la fila pre-ADR ------------------------------------------
viejo_2 = db.get_run("old-failed")
check("la fila pre-ADR 'old-failed' sigue NULL en las 7 tras todo el smoke (nadie backfilleó)",
      all(viejo_2.get(c) is None for c in db.THREAD_COLUMNS))

n_ok = sum(CHECKS)
print(f"\n== {n_ok}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_ok == len(CHECKS) else 1)
