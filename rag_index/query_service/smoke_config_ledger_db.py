"""smoke_config_ledger_db.py — gate determinista de la BITÁCORA DE CONFIGURACIÓN (ADR-0081 (I), rebanada
S4 · BD): la tabla `config_history` y las funciones `config_ledger_*` de db.py — la clase MEDICIÓN de
/config-history (el archivo rag_index/config_history.json es la clase ATESTIGUADA y no se toca aquí).

Cubre: (a) create_all crea la tabla con las columnas EXACTAS del ADR y el índice
ix_config_history_field_recorded, sin ALTER (idempotente; _migrate no la menciona); DDL compilado para
postgresql (SERIAL, TIMESTAMP WITH TIME ZONE); (b) append / list / last_by_field / stats con filas armadas
COMO las arma el escritor (config_ledger.diff_rows, S5): valores YA codificados a texto, `recorded_at` de
lote, `previous_value None` en el primer arranque; (c) los TRES ESTADOS de previous_value — SQL NULL
(primera observación, previous_recorded false) ≠ texto 'null' (anterior None DECLARADO) ≠ texto; (d) la
codificación COMPARTIDA (config_ledger_encode: str tal cual · None 'null' · bool 'true'|'false' · otros
JSON) para insumos no-str; (e) NUNCA update: las filas viejas quedan byte a byte, db no expone
update/delete sobre la tabla y su fuente no los contiene; (f) boot_id viaja y dos arranques se distinguen;
`recorded_at` del llamador se respeta y sin él se mide al escribir; (g) el CINTURÓN: un valor con 'sk-' /
'key' / 'token' (sin distinguir mayúsculas) NO entra, se declara en rejected[] sin copiar el valor, y las
demás filas del lote sí entran; (h) errores ESTRUCTURALES (llave requerida ausente, llave desconocida,
texto más largo que su columna) -> ValueError y CERO filas del lote (atómico: lo que Postgres rechazaría,
aquí se rechaza también en SQLite).

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes — cero red, cero modelo, cero mutación de
la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre (con la máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-ledger.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_config_ledger_db.py
(si WITT_BACKEND_DB_URL no viene, se fija a ese archivo; el archivo previo se borra al arrancar.)
"""
import datetime
import inspect
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
_default_db = SMOKES_DIR / "smoke-ledger.db"
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))   # ADR-0081 (M.4, S7): la tabla
import db  # noqa: E402
from lib import models  # noqa: E402
# ADR-0081 (M.4, S7): ids de modelo LEÍDOS de la tabla, jamás literales en el smoke
_G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
OPUS5, G4O = _G2["synthesizer"], _G2["judge.reproducibility"]
EMBED = models.SNAPSHOT_ALSO_READS[models.EMBED_MODEL_ENV]["default"]
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _raises(fn, exc):
    try:
        fn()
        return False
    except exc:
        return True


def _crudo():
    """Las filas TAL CUAL están en la tabla (sin decodificar) — para medir 'nunca update'."""
    with db.engine().begin() as cx:
        return [tuple(r) for r in cx.execute(text("SELECT * FROM config_history ORDER BY id")).all()]


def _n_filas():
    with db.engine().begin() as cx:
        return cx.execute(text("SELECT COUNT(*) FROM config_history")).scalar()


def _filas_como_s5(snapshot_fields, last, changed_by, boot_id, stamp, generation="g2-2026-09"):
    """Arma las filas COMO config_ledger.diff_rows (S5): valor codificado a texto, previous_value = texto
    del último o None (primer arranque), note por caso, recorded_at de lote. Reproducido aquí para medir la
    capa db contra la forma REAL de su escritor, sin importar config_ledger (archivo de S5)."""
    first_boot = not last
    rows = []
    for field, cell in snapshot_fields.items():
        enc = db.config_ledger_encode(cell["value"])
        prev_row = last.get(field)
        prev = prev_row["value"] if prev_row else None
        if prev_row is not None and prev == enc:
            continue
        rows.append({"recorded_at": stamp, "field": field, "value": enc, "previous_value": prev,
                     "source": cell["source"], "changed_by": changed_by,
                     "scope": field.split(".", 1)[0] if "." in field else "generation",
                     "generation": generation, "boot_id": boot_id,
                     "note": ("first-boot-snapshot" if first_boot else ("new-field" if prev_row is None else None))})
    return rows


# ---- 1. create_all crea la tabla; columnas e índice EXACTOS; sin ALTER; idempotente ----------------------
check("antes de init_db: config_ledger_table_exists() False (BD fresca) — insumo de ledger_state 'table-missing'",
      db.config_ledger_table_exists() is False)
db.init_db()
with db.engine().begin() as cx:
    cols = cx.execute(text("PRAGMA table_info(config_history)")).all()   # (cid, name, type, notnull, dflt, pk)
    idx = {r[1]: r for r in cx.execute(text("PRAGMA index_list(config_history)")).all()}
    idx_cols = [r[2] for r in cx.execute(text("PRAGMA index_info(ix_config_history_field_recorded)")).all()] \
        if "ix_config_history_field_recorded" in idx else []
nombres = [c[1] for c in cols]
notnull = {c[1]: bool(c[3]) for c in cols}
check("init_db: la tabla existe con las 11 columnas EXACTAS del ADR, en orden",
      db.config_ledger_table_exists() is True
      and nombres == ["id", "recorded_at", "field", "value", "previous_value", "source", "changed_by", "scope",
                      "generation", "boot_id", "note"], str(nombres))
check("NOT NULL en recorded_at/field/value/source/changed_by/scope/generation/boot_id; NULL permitido SÓLO en previous_value y note; id PK",
      all(notnull[k] for k in ("recorded_at", "field", "value", "source", "changed_by", "scope", "generation", "boot_id"))
      and not notnull["previous_value"] and not notnull["note"] and [c[1] for c in cols if c[5]] == ["id"],
      str(notnull))
check("índice ix_config_history_field_recorded sobre (field, recorded_at)",
      idx_cols == ["field", "recorded_at"], str(idx_cols))
db.init_db()
check("init_db (2a vez): idempotente — la tabla sigue, sin error y con 0 filas", db.config_ledger_table_exists() and _n_filas() == 0)
check("sin ALTER: _migrate NO menciona config_history (tabla nueva: esquema completo desde create_all)",
      "config_history" not in inspect.getsource(db._migrate))
ddl = str(CreateTable(db.config_history).compile(dialect=postgresql.dialect()))
ddl_ix = [str(CreateIndex(ix).compile(dialect=postgresql.dialect())) for ix in db.config_history.indexes]
check("DDL compilado para postgresql: id SERIAL, recorded_at TIMESTAMP WITH TIME ZONE, field VARCHAR(64), changed_by VARCHAR(64), "
      "scope VARCHAR(24), generation/boot_id VARCHAR(32), value TEXT NOT NULL, previous_value TEXT nulo; índice (field, recorded_at)",
      "id SERIAL NOT NULL" in ddl and "recorded_at TIMESTAMP WITH TIME ZONE NOT NULL" in ddl
      and "field VARCHAR(64) NOT NULL" in ddl and "changed_by VARCHAR(64) NOT NULL" in ddl
      and "scope VARCHAR(24) NOT NULL" in ddl and "generation VARCHAR(32) NOT NULL" in ddl
      and "boot_id VARCHAR(32) NOT NULL" in ddl and "value TEXT NOT NULL" in ddl and "previous_value TEXT, " in ddl
      and len(ddl_ix) == 1 and "ON config_history (field, recorded_at)" in ddl_ix[0], ddl.replace("\n", " ")[:160])

# ---- 2. la codificación COMPARTIDA (config_ledger_encode == config_ledger._encode de S5) ------------------
check("config_ledger_encode: str tal cual · None 'null' · True/False 'true'/'false' · int '4000' · dict JSON sort_keys (sin comillas dobles)",
      db.config_ledger_encode(G4O) == G4O and db.config_ledger_encode(None) == "null"
      and db.config_ledger_encode(True) == "true" and db.config_ledger_encode(False) == "false"
      and db.config_ledger_encode(4000) == "4000" and db.config_ledger_encode({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
      and db.config_ledger_encode("null") == "null" and db.config_ledger_encode("") == "")

# ---- 3. primer arranque: append / list / last_by_field / stats — filas como las arma S5 --------------------
BOOT_A, BOOT_B = "boot-aaaaaaaa", "boot-bbbbbbbb"
STAMP_A = datetime.datetime(2026, 9, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
SNAP_A = {"model_generation": {"value": "g2-2026-09", "source": "default-unset:WITT_MODEL_GENERATION"},
          "panel.min_families": {"value": 2, "source": "default-unset:WITT_PANEL_MIN_FAMILIES"},
          "openai.store": {"value": False, "source": "default-unset:WITT_OPENAI_STORE"},
          "openai.reasoning_effort": {"value": None, "source": "default-unset:WITT_OPENAI_REASONING_EFFORT"}}
filas_a = _filas_como_s5(SNAP_A, db.config_ledger_last_by_field(), "system:boot-diff", BOOT_A, STAMP_A)
check("primer arranque (last_by_field vacío -> {}): 4 filas, note 'first-boot-snapshot', previous_value None, recorded_at de lote",
      db.config_ledger_last_by_field() == {} and len(filas_a) == 4
      and all(f["note"] == "first-boot-snapshot" and f["previous_value"] is None and f["recorded_at"] is STAMP_A for f in filas_a))
res_a = db.config_ledger_append(filas_a)
check("config_ledger_append(primer arranque): n_written 4, rejected [], recorded_at = la marca del lote (2026-09-15T12:00:00+00:00)",
      res_a == {"n_written": 4, "rejected": [], "recorded_at": "2026-09-15T12:00:00+00:00"}, json.dumps(res_a))
lst = db.config_ledger_list()
check("config_ledger_list: 4 filas, recorded_at DESC e id DESC (la última escrita primero), llaves EXACTAS (CONFIG_LEDGER_ROW_FIELDS), "
      "recorded_at ISO con zona = la marca del llamador",
      len(lst) == 4 and [r["id"] for r in lst] == [4, 3, 2, 1]
      and all(tuple(r.keys()) == db.CONFIG_LEDGER_ROW_FIELDS for r in lst)
      and all(r["recorded_at"] == "2026-09-15T12:00:00+00:00" for r in lst), str([r["id"] for r in lst]))
por_campo = {r["field"]: r for r in lst}
check("value es TEXTO tal cual se escribió: 'g2-2026-09', '2', 'false', 'null' (el tipo vive en current.fields, no en la bitácora); json.dumps(list) serializable",
      por_campo["model_generation"]["value"] == "g2-2026-09" and por_campo["panel.min_families"]["value"] == "2"
      and por_campo["openai.store"]["value"] == "false" and por_campo["openai.reasoning_effort"]["value"] == "null"
      and json.dumps(lst) is not None, json.dumps({k: v["value"] for k, v in por_campo.items()}))
check("primera observación: previous_recorded false y previous_value None en las 4; changed_by/scope/generation/source tal cual",
      all(r["previous_recorded"] is False and r["previous_value"] is None for r in lst)
      and all(r["changed_by"] == "system:boot-diff" and r["generation"] == "g2-2026-09" for r in lst)
      and por_campo["openai.store"]["scope"] == "openai" and por_campo["model_generation"]["scope"] == "generation"
      and por_campo["openai.store"]["source"] == "default-unset:WITT_OPENAI_STORE")
ult = db.config_ledger_last_by_field()
check("config_ledger_last_by_field: 4 campos -> la fila de cada uno, con el texto del snapshot",
      set(ult) == set(SNAP_A) and all(ult[k]["value"] == db.config_ledger_encode(SNAP_A[k]["value"]) for k in SNAP_A))
st = db.config_ledger_stats()
check("config_ledger_stats: {table 'config_history', n_rows 4, last_recorded_at == recorded_at de la fila más reciente}",
      st == {"table": "config_history", "n_rows": 4, "last_recorded_at": lst[0]["recorded_at"]}, json.dumps(st))
crudo_a = _crudo()

# ---- 4. segundo arranque: mismo snapshot -> 0 filas; un cambio -> UNA fila con previous_value --------------
STAMP_B = datetime.datetime(2026, 9, 16, 8, 30, 0, tzinfo=datetime.timezone.utc)
check("segundo arranque con el MISMO snapshot: el diff (texto contra texto de last_by_field) produce 0 filas y append([]) escribe 0",
      _filas_como_s5(SNAP_A, db.config_ledger_last_by_field(), "system:boot-diff", BOOT_B, STAMP_B) == []
      and db.config_ledger_append([])["n_written"] == 0 and _n_filas() == 4)
SNAP_B = {**SNAP_A, "panel.min_families": {"value": 0, "source": "env:WITT_PANEL_MIN_FAMILIES"}}
filas_b = _filas_como_s5(SNAP_B, db.config_ledger_last_by_field(), "system:boot-diff", BOOT_B, STAMP_B)
check("un campo cambiado (2 -> 0): exactamente UNA fila, previous_value '2' (texto del último), note None, fuente nueva",
      len(filas_b) == 1 and filas_b[0]["field"] == "panel.min_families" and filas_b[0]["value"] == "0"
      and filas_b[0]["previous_value"] == "2" and filas_b[0]["note"] is None
      and filas_b[0]["source"] == "env:WITT_PANEL_MIN_FAMILIES", json.dumps(filas_b, default=str))
res_b = db.config_ledger_append(filas_b)
ult_b = db.config_ledger_last_by_field()
check("tras el append: last_by_field['panel.min_families'] = {value '0', previous_value '2', previous_recorded true, boot_id B, "
      "recorded_at de B}; los otros 3 campos siguen con boot_id A (nadie los reescribió)",
      res_b["n_written"] == 1 and ult_b["panel.min_families"]["value"] == "0" and ult_b["panel.min_families"]["previous_value"] == "2"
      and ult_b["panel.min_families"]["previous_recorded"] is True and ult_b["panel.min_families"]["boot_id"] == BOOT_B
      and ult_b["panel.min_families"]["recorded_at"] == "2026-09-16T08:30:00+00:00"
      and all(ult_b[k]["boot_id"] == BOOT_A for k in ("model_generation", "openai.store", "openai.reasoning_effort")),
      json.dumps(ult_b["panel.min_families"]))

# ---- 5. tres estados de previous_value: SQL NULL ≠ 'null' declarado ≠ texto ---------------------------------
base_b = {"source": "env:X", "changed_by": "system:runtime-diff", "scope": "openai", "generation": "g2-2026-09",
          "boot_id": BOOT_B}
res_c = db.config_ledger_append([
    {"field": "openai.reasoning_effort", "value": "low", "previous_value": "null", **base_b},   # anterior None DECLARADO
    {"field": "anthropic.effort", "value": "null", "note": "new-field", **base_b},               # campo NUEVO, valor None declarado
])
ult_c = db.config_ledger_last_by_field()
with db.engine().begin() as cx:
    raw = {r[0]: (r[1], r[2]) for r in cx.execute(text(
        "SELECT field, value, previous_value FROM config_history WHERE id IN (6, 7)")).all()}
check("'null' -> 'low': previous_value 'null' con previous_recorded TRUE (anterior declarado ausente, NO primera observación); "
      "campo nuevo con valor 'null': previous_value None y previous_recorded FALSE — distinguibles; sin recorded_at -> se mide al escribir",
      res_c["n_written"] == 2 and ult_c["openai.reasoning_effort"]["value"] == "low"
      and ult_c["openai.reasoning_effort"]["previous_value"] == "null" and ult_c["openai.reasoning_effort"]["previous_recorded"] is True
      and ult_c["anthropic.effort"]["value"] == "null" and ult_c["anthropic.effort"]["previous_value"] is None
      and ult_c["anthropic.effort"]["previous_recorded"] is False
      and ult_c["anthropic.effort"]["recorded_at"].startswith(
          datetime.datetime.now(datetime.timezone.utc).date().isoformat())
      and ult_c["anthropic.effort"]["recorded_at"] != "2026-09-16T08:30:00+00:00",
      json.dumps({k: ult_c[k] for k in ("openai.reasoning_effort", "anthropic.effort")}))
check("en la tabla, tal cual: previous_value = 'null' (texto) para el anterior declarado y SQL NULL para la primera observación; "
      "value 'null' texto (CONFIG_LEDGER_ENCODING)",
      raw["openai.reasoning_effort"] == ("low", "null") and raw["anthropic.effort"] == ("null", None), str(raw))
check("insumos NO-str también entran por la codificación compartida: value 7 -> '7', previous_value True -> 'true'; "
      "previous_value None explícito -> SQL NULL (== llave ausente)",
      db.config_ledger_append([{"field": "judge.retries", "value": 7, "previous_value": True, **base_b},
                               {"field": "prices.as_of", "value": "2026-09", "previous_value": None, **base_b}])["n_written"] == 2
      and db.config_ledger_last_by_field()["judge.retries"]["value"] == "7"
      and db.config_ledger_last_by_field()["judge.retries"]["previous_value"] == "true"
      and db.config_ledger_last_by_field()["prices.as_of"]["previous_recorded"] is False)
# corrector (gate): las dos fechas SELLADAS por el llamador se calculan DESDE AHORA (+1 h y +2 h). Antes eran los literales
# 2026-09-17T00:00/01:00 y el check de orden de abajo afirmaba que iban primero — cierto hasta que el calendario las alcanzó
# (a partir del 2026-09-18 la fila medida "ahora" era la más reciente y el gate se ponía rojo SIN que nada hubiera cambiado).
_SELLO_1 = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).replace(microsecond=0)
_SELLO_2 = _SELLO_1 + datetime.timedelta(hours=1)
check("recorded_at del llamador: ISO str y datetime NAIVE se aceptan (naive = UTC por construcción); basura -> ValueError",
      db.config_ledger_append([{"field": "embed.model", "value": EMBED,
                                "recorded_at": _SELLO_1.isoformat(), **base_b}])["recorded_at"] == _SELLO_1.isoformat()
      and db.config_ledger_append([{"field": "openai.api", "value": "table",
                                    "recorded_at": _SELLO_2.replace(tzinfo=None), **base_b}])["recorded_at"] == _SELLO_2.isoformat()
      and _raises(lambda: db.config_ledger_append([{"field": "x", "value": "y", "recorded_at": 12345, **base_b}]), ValueError))

# ---- 6. NUNCA update: las filas viejas byte a byte; db sin update/delete sobre la tabla ----------------------
crudo_c = _crudo()
check("nunca update: las 4 filas del primer arranque están BYTE A BYTE como se escribieron tras todos los appends (ids 1..4) y los ids son consecutivos",
      crudo_c[:4] == crudo_a and [r[0] for r in crudo_c] == list(range(1, _n_filas() + 1)))
fuente_db = inspect.getsource(db)
check("db NO expone update/delete sobre config_history: ningún atributo config_ledger_(update|delete|set|clear) y la fuente no "
      "contiene 'config_history.update(' ni 'config_history.delete(' ni 'delete(config_history'",
      not [n for n in dir(db) if n.startswith("config_ledger_") and any(w in n for w in ("update", "delete", "set", "clear"))]
      and "config_history.update(" not in fuente_db and "config_history.delete(" not in fuente_db
      and "delete(config_history" not in fuente_db)
check("boot_id: dos arranques se distinguen — {A, B} en la tabla; el campo cambiado lleva B y los intactos A",
      {r["boot_id"] for r in db.config_ledger_list()} == {BOOT_A, BOOT_B})
check("orden de config_ledger_list: recorded_at DESC manda sobre id (las dos filas SELLADAS por el llamador — ahora +2 h y +1 h — "
      "van primero aunque otra fila se haya medido 'ahora' y tenga id mayor)",
      db.config_ledger_list()[0]["field"] == "openai.api" and db.config_ledger_list()[1]["field"] == "embed.model")

# ---- 7. el CINTURÓN contra secretos ---------------------------------------------------------------------
n_antes = _n_filas()
res_s = db.config_ledger_append([{"field": "embed.model", "value": "sk-abc123DEF", **base_b},
                                 {"field": "panel.min_lenses", "value": "3", **base_b}])
check("lote mixto: el valor 'sk-…' se RECHAZA y se declara {field, reason 'secret-like-value', marker 'sk-', value_len}; "
      "la otra fila SÍ entra (n_written 1)",
      res_s["n_written"] == 1 and len(res_s["rejected"]) == 1
      and res_s["rejected"][0] == {"field": "embed.model", "reason": "secret-like-value", "marker": "sk-", "value_len": 12}
      and _n_filas() == n_antes + 1 and db.config_ledger_last_by_field()["panel.min_lenses"]["value"] == "3",
      json.dumps(res_s))
check("el valor rechazado JAMÁS se copia: ni en rejected[] ni en la tabla (embed.model conserva su fila anterior)",
      "sk-abc123DEF" not in json.dumps(res_s) and "sk-abc" not in json.dumps(db.config_ledger_list())
      and db.config_ledger_last_by_field()["embed.model"]["value"] == EMBED)
n_antes = _n_filas()
res_k = db.config_ledger_append([{"field": "a", "value": "MY_API_KEY_X", **base_b},
                                 {"field": "b", "value": "BearerTOKENx", **base_b},
                                 {"field": "c", "value": {"nested": "Sk-9"}, **base_b}])
check("marcas sin distinguir mayúsculas y dentro de estructuras: 'MY_API_KEY_X' -> 'key', 'BearerTOKENx' -> 'token', "
      "{'nested':'Sk-9'} -> 'sk-'; n_written 0",
      res_k["n_written"] == 0 and [r["marker"] for r in res_k["rejected"]] == ["key", "token", "sk-"] and _n_filas() == n_antes)
res_p = db.config_ledger_append([{"field": "d", "value": "ok", "previous_value": "sk-old", **base_b}])
check("un previous_value que parezca llave también se rechaza (where 'previous_value')",
      res_p["n_written"] == 0 and res_p["rejected"][0]["where"] == "previous_value" and res_p["rejected"][0]["marker"] == "sk-")
legitimos = ["g2-2026-09", OPUS5, G4O, "openai-chat-completions", "table", 4000, 120, True, False, None,
             "2026-09", "1.10", EMBED, "1c9f0a3b2d4e5f60", "off", "default", "high", "null", "true"]
check("valores legítimos del snapshot no disparan el cinturón (ids de modelo, api, números, booleanos, None, firma hex, versión)",
      all(db.config_ledger_secret_like(db.config_ledger_encode(v)) is None for v in legitimos)
      and db.config_ledger_secret_like("sk-x") == "sk-" and db.config_ledger_secret_like("") is None)

# ---- 8. errores ESTRUCTURALES -> ValueError y cero filas (atómico) -------------------------------------------
n_antes = _n_filas()
buena = {"field": "z", "value": "1", **base_b}
check("llave requerida ausente (boot_id) -> ValueError; lote [buena, mala] NO escribe ninguna (atómico)",
      _raises(lambda: db.config_ledger_append([buena, {k: v for k, v in buena.items() if k != "boot_id"}]), ValueError)
      and _n_filas() == n_antes)
check("llave desconocida ('foo') -> ValueError; fila que no es dict -> ValueError; generation None -> ValueError",
      _raises(lambda: db.config_ledger_append([{**buena, "foo": 1}]), ValueError)
      and _raises(lambda: db.config_ledger_append(["no-dict"]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "generation": None}]), ValueError) and _n_filas() == n_antes)
check("texto más largo que su columna -> ValueError (field 65, scope 25, changed_by 65, generation/boot_id 33): lo que Postgres "
      "rechazaría se rechaza también en SQLite; str vacío en field -> ValueError",
      _raises(lambda: db.config_ledger_append([{**buena, "field": "f" * 65}]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "scope": "s" * 25}]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "changed_by": "c" * 65}]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "generation": "g" * 33}]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "boot_id": "b" * 33}]), ValueError)
      and _raises(lambda: db.config_ledger_append([{**buena, "field": ""}]), ValueError)
      and _n_filas() == n_antes)
check("los topes son exactamente los de las columnas: field/changed_by 64, scope 24, generation/boot_id 32 entran",
      db.config_ledger_append([{**buena, "field": "f" * 64, "changed_by": "c" * 64, "scope": "s" * 24,
                                "generation": "g" * 32, "boot_id": "b" * 32}])["n_written"] == 1)
check("lote vacío / None -> n_written 0, recorded_at None, sin error; list(limit=2) -> 2 filas; list(limit=0) -> ValueError",
      db.config_ledger_append([]) == {"n_written": 0, "rejected": [], "recorded_at": None}
      and db.config_ledger_append(None)["n_written"] == 0
      and len(db.config_ledger_list(limit=2)) == 2 and _raises(lambda: db.config_ledger_list(limit=0), ValueError))
check("constantes congeladas para S5/webapp: CONFIG_LEDGER_TABLE 'config_history', LIST_LIMIT 500, SECRET_MARKERS ('sk-','key','token'), "
      "REQUIRED (7) / OPTIONAL (previous_value, note, recorded_at) / ROW_FIELDS (12) / ENCODING declarado",
      db.CONFIG_LEDGER_TABLE == "config_history" and db.CONFIG_LEDGER_LIST_LIMIT == 500
      and db.CONFIG_LEDGER_SECRET_MARKERS == ("sk-", "key", "token")
      and db.CONFIG_LEDGER_REQUIRED == ("field", "value", "source", "changed_by", "scope", "generation", "boot_id")
      and db.CONFIG_LEDGER_OPTIONAL == ("previous_value", "note", "recorded_at")
      and len(db.CONFIG_LEDGER_ROW_FIELDS) == 12 and "SQL NULL" in db.CONFIG_LEDGER_ENCODING)

n_ok = sum(CHECKS)
print(f"\n== {n_ok}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_ok == len(CHECKS) else 1)
