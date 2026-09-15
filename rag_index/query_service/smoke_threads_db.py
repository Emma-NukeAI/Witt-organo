"""smoke_threads_db.py — gate determinista de la rebanada T1 (ADR-0079): la capa de DATOS de la
investigación (T-<run_no raíz>) en db.py.

Cubre: (a) migración aditiva e idempotente de las SIETE columnas (THREAD_COLUMNS) sobre una tabla runs
que YA existía sin ellas — corrida dos veces, mismo resultado; (b) las filas anteriores al ADR quedan
NULL en todas (ausencia declarada, sin backfill); (c) create_run persiste lo que el llamador deriva
(kwargs con default None: los llamadores viejos siguen funcionando) y rechaza un turn_kind fuera del
enum; (d) get_children / thread_turns / max_turn_no; (e) runs_by_thread paginable por run_no y por
created_at; (f) filtro opcional por origin en closed_runs / runs_usage / plan_history / question_calibration
con el CONTADOR de lo excluido (excluded_by_origin); (g) lista == detalle en las columnas nuevas.

ADR-0081 (S4 · BD): (h) `root_run_no` NACE en la BD por el JOIN a la raíz (`_root_join`): raíz == su run_no,
hijo y nieto == el de la raíz, corrida pre-ADR = NULL declarado (llave presente), hijo de raíz VIRTUAL
hereda el run_no del padre pre-ADR; lista == detalle == thread_turns/get_children/runs_by_thread por
construcción; SQL compilado para postgresql con exactamente UN LEFT OUTER JOIN; (i) `threads_index`: orden
root_run_no DESC NULLS LAST, n_turns/n_closed/authors/origins IGUALES a app.get_thread (misma verdad por dos
puertas, raíz virtual +1 declarada con root_counted false), cursor `after` exclusivo, has_more medido con
limit+1, tope declarado, `mine` (incluida la raíz virtual del usuario), errores tipados, SQL compilado para
postgresql sin funciones exclusivas de SQLite. LÍMITE DECLARADO: este gate NO mide la dependencia funcional
del GROUP BY (root.* sin agregar bajo GROUP BY root.run_id) — eso sólo lo mide Postgres (G7 / LG8).

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

# ---- 10. ADR-0081 (F): root_run_no NACE en la BD — JOIN a la raíz en _list_select y get_run -----------
# run_no medidos hasta aquí: old-closed 1 · old-failed 2 · legacy-1 3 · root-1 4 · child-2 5 · child-3 6 ·
# child-4 7 · root-9 8 (bad-kind y dup-turn no se insertaron).
from sqlalchemy.dialects import postgresql  # noqa: E402

raiz_f, hijo_f, nieto_f = db.get_run("root-1"), db.get_run("child-2"), db.get_run("child-4")
check("F · get_run(raíz): root_run_no == run_no (la raíz apunta a sí misma) == 4",
      raiz_f["root_run_no"] == raiz_f["run_no"] == 4, f"{raiz_f['root_run_no']} vs {raiz_f['run_no']}")
check("F · get_run(hijo) y get_run(nieto): root_run_no == 4 (el run_no de la raíz), no el propio",
      hijo_f["root_run_no"] == 4 and hijo_f["run_no"] == 5 and nieto_f["root_run_no"] == 4 and nieto_f["run_no"] == 7)
check("F · corridas pre-ADR (old-closed, old-failed, legacy-1): llave root_run_no PRESENTE y NULL declarado, jamás rellenada",
      all("root_run_no" in db.get_run(rid) and db.get_run(rid)["root_run_no"] is None
          for rid in ("old-closed", "old-failed", "legacy-1")))
# hijo de raíz VIRTUAL: old-closed es pre-ADR (thread_id NULL); su hijo lleva thread_id = 'old-closed'
db.create_run("virt-child", "martin", "¿sigue la vieja cerrada?", ["sox9b"], parent_run_id="old-closed",
              thread_id="old-closed", turn_no=2, turn_kind="refine", origin="smoke")
vc = db.get_run("virt-child")
check("F · hijo de raíz VIRTUAL: root_run_no == 1 (run_no de old-closed, hallada por run_id aunque su thread_id sea NULL); "
      "la propia old-closed sigue NULL",
      vc["root_run_no"] == 1 and vc["run_no"] == 9 and db.get_run("old-closed")["root_run_no"] is None,
      f"virt-child root_run_no={vc['root_run_no']} run_no={vc['run_no']}")
lista_f = {r["run_id"]: r for r in db.list_runs(limit=100)}
with db.engine().begin() as cx:
    n_total_runs = cx.execute(select(func.count()).select_from(db.runs)).scalar()
check("F · list_runs == get_run en root_run_no para las 9 corridas (misma definición _root_join: paridad lista/detalle)",
      len(lista_f) == n_total_runs == 9
      and all(lista_f[rid]["root_run_no"] == db.get_run(rid)["root_run_no"] for rid in lista_f),
      str({rid: (lista_f[rid]["root_run_no"], db.get_run(rid)["root_run_no"]) for rid in lista_f}))
check("F · OUTER: el JOIN no quita filas (list_runs(limit=100) == COUNT(*) runs == 9)", len(lista_f) == 9)
check("F · thread_turns / get_children / runs_by_thread sirven root_run_no (todas pasan por _list_select)",
      all(t["root_run_no"] == 4 for t in db.thread_turns("root-1"))
      and all(h["root_run_no"] == 4 for h in db.get_children("root-1"))
      and all(i["root_run_no"] == 4 for i in db.runs_by_thread("root-1", limit=2)["items"])
      and [t["run_id"] for t in db.thread_turns("root-1")] == ["root-1", "child-2", "child-3", "child-4"])
check("F · thread_turns(old-closed) = sólo el hijo (la raíz virtual NO está en el hilo: thread_id NULL) con root_run_no 1",
      [t["run_id"] for t in db.thread_turns("old-closed")] == ["virt-child"]
      and db.thread_turns("old-closed")[0]["root_run_no"] == 1)
check("F · root_run_no NO es columna de runs (nace del JOIN, nadie la escribe ni la backfillea)",
      "root_run_no" not in db.runs.c)
check("F · las fechas siguen normalizadas a UTC en lista y detalle tras el JOIN",
      lista_f["root-1"]["created_at"].tzinfo is not None and raiz_f["created_at"].tzinfo is not None)
_pg = postgresql.dialect()
sql_l = str(db._list_select().compile(dialect=_pg))
sql_d = str(db._detail_select().compile(dialect=_pg))
_JOIN = "FROM runs LEFT OUTER JOIN runs AS root ON root.run_id = runs.thread_id"
check("F · SQL (postgresql): lista y detalle llevan exactamente UN 'LEFT OUTER JOIN runs AS root' y 'root.run_no AS root_run_no'",
      sql_l.count(_JOIN) == 1 and sql_d.count(_JOIN) == 1
      and sql_l.count("root.run_no AS root_run_no") == 1 and sql_d.count("root.run_no AS root_run_no") == 1)
check("F · SQL: la frontera de blobs sigue — el detalle trae bundle_json/frozen_record_json, la lista no",
      "runs.bundle_json" in sql_d and "runs.frozen_record_json" in sql_d
      and "runs.bundle_json" not in sql_l and "runs.frozen_record_json" not in sql_l)
check("F · closed_runs / runs_usage no pasan por _list_select y NO traen root_run_no (declarado: sus consumidores no lo piden)",
      all("root_run_no" not in r for r in db.closed_runs()) and all("root_run_no" not in r for r in db.runs_usage()))

# ---- 11. ADR-0081 (G): threads_index — el índice de investigaciones con denominador -------------------
# Hilos: root-1 (raíz real run_no 4, 4 turnos) · root-9 (raíz real 8, 1 turno) · old-closed (raíz VIRTUAL
# run_no 1: 1 turno contado + la raíz virtual). Orden esperado root_run_no DESC: root-9, root-1, old-closed.
ix = db.threads_index()
check("G · sobre: llaves EXACTAS (THREADS_INDEX_ENVELOPE_FIELDS) y serializable a JSON",
      tuple(ix.keys()) == db.THREADS_INDEX_ENVELOPE_FIELDS and json.dumps(ix) is not None,
      str(tuple(ix.keys())))
check("G · fila: llaves EXACTAS y en orden (THREADS_INDEX_ROW_FIELDS)",
      all(tuple(f.keys()) == db.THREADS_INDEX_ROW_FIELDS for f in ix["threads"]),
      str(tuple(ix["threads"][0].keys())) if ix["threads"] else "sin filas")
check("G · orden root_run_no DESC: [root-9 (8), root-1 (4), old-closed (1)]; n 3; has_more false; next_after null",
      [f["thread_id"] for f in ix["threads"]] == ["root-9", "root-1", "old-closed"]
      and [f["root_run_no"] for f in ix["threads"]] == [8, 4, 1] and ix["n"] == 3
      and ix["has_more"] is False and ix["next_after"] is None,
      str([(f["thread_id"], f["root_run_no"]) for f in ix["threads"]]))
check("G · denominadores: n_threads_total 3 · n_runs_without_thread 3 == count_runs_without_thread() (old-closed, old-failed, "
      "legacy-1: la raíz virtual ES una corrida sin hilo y se declara) · limit 50 · limit_cap 50 · after null · mine false",
      ix["n_threads_total"] == 3 and ix["n_runs_without_thread"] == db.count_runs_without_thread() == 3
      and ix["limit"] == 50 and ix["limit_cap"] == 50 and ix["after"] is None and ix["mine"] is False
      and "raíces VIRTUALES" in ix["n_runs_without_thread_rule"])
check("G · costs 'not-aggregated (GET /threads/{id})' y order/cursor_rule/mine_rule/n_turns_rule declarados (str)",
      ix["costs"] == "not-aggregated (GET /threads/{id})" and ix["order"] == "root_run_no DESC NULLS LAST, thread_id ASC"
      and all(isinstance(ix[k], str) and ix[k] for k in ("cursor_rule", "mine_rule", "n_turns_rule")))
r1 = ix["threads"][1]
check("G · root-1: label T-4, root real (root_pre_adr_0079 false, root_counted true), n_turns 4, n_closed 2, n_with_record 2, "
      "n_turns_without_record 2, last_turn_no 4",
      r1["label"] == "T-4" and r1["root_run_id"] == "root-1" and r1["root_pre_adr_0079"] is False
      and r1["root_counted"] is True and r1["n_turns"] == 4 and r1["n_closed"] == 2 and r1["n_with_record"] == 2
      and r1["n_turns_without_record"] == 2 and r1["last_turn_no"] == 4,
      json.dumps({k: r1[k] for k in ("label", "root_pre_adr_0079", "root_counted", "n_turns", "n_closed",
                                      "n_with_record", "n_turns_without_record", "last_turn_no")}))
check("G · root-1: raíz {question, user_id, state, root_question_id} desde la fila raíz; last_turn = child-4 (run_no 7, turno 4, closed)",
      r1["root_question"] == "¿sox9b en cartílago?" and r1["root_user_id"] == "emmanuel" and r1["root_state"] == "queued"
      and r1["root_question_id"] == "q-1"
      and r1["last_turn"] == {"run_id": "child-4", "run_no": 7, "turn_no": 4, "state": "closed"}, str(r1["last_turn"]))
check("G · root-1: authors ordenados ['emmanuel','martin'], origins {'smoke':3,'production':1}, states {'queued':2,'closed':2} "
      "(agregación en Python sobre la consulta ligera, sin group_concat)",
      r1["authors"] == ["emmanuel", "martin"] and r1["origins"] == {"smoke": 3, "production": 1}
      and r1["states"] == {"queued": 2, "closed": 2}, json.dumps([r1["authors"], r1["origins"], r1["states"]]))
check("G · root-1: first/last_created_at son ISO con zona (+00:00) y first <= last",
      isinstance(r1["first_created_at"], str) and r1["first_created_at"].endswith("+00:00")
      and r1["first_created_at"] <= r1["last_created_at"], f"{r1['first_created_at']} .. {r1['last_created_at']}")
rv = ix["threads"][2]
check("G · old-closed (raíz VIRTUAL): root_pre_adr_0079 true, root_counted false, label T-1, n_turns 2 (1 contado + la raíz virtual), "
      "n_closed 1 (la raíz cerrada), n_with_record 1, n_turns_without_record 1, last_turn virt-child",
      rv["root_pre_adr_0079"] is True and rv["root_counted"] is False and rv["label"] == "T-1"
      and rv["root_run_id"] == "old-closed" and rv["n_turns"] == 2 and rv["n_closed"] == 1
      and rv["n_with_record"] == 1 and rv["n_turns_without_record"] == 1 and rv["last_turn_no"] == 2
      and rv["last_turn"]["run_id"] == "virt-child",
      json.dumps({k: rv[k] for k in ("root_pre_adr_0079", "root_counted", "label", "n_turns", "n_closed",
                                      "n_with_record", "n_turns_without_record", "last_turn_no")}))
check("G · old-closed: la raíz virtual entra a authors/origins/states — authors ['emmanuel','martin'], origins "
      "{'smoke':1,'unknown-pre-adr-0079':1} (origin NULL etiquetado, no rellenado), states {'closed':1,'queued':1}; "
      "first_created_at = el de la raíz (2026-09-01T10:00)",
      rv["authors"] == ["emmanuel", "martin"] and rv["origins"] == {"smoke": 1, db.ORIGIN_UNKNOWN_LABEL: 1}
      and rv["states"] == {"closed": 1, "queued": 1} and rv["first_created_at"].startswith("2026-09-01T10:00:00")
      and rv["root_state"] == "closed" and rv["root_question"] == "vieja cerrada" and rv["root_question_id"] is None,
      json.dumps([rv["authors"], rv["origins"], rv["states"], rv["first_created_at"]]))
r9 = ix["threads"][0]
check("G · root-9: hilo de un solo turno — n_turns 1, label T-8, authors ['martin'], last_turn = la raíz misma",
      r9["n_turns"] == 1 and r9["label"] == "T-8" and r9["authors"] == ["martin"] and r9["origins"] == {"smoke": 1}
      and r9["last_turn"]["run_id"] == "root-9" and r9["root_counted"] is True)

# paridad con la OTRA puerta: app.get_thread (misma verdad por dos puertas) — se importa aquí, con la máscara puesta
import app as app_mod  # noqa: E402
_tok = "Bearer " + db.create_session("emmanuel")["token"]
_PARIDAD = ("root_run_id", "root_run_no", "label", "root_pre_adr_0079", "n_turns", "n_closed", "n_turns_without_record",
            "authors", "origins", "root_question_id")
_dif = []
for f in ix["threads"]:
    gt = app_mod.get_thread(f["thread_id"], authorization=_tok)
    for k in _PARIDAD:
        if f[k] != gt[k]:
            _dif.append((f["thread_id"], k, f[k], gt[k]))
check("G · PARIDAD threads_index == app.get_thread en {root_run_id, root_run_no, label, root_pre_adr_0079, n_turns, n_closed, "
      "n_turns_without_record, authors, origins, root_question_id} para los 3 hilos (incluida la raíz virtual +1)",
      not _dif, str(_dif))

# cursor exclusivo y has_more medido con limit+1
p1 = db.threads_index(limit=1)
p2 = db.threads_index(limit=1, after=p1["next_after"])
p3 = db.threads_index(limit=1, after=p2["next_after"])
p4 = db.threads_index(after=1)
check("G · limit=1: [root-9], has_more true (medido con limit+1), next_after 8; after=8 → [root-1], next_after 4; "
      "after=4 → [old-closed], has_more false, next_after null; after=1 → vacío declarado (n 0) con n_threads_total 3",
      [f["thread_id"] for f in p1["threads"]] == ["root-9"] and p1["has_more"] is True and p1["next_after"] == 8
      and [f["thread_id"] for f in p2["threads"]] == ["root-1"] and p2["has_more"] is True and p2["next_after"] == 4
      and p2["after"] == 8
      and [f["thread_id"] for f in p3["threads"]] == ["old-closed"] and p3["has_more"] is False and p3["next_after"] is None
      and p4["n"] == 0 and p4["threads"] == [] and p4["has_more"] is False and p4["n_threads_total"] == 3,
      f"p1={[f['thread_id'] for f in p1['threads']]}/{p1['next_after']} p2={[f['thread_id'] for f in p2['threads']]}/{p2['next_after']} "
      f"p3={[f['thread_id'] for f in p3['threads']]} p4.n={p4['n']}")
check("G · limit=2 → has_more true y next_after 4; limit=3 → has_more false (limit+1 medido, jamás estimado)",
      db.threads_index(limit=2)["has_more"] is True and db.threads_index(limit=2)["next_after"] == 4
      and db.threads_index(limit=3)["has_more"] is False)
check("G · el tope manda y se declara: limit=500 → limit 50, limit_cap 50; limit=None → 50",
      db.threads_index(limit=500)["limit"] == 50 and db.threads_index(limit=None)["limit"] == 50)


def _raises(fn, exc):
    try:
        fn()
        return False
    except exc:
        return True


check("G · errores tipados: limit 0 / -1 / '5' → ValueError; after '8' / True / 1.5 → ValueError (la puerta los vuelve 400/422)",
      _raises(lambda: db.threads_index(limit=0), ValueError) and _raises(lambda: db.threads_index(limit=-1), ValueError)
      and _raises(lambda: db.threads_index(limit="5"), ValueError)
      and _raises(lambda: db.threads_index(after="8"), ValueError) and _raises(lambda: db.threads_index(after=True), ValueError)
      and _raises(lambda: db.threads_index(after=1.5), ValueError))
# mine: ≥ 1 turno del usuario — la raíz virtual del usuario cuenta
mm = db.threads_index(user_id="martin")
me = db.threads_index(user_id="emmanuel")
mn = db.threads_index(user_id="natalia")
check("G · mine=martin: [root-9 (raíz suya), root-1 (child-2 suyo), old-closed (virt-child suyo)], n_threads_total 3, mine true; "
      "natalia (sin turnos): 0 hilos, total 0, mine true",
      [f["thread_id"] for f in mm["threads"]] == ["root-9", "root-1", "old-closed"] and mm["n_threads_total"] == 3
      and mm["mine"] is True and mn["n"] == 0 and mn["n_threads_total"] == 0 and mn["mine"] is True,
      f"martin={[f['thread_id'] for f in mm['threads']]} natalia.n={mn['n']}")
check("G · mine=emmanuel: [root-1, old-closed] — old-closed entra por la RAÍZ VIRTUAL (root.user_id), no por un turno del grupo",
      [f["thread_id"] for f in me["threads"]] == ["root-1", "old-closed"] and me["n_threads_total"] == 2,
      str([f["thread_id"] for f in me["threads"]]))
# root_question truncada a 120 (una raíz nueva con 200 chars: queda primera en el orden)
db.create_run("root-long", "natalia", "¿" + "x" * 199, [], thread_id="root-long", turn_no=1, turn_kind="root", origin="smoke")
rl = db.threads_index(limit=1)["threads"][0]
check("G · root_question se recorta a ROOT_QUESTION_MAX (120) y la raíz nueva (run_no 10) encabeza el orden",
      rl["thread_id"] == "root-long" and len(rl["root_question"]) == 120 == db.ROOT_QUESTION_MAX and rl["root_run_no"] == 10
      and db.threads_index()["n_threads_total"] == 4, f"len={len(rl['root_question'])} run_no={rl['root_run_no']}")
# SQL compilado para postgresql: dialecto neutral (declarado: NO se mide la dependencia funcional del GROUP BY)
_q, _root = db._threads_index_query("u", 5)
sql_g = str(_q.compile(dialect=_pg))
sql_light = str(db._threads_index_light_query(["a", "b"]).compile(dialect=_pg))
_SQLITE_ONLY = ("group_concat", "ifnull(", "julianday", "strftime", "datetime(", "||")
check("G · SQL (postgresql) de threads_index: 'GROUP BY runs.thread_id, root.run_id' (PK del alias: dependencia funcional, que este "
      "gate NO mide — G7/LG8 en Postgres), LEFT OUTER JOIN, WHERE thread_id IS NOT NULL, cursor 'root.run_no <', "
      "sin funciones exclusivas de SQLite; la consulta ligera compila sin blobs",
      "GROUP BY runs.thread_id, root.run_id" in sql_g and _JOIN in sql_g and "runs.thread_id IS NOT NULL" in sql_g
      and "root.run_no <" in sql_g and "root.user_id =" in sql_g
      and not any(s in sql_g.lower() for s in _SQLITE_ONLY) and not any(s in sql_light.lower() for s in _SQLITE_ONLY)
      and "frozen_record_json" not in sql_light and "bundle_json" not in sql_light and "thread_context_json" not in sql_light
      and "count(runs.frozen_record_json)" in sql_g,
      sql_g[:200])
check("G · el NULLS LAST se emula con CASE (una definición SQLite/Postgres) y la consulta de la página compila en ambos dialectos",
      "ORDER BY CASE WHEN (root.run_no IS NULL) THEN 1 ELSE 0 END, root.run_no DESC" in str(
          _q.order_by(db.case((_root.c.run_no.is_(None), 1), else_=0), _root.c.run_no.desc())
          .compile(dialect=_pg, compile_kwargs={"literal_binds": True}))
      and "NULLS" not in sql_g and str(_q.compile(dialect=db.engine().dialect)))

n_ok = sum(CHECKS)
print(f"\n== {n_ok}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_ok == len(CHECKS) else 1)
