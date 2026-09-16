"""smoke_web_quota_db.py — gate determinista de la CUOTA MENSUAL del localizador web (ADR-0084 (H), rebanada W7 · BD): la tabla
`web_locator_usage` y `db.web_locator_reserve` / `web_locator_month_to_date` / `web_locator_usage_months` — el contador LOCAL de
consultas ENVIADAS por este despliegue (mes calendario UTC × proveedor). Molde: smoke_config_ledger_db.py.

Cubre: (a) create_all crea la tabla con las columnas EXACTAS del ADR y la UNIQUE (month, provider), sin ALTER (idempotente; _migrate
no la menciona); DDL compilado para postgresql (SERIAL, TIMESTAMP WITH TIME ZONE, FLOAT); (b) reserve × cap → granted n
veces y luego False con n_after == cap (UPDATE condicional: rowcount 1 = granted); (c) 8 hilos concurrentes sobre la MISMA fila →
EXACTAMENTE cap granted (atómico, sin carrera); (d) otro mes / otro proveedor = otra fila (no cuenta); (e) cap 0 = sin tope DECLARADO
(cuenta, granted siempre); (f) record= suma n_results y cost_usd_projected sobre la fila y NO reserva (granted None); (g) month_to_date
con y sin fila (ceros MEDIDOS + row_present False); usage_months ordenadas; (h) SQL PORTABLE: la sección (H) de db.py no usa RETURNING ni
ON CONFLICT; (i) la costura REAL con web_locator.locate (W2): quota_fn=db.web_locator_reserve con cap 1 → 1ª consulta 'under-cap'
(proveedor fake llamado), 2ª 'skipped-cap' con detail y CERO llamadas al proveedor; la fila del mes queda en 1; (j) cero red.

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes — cero red (urlopen bloqueado y contado), cero modelo, cero mutación
de la DATA INAMOVIBLE ni de mcp_cache (WITT_MCP_CACHE_DIR temporal). Exit 0 = todo PASS.

Corre (con la máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr84-smoke_web_quota_db.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" BRAVE_API_KEY="" WITT_RUN_ORIGIN=smoke
  WITT_MCP_CACHE_DIR=<tmp> python rag_index/query_service/smoke_web_quota_db.py
(si WITT_BACKEND_DB_URL no viene, se fija a ese archivo; el archivo previo se borra al arrancar.)
"""
import inspect
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_default_db = SMOKES_DIR / "adr84-smoke_web_quota_db.db"
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
os.environ.setdefault("BRAVE_API_KEY", "")
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")
if not (os.environ.get("WITT_MCP_CACHE_DIR") or "").strip():
    os.environ["WITT_MCP_CACHE_DIR"] = tempfile.mkdtemp(prefix="witt-smoke-web-quota-")

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------------------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    req = a[0] if a else kw.get("url")
    _NET_CALLS.append(str(getattr(req, "full_url", None) or req)[:120])
    raise RuntimeError("network blocked by smoke_web_quota_db (offline gate)")


_urlreq.urlopen = _urlopen_blocked

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
import db  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _row(month, provider):
    with db.engine().begin() as cx:
        r = cx.execute(text("SELECT n_queries, n_results, cost_usd_projected FROM web_locator_usage WHERE month=:m AND provider=:p"),
                       {"m": month, "p": provider}).first()
    return tuple(r) if r else None


def _n_rows():
    with db.engine().begin() as cx:
        return cx.execute(text("SELECT COUNT(*) FROM web_locator_usage")).scalar()


# ---- 1. create_all crea la tabla; columnas EXACTAS; UNIQUE; sin ALTER; idempotente; DDL Postgres -------------------------------
check("antes de init_db: web_locator_usage_table_exists() False (BD fresca) — insumo de /usage.web_locator.month_to_date.state 'table-missing'",
      db.web_locator_usage_table_exists() is False)
db.init_db()
with db.engine().begin() as cx:
    cols = [r[1] for r in cx.execute(text("PRAGMA table_info(web_locator_usage)")).all()]
    idx = cx.execute(text("PRAGMA index_list(web_locator_usage)")).all()
    uniq_cols = []
    for i in idx:
        if i[2]:   # unique
            uniq_cols.append(tuple(r[2] for r in cx.execute(text(f"PRAGMA index_info({i[1]})")).all()))
check("init_db: la tabla EXISTE con las columnas EXACTAS del ADR (id, month, provider, n_queries, n_results, cost_usd_projected, updated_at) "
      "y UNA UNIQUE (month, provider); db.WEB_LOCATOR_USAGE_TABLE/FIELDS declarados",
      db.web_locator_usage_table_exists() is True
      and cols == ["id", "month", "provider", "n_queries", "n_results", "cost_usd_projected", "updated_at"]
      and ("month", "provider") in uniq_cols
      and db.WEB_LOCATOR_USAGE_TABLE == "web_locator_usage"
      and db.WEB_LOCATOR_USAGE_FIELDS == ("month", "provider", "n_queries", "n_results", "cost_usd_projected", "updated_at"),
      f"cols={cols} uniq={uniq_cols}")
_n0 = _n_rows()
db.init_db()   # idempotente
_src_migrate = inspect.getsource(db._migrate)
_ddl_pg = str(CreateTable(db.web_locator_usage).compile(dialect=postgresql.dialect()))
check("init_db idempotente (segunda llamada no altera filas) · _migrate NO menciona la tabla (nace por create_all, sin ALTER) · DDL compilado "
      "para postgresql: SERIAL, TIMESTAMP WITH TIME ZONE, FLOAT, UNIQUE (month, provider)",
      _n_rows() == _n0 == 0 and "web_locator_usage" not in _src_migrate
      and "SERIAL" in _ddl_pg and "TIMESTAMP WITH TIME ZONE" in _ddl_pg and "cost_usd_projected FLOAT" in _ddl_pg
      and "UNIQUE (month, provider)" in _ddl_pg, _ddl_pg.replace("\n", " ")[:300])

# ---- 2. reserve × cap: granted n veces, luego False con n_after == cap ------------------------------------------------------------
M = "2025-03"        # meses PASADOS: la fila del mes UTC en curso queda libre para la costura con web_locator.locate (abajo)
res = [db.web_locator_reserve("brave", M, 3) for _ in range(4)]
check("reserve(cap 3) × 4: granted True, True, True, False; n_before 0,1,2,3; n_after 1,2,3,3 (== cap: el UPDATE condicional devolvió "
      "rowcount 0); cap eco 3; la fila del mes nace idempotente (1 fila)",
      [r["granted"] for r in res] == [True, True, True, False]
      and [r["n_before"] for r in res] == [0, 1, 2, 3] and [r["n_after"] for r in res] == [1, 2, 3, 3]
      and all(r["cap"] == 3 for r in res) and _row(M, "brave") == (3, 0, 0.0) and _n_rows() == 1,
      repr(res))
check("reserve devuelve EXACTAMENTE {granted, n_before, n_after, cap} (la forma que web_locator.locate consume)",
      all(set(r) == {"granted", "n_before", "n_after", "cap"} for r in res))

# ---- 3. concurrencia: 8 hilos sobre la MISMA fila con cap 5 → EXACTAMENTE 5 granted --------------------------------------------
M2 = "2025-04"
_granted, _lock, _errors = [], threading.Lock(), []
_barrier = threading.Barrier(8)


def _worker():
    try:
        _barrier.wait(timeout=10)
        r = db.web_locator_reserve("brave", M2, 5)
        with _lock:
            _granted.append(bool(r["granted"]))
    except Exception as e:   # pragma: no cover
        with _lock:
            _errors.append(f"{type(e).__name__}: {e}")


ths = [threading.Thread(target=_worker) for _ in range(8)]
for t in ths:
    t.start()
for t in ths:
    t.join(timeout=30)
check("8 hilos concurrentes con cap 5 (barrera de salida) → EXACTAMENTE 5 granted y 3 denegados, fila n_queries 5, 0 excepciones "
      "(UPDATE … WHERE n_queries < cap es atómico: sin sobregiro ni doble conteo)",
      sum(_granted) == 5 and len(_granted) == 8 and _row(M2, "brave") == (5, 0, 0.0) and not _errors,
      f"granted={sum(_granted)}/{len(_granted)} row={_row(M2, 'brave')} errors={_errors}")

# ---- 4. otro mes / otro proveedor = otra fila -----------------------------------------------------------------------------------
r_old = db.web_locator_reserve("brave", "2025-02", 3)
r_anth = db.web_locator_reserve("anthropic", M, 3)
check("otro mes ('2025-02') y otro proveedor ('anthropic', mismo mes) NO cuentan contra la fila brave/2025-03 (tope alcanzado): ambos granted "
      "True con n_after 1 en SU fila; la fila brave/2025-03 sigue en 3; 4 filas en la tabla",
      r_old["granted"] is True and r_old["n_after"] == 1 and r_anth["granted"] is True and r_anth["n_after"] == 1
      and _row(M, "brave") == (3, 0, 0.0) and _n_rows() == 4, f"old={r_old} anth={r_anth} n={_n_rows()}")

# ---- 5. cap 0 = sin tope declarado ---------------------------------------------------------------------------------------------
res0 = [db.web_locator_reserve("brave", "2025-01", 0) for _ in range(3)]
check("cap 0 (WITT_WEB_MONTHLY_CAP=0 = sin tope DECLARADO): granted True siempre y el contador SIGUE contando (n_after 1, 2, 3) — el gasto "
      "se declara, no se frena (web_locator.locate lo etiqueta 'disabled (WITT_WEB_MONTHLY_CAP=0)')",
      [r["granted"] for r in res0] == [True, True, True] and [r["n_after"] for r in res0] == [1, 2, 3]
      and all(r["cap"] == 0 for r in res0), repr(res0))

# ---- 6. record= suma n_results / cost sobre la fila y NO reserva ---------------------------------------------------------------
rr1 = db.web_locator_reserve("brave", M, 3, record={"n_results": 7, "cost": 0.005})
rr2 = db.web_locator_reserve("brave", M, 3, record={"n_results": 3, "cost": 0.005})
check("record={n_results, cost} (tras la llamada) SUMA sobre la fila (n_results 10, cost_usd_projected 0.01) sin tocar n_queries (3) y "
      "devuelve granted None (no es una reserva) con n_before == n_after == 3",
      rr1["granted"] is None and rr2["granted"] is None and rr2["n_before"] == rr2["n_after"] == 3
      and _row(M, "brave")[0] == 3 and _row(M, "brave")[1] == 10 and abs(_row(M, "brave")[2] - 0.01) < 1e-9,
      f"row={_row(M, 'brave')} rr={rr2}")
rr3 = db.web_locator_reserve("anthropic", "2024-12", 900, record={"n_results": 2, "cost": 0.01})
check("record= sobre un mes SIN reserva previa crea la fila (INSERT idempotente) con n_queries 0 y suma igual — jamás una excepción",
      rr3["granted"] is None and _row("2024-12", "anthropic") == (0, 2, 0.01), f"{rr3} {_row('2024-12', 'anthropic')}")
# ---- 6b (corrector). peticiones FACTURADAS por encima de la reserva (reintento 429 / max_uses > 1) se suman DESPUÉS a n_queries ----------
r_x1 = db.web_locator_reserve("anthropic", "2024-11", 900)
r_x2 = db.web_locator_reserve("anthropic", "2024-11", 900, record={"n_results": 5, "cost": 0.03, "n_requests_extra": 2})
r_x3 = db.web_locator_reserve("anthropic", "2024-11", 900, record={"n_results": 1, "cost": 0.01, "n_requests_extra": 0})
check("(corrector ADR-0084) reserva 1 + record con n_requests_extra 2 (el proveedor facturó 3 búsquedas por UNA consulta: anthropic max_uses) → "
      "la fila del mes queda en n_queries 3 (peticiones FACTURADAS, no consultas), n_results 6, cost 0.04; record sin n_requests_extra (0) no "
      "mueve n_queries; el registro devuelve n_before == n_after == 3; web_locator.QUOTA_RULE lo declara ('n_requests_extra')",
      r_x1["granted"] is True and r_x2["granted"] is None and r_x2["n_after"] == 3 and r_x3["n_after"] == 3
      and _row("2024-11", "anthropic")[0] == 3 and _row("2024-11", "anthropic")[1] == 6 and abs(_row("2024-11", "anthropic")[2] - 0.04) < 1e-9,
      f"row={_row('2024-11', 'anthropic')} r_x2={r_x2}")
# ---- 6c (corrector). la carrera UNIQUE de la PRIMERA fila del mes corre en su PROPIA transacción: el perdedor no envenena el UPDATE ------
_insert_real = db._web_locator_insert_row
_lost = []


def _losing_insert(cx, month, provider):
    """Simula al PERDEDOR de la carrera: otro proceso insertó la fila entre el SELECT y el INSERT — el INSERT propio viola la UNIQUE."""
    with db.engine().begin() as cx2:
        _insert_real(cx2, month, provider)           # «el otro proceso» gana
    _lost.append((month, provider))
    _insert_real(cx, month, provider)                # el nuestro choca con la UNIQUE → IntegrityError dentro de SU transacción


db._web_locator_insert_row = _losing_insert
try:
    r_race = db.web_locator_reserve("brave", "2024-10", 3)
    r_race2 = db.web_locator_reserve("brave", "2024-10", 3)
finally:
    db._web_locator_insert_row = _insert_real
_src_h = inspect.getsource(db._web_locator_ensure_row) + inspect.getsource(db.web_locator_reserve)
check("(corrector ADR-0084) carrera UNIQUE en la PRIMERA fila del mes: el INSERT perdedor (IntegrityError) corre en su PROPIA transacción y se "
      "revierte SOLO — la reserva siguiente en la MISMA llamada se concede (granted True, n_after 1) y la fila existe UNA vez (en PostgreSQL la "
      "transacción compartida quedaba abortada → InFailedSqlTransaction → fila 'error' de la ronda); _web_locator_ensure_row devuelve "
      "(row_present_before False, inserted False, lost_race True) y abre engine().begin() propio; la 2ª reserva sigue contando (n_after 2)",
      r_race["granted"] is True and r_race["n_after"] == 1 and r_race2["n_after"] == 2 and _lost == [("2024-10", "brave")]
      and _row("2024-10", "brave") == (2, 0, 0.0)
      and db._web_locator_ensure_row("2024-10", "brave") == (True, False, False)
      and "with engine().begin() as cx:" in inspect.getsource(db._web_locator_ensure_row)
      and inspect.getsource(db.web_locator_reserve).index("_web_locator_ensure_row(month, provider)")
      < inspect.getsource(db.web_locator_reserve).index("with engine().begin() as cx:"),
      f"r_race={r_race} r_race2={r_race2} lost={_lost} row={_row('2024-10', 'brave')}")

# ---- 7. month_to_date / usage_months ---------------------------------------------------------------------------------------------
mtd = db.web_locator_month_to_date("brave", M)
mtd_missing = db.web_locator_month_to_date("anthropic", "2030-01")
months = db.web_locator_usage_months(limit=12)
check("web_locator_month_to_date(brave, 2025-03): {month, provider, n_queries 3, n_results 10, cost_usd_projected 0.01, updated_at ISO, "
      "row_present True}; sin fila (anthropic/2030-01): CEROS MEDIDOS + row_present False + updated_at None (ausencia de fila = nada enviado)",
      mtd["n_queries"] == 3 and mtd["n_results"] == 10 and abs(mtd["cost_usd_projected"] - 0.01) < 1e-9 and mtd["row_present"] is True
      and isinstance(mtd["updated_at"], str) and mtd["month"] == M and mtd["provider"] == "brave"
      and mtd_missing == {"month": "2030-01", "provider": "anthropic", "n_queries": 0, "n_results": 0, "cost_usd_projected": 0.0,
                          "updated_at": None, "row_present": False},
      f"{mtd} | {mtd_missing}")
check("web_locator_usage_months(limit 12): 8 filas (6 + las 2 del corrector), mes DESC y proveedor ASC dentro del mes, cada una {month, provider, "
      "n_queries, n_results, cost_usd_projected, updated_at}; limit 2 → 2",
      len(months) == 8 and [m["month"] for m in months] == sorted([m["month"] for m in months], reverse=True)
      and months[0]["month"] == "2025-04" and [m["provider"] for m in months if m["month"] == M] == ["anthropic", "brave"]
      and all(set(m) == {"month", "provider", "n_queries", "n_results", "cost_usd_projected", "updated_at"} for m in months)
      and len(db.web_locator_usage_months(limit=2)) == 2,
      repr([(m["month"], m["provider"], m["n_queries"]) for m in months]))

# ---- 8. SQL portable (sin RETURNING / ON CONFLICT) en la sección (H) de db.py -------------------------------------------------------
_src = Path(db.__file__).read_text(encoding="utf-8")
_sec = _src[_src.index("def web_locator_usage_table_exists"):]
_code_sec = re.sub(r'"""[\s\S]*?"""', "", _sec)                       # sin docstrings
_code_sec = "\n".join(l.split("#", 1)[0] for l in _code_sec.splitlines())   # sin comentarios
check("SQL PORTABLE (SQLite y Postgres): la sección (H) de db.py no usa RETURNING ni ON CONFLICT ni INSERT OR IGNORE (SELECT + INSERT "
      "idempotente bajo la UNIQUE; UPDATE condicional por rowcount) — se mide el CÓDIGO (sin docstrings ni comentarios)",
      "returning" not in _code_sec.lower() and "on_conflict" not in _code_sec.lower() and "insert or ignore" not in _code_sec.lower()
      and "rowcount" in _code_sec)

# ---- 9. la costura REAL con web_locator.locate (W2): quota_fn=db.web_locator_reserve, cap 1 ----------------------------------------
try:
    from lib import web_locator as wl  # noqa: E402
    _calls = []

    def _fake_provider(query, **kw):
        _calls.append(query)
        return {"status": "success", "query_sent": query, "n_http_gets": 1, "cache_hit": False, "elapsed_s": 0.01,
                "data": {"results": [{"url": "https://pubmed.ncbi.nlm.nih.gov/12345678/", "title": "t", "host": "pubmed.ncbi.nlm.nih.gov",
                                      "age": None, "page_age": None}], "query_altered_by_provider": False}}

    _saved = {k: os.environ.get(k) for k in ("WITT_WEB_LOCATOR", "BRAVE_API_KEY", "WITT_WEB_MONTHLY_CAP")}
    os.environ.update({"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": "fake-brave-key-smoke-quota", "WITT_WEB_MONTHLY_CAP": "1"})
    try:
        cfg = wl.env_config()
        month = wl.month_utc()
        q1 = wl.locate("wt1a quota q1", cfg, provider_fn=_fake_provider, quota_fn=db.web_locator_reserve, round_no=1)
        q2 = wl.locate("wt1a quota q2", cfg, provider_fn=_fake_provider, quota_fn=db.web_locator_reserve, round_no=1)
    finally:
        for k, v in _saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    row_m = _row(month, "brave")
    check("costura W2↔H: web_locator.locate(quota_fn=db.web_locator_reserve) con WITT_WEB_MONTHLY_CAP=1 → 1ª consulta 'under-cap' (proveedor "
          "fake llamado 1 vez, n_located 1, record= sumó n_results 1), 2ª 'skipped-cap' con detail 'monthly cap WITT_WEB_MONTHLY_CAP=1 reached "
          "(n_queries=1, month <m>)' y CERO llamadas más al proveedor; la fila del mes UTC queda en n_queries 1",
          q1["provider_status"] == "success" and q1["quota"]["state"] == "under-cap" and q1["n_located"] == 1
          and q2["provider_status"] == "skipped-cap" and q2["quota"]["state"] == "cap-reached"
          and q2.get("detail") == f"monthly cap WITT_WEB_MONTHLY_CAP=1 reached (n_queries=1, month {month})"
          and q2["state"].startswith("skipped-cap (") and len(_calls) == 1
          and row_m is not None and row_m[0] == 1 and row_m[1] == 1,
          f"q1={q1['quota']} q2={q2.get('detail')} calls={len(_calls)} row={row_m}")
except Exception as e:   # pragma: no cover — árbol sin la rebanada W2: se declara
    check(f"costura W2↔H: lib.web_locator importable ({type(e).__name__}: {str(e)[:100]})", False)

# ---- 10. cero red ------------------------------------------------------------------------------------------------------------------
check("cero red: urllib.request.urlopen bloqueado y contado == 0", _NET_CALLS == [], f"{_NET_CALLS}")
_urlreq.urlopen = _urlopen_real

n_pass = sum(CHECKS)
print(f"\n== {n_pass}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_pass == len(CHECKS) else 1)
