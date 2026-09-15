"""
config_ledger.py — la bitácora de configuración del servicio (ADR-0081 (I) y (E)).

QUÉ ES. La configuración EFECTIVA del servicio (generación de modelos, roles, panel, transporte del juez
OpenAI, cuórum, topes, precios, kill-switches) se resuelve EN LA LLAMADA desde `lib.models.snapshot()` —
una lista CERRADA de campos (`models.SNAPSHOT_FIELDS`), cada uno {value, source}. Este módulo la compara
con la ÚLTIMA fila por campo de la tabla `config_history` (S4, `db.config_ledger_*` — dependencia DURA desde S7:
sin esas funciones boot()/observe() reportan 'error: AttributeError', jamás fingen 'table-missing') y APPENDEA una fila
por campo que cambió. Nunca reescribe ni borra: la historia es append-only (regla ERP "el catálogo tiene
historia", ADR-0055).

DOS momentos, UNA comparación (`diff_rows`, función pura y medible sin BD):
  · `boot()`  — al arrancar (lifespan de app.py, tras db.init_db() y antes de start_workers). Primer
    arranque: TODOS los campos, previous_value null, note 'first-boot-snapshot'. Arranques siguientes: sólo
    lo que cambió respecto a la última fila por campo, `changed_by 'system:boot-diff'`. Invariante (ADR-0081
    Context 10): toda env cambia SÓLO con reinicio, así que el diff al boot es COMPLETO para envs.
  · `observe(snapshot)` — al inicio de cada execute_run (S3 lo llama): compara el snapshot de la corrida con
    `_LEDGER_STATE['last']` (un dict compare; escribe SÓLO en cambio) y appendea `changed_by
    'system:runtime-diff'` — cubre lo que el reloj cambia sin reinicio (auto-retire de haiku con
    WITT_PANEL_AUTO_RETIRE=1 al llegar retire_not_before). JAMÁS lanza: un fallo del ledger no toca la corrida.
    Corrector (2026-09-15): boot() y observe() están SERIALIZADOS por `_LOCK` (threading.Lock) — el servicio corre
    WITT_RUN_WORKERS hilos (default 2) y dos execute_run concurrentes observaban el MISMO cambio contra la misma
    baseline antes de que alguna la avanzara: la fila runtime-diff se duplicaba en una tabla append-only. Con el
    lock, exactamente 1 fila por campo cambiado (medido en smoke_config_history_http con 2 hilos). El riesgo de
    DOS PROCESOS (boot duplicado) sigue siendo el de R9: `--workers 1`.

LO QUE EL LEDGER NO PUEDE REGISTRAR (declarado, no disimulado): QUIÉN cambió la env (`actor_state
'not-observable (env set outside the service)'`); un `min_families=` pasado por un llamador de audit()
(viaja en `audit.quorum.source 'caller'`, no es configuración del servicio).

KILL-SWITCH `WITT_CONFIG_LEDGER=0` (default 1, `models.ENV_TABLE`): cero escrituras; `ledger_state` lo dice.
Un fallo del ledger JAMÁS impide el arranque: todo va a `_LEDGER_STATE` y a `ledger_state 'error: <tipo>'`.

CINTURÓN: ningún `value` que parezca llave sale de aquí — models.snapshot() ya redacta; S4 repite el cinturón
al escribir y devuelve `rejected[]`, que se declara en el estado.

Firmas (contrato para S3/S7):
    boot(env=None, today=None, extra=None) -> dict   (nunca lanza)
    observe(snapshot=None, env=None, today=None) -> dict   (nunca lanza)
    diff_rows(snapshot, last_by_field, changed_by, boot_id=None) -> list[row]   (pura)
    current(env=None, today=None, extra=None) -> dict   (el bloque `current` de /config-history)
    state_view() -> dict   (el estado del ledger para /config-history y consulta_sistema)
    default_extra(env=None) -> dict   (los 4 EXTRA_FIELDS que models.py no deriva)
"""
import datetime
import json
import os
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "analysis" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import models  # noqa: E402
import db  # noqa: E402

LEDGER_ENV = "WITT_CONFIG_LEDGER"          # models.ENV_TABLE: default "1", kind bool01
LEDGER_TABLE = "config_history"
LEDGER_LIST_LIMIT = 500
CHANGED_BY_BOOT = "system:boot-diff"
CHANGED_BY_RUNTIME = "system:runtime-diff"
NOTE_FIRST_BOOT = "first-boot-snapshot"
NOTE_NEW_FIELD = "new-field (sin fila previa para este campo)"
ACTOR_STATE = "not-observable (env set outside the service)"
# Estados CERRADOS del ledger (la webapp los tipa; 'not-booted' es el estado ANTES del lifespan — un
# TestClient sin lifespan lo ve, y así se declara en vez de fingir 'ok').
STATE_OK = "ok"
STATE_KILL = "kill-switch WITT_CONFIG_LEDGER=0"
STATE_TABLE_MISSING = "table-missing"
STATE_NOT_BOOTED = "not-booted (lifespan no corrió: config_ledger.boot() no se ha llamado)"
STATES_RULE = ("'ok' | 'kill-switch WITT_CONFIG_LEDGER=0' | 'table-missing' | 'error: <tipo>' | "
               "'not-booted (…)' — el estado del ESCRITOR; una lectura fallida de la tabla manda el suyo")
# Codificación del `value` Text de la fila (declarada en /config-history.ledger_encoding): un str viaja tal
# cual; bool → 'true'|'false'; None → 'null' (valor declarado ausente, p. ej. effort no enviado); otros → JSON.
VALUE_ENCODING = "text: str tal cual · bool → true|false · None → null · otros → JSON"
SCOPE_RULE = ("prefijo del campo antes del primer '.' (role|panel|openai|anthropic|judge|prices|contract|embed|"
              "competence|search|revision); los tres campos sin prefijo (model_generation, table_version, "
              "panel_signature) → 'generation'")

BOOT_ID = uuid.uuid4().hex[:16]
# corrector ADR-0081 (I): boot()/observe() mutan _LEDGER_STATE y comparan contra su baseline desde los hilos worker
# ('run-worker-0/1'); el lock serializa la comparación + escritura + avance de baseline (coste cero sin cambio).
_LOCK = threading.Lock()

_LEDGER_STATE = {
    "state": STATE_NOT_BOOTED,
    "boot_id": BOOT_ID,
    "booted_at": None,            # ISO del último boot() (None hasta que corra)
    "last": None,                 # {campo: value CODIFICADO} del último snapshot observado (baseline de observe)
    "last_signature": None,       # panel_signature del baseline
    "n_written_boot": 0,
    "n_written_runtime": 0,
    "rejected": [],               # lo que S4 rechazó al escribir (cinturón de secretos), declarado
    "last_error": None,
    "observed_at": None,          # ISO del último observe()
    "n_observed": 0,
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _now_iso():
    return _now().isoformat(timespec="seconds")


def _encode(value):
    """El `value` Text de la fila (VALUE_ENCODING). Comparación EXACTA de strings en el diff."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _scope_of(field):
    return field.split(".", 1)[0] if "." in field else "generation"


def _enabled(env=None):
    """(bool, fuente) — WITT_CONFIG_LEDGER vía models.env_value (default declarado '1'; basura → default)."""
    return models.env_value(LEDGER_ENV, env)


def _is_table_missing(exc):
    """OperationalError/ProgrammingError de 'no such table' (SQLite) / 'does not exist' (Postgres) → la tabla
    no existe (create_all no corrió): 'table-missing', no 'error: …'."""
    s = str(exc).lower()
    return ("no such table" in s) or ("does not exist" in s and "relation" in s)


def default_extra(env=None):
    """Los 4 EXTRA_FIELDS que models.py NO puede derivar (viven en runs/competence), cada uno {value, source}.
    Import perezoso de runs/competence (mismo directorio; app.py ya los tiene cargados). Con `env` inyectado
    (smokes) se aplican las MISMAS reglas de lectura que los dueños (runs._search_harness_enabled: vacío →
    True; runs._revision_enabled: `== '1'`) sobre el mapping; con env=None se llama a los dueños directamente
    — así no hay dos verdades. Lo que no se pueda leer queda {None, 'not-provided-by-caller (…)'}."""
    out = {}
    e = os.environ if env is None else env
    try:
        import runs as runs_mod
        if env is None and callable(getattr(runs_mod, "snapshot_extra", None)):
            # UNA sede (S3, runs.snapshot_extra): el boot y la corrida describen el MISMO estado con las MISMAS
            # fuentes; el espejo de abajo sólo sirve a un `env` inyectado (smokes), que runs no acepta.
            return dict(runs_mod.snapshot_extra())
        out["contract.render_contract_version"] = {"value": runs_mod.RENDER_CONTRACT_VERSION,
                                                   "source": "runs.RENDER_CONTRACT_VERSION"}
        if env is None:
            harness, h_src = runs_mod._search_harness_enabled()
        else:
            raw = str(e.get(runs_mod.SEARCH_HARNESS_ENV) or "").strip()
            harness, h_src = ((True, f"default-unset:{runs_mod.SEARCH_HARNESS_ENV}") if not raw
                              else (raw != "0", f"env:{runs_mod.SEARCH_HARNESS_ENV}"))
        out["search.harness"] = {"value": bool(harness), "source": h_src}
        if env is None:
            rev = runs_mod._revision_enabled()
        else:
            rev = str(e.get("WITT_REVISION_CYCLE", "1")) == "1"
        out["revision.cycle"] = {"value": bool(rev),
                                 "source": ("env:WITT_REVISION_CYCLE" if "WITT_REVISION_CYCLE" in e
                                            else "default-unset:WITT_REVISION_CYCLE")}
    except Exception as ex:   # runs no importable (entorno recortado): ausencia declarada, jamás un default copiado
        for k in ("contract.render_contract_version", "search.harness", "revision.cycle"):
            out.setdefault(k, {"value": None, "source": f"{models.NOT_PROVIDED} (runs: {type(ex).__name__})"})
    try:
        import competence as competence_mod
        cfg = competence_mod.env_config(e)
        raw = str(e.get(competence_mod.GATE_ENV) or "").strip()
        out["competence.gate"] = {"value": bool(cfg["gate_enabled"]),
                                  "source": (f"env:{competence_mod.GATE_ENV}" if raw
                                             else f"default-unset:{competence_mod.GATE_ENV}")}
    except Exception as ex:
        out["competence.gate"] = {"value": None, "source": f"{models.NOT_PROVIDED} (competence: {type(ex).__name__})"}
    return out


def take_snapshot(env=None, today=None, extra=None):
    """models.snapshot() con los extras del servicio — la MISMA función para boot, observe, current y
    stage.models (N: 'el snapshot del boot usa models.snapshot() sin re-derivar')."""
    return models.snapshot(env, today, extra=default_extra(env) if extra is None else extra)


def diff_rows(snapshot, last_by_field, changed_by, boot_id=None, recorded_at=None):
    """PURA: las filas a appendear = un campo por cada `SNAPSHOT_FIELDS` cuyo value codificado difiere de la
    última fila por campo (`last_by_field` = {campo: fila con `value`} — {} o None = primer arranque: TODAS,
    previous_value null, note 'first-boot-snapshot'; un campo nuevo sin fila previa → note 'new-field'). Cada fila:
    {recorded_at, field, value, previous_value, source, changed_by, scope, generation, boot_id, note}."""
    last = last_by_field or {}
    first_boot = not last
    fields = snapshot.get("fields") or {}
    rows = []
    stamp = recorded_at or _now()
    for field in models.SNAPSHOT_FIELDS:
        cell = fields.get(field)
        if not isinstance(cell, dict):
            continue   # un snapshot recortado no inventa el campo
        enc = _encode(cell.get("value"))
        prev_row = last.get(field)
        prev = None
        if isinstance(prev_row, dict):
            prev = prev_row.get("value")
        elif prev_row is not None:
            prev = str(prev_row)
        if prev_row is not None and prev == enc:
            continue
        rows.append({
            "recorded_at": stamp,
            "field": field,
            "value": enc,
            "previous_value": prev,
            "source": str(cell.get("source")),
            "changed_by": changed_by,
            "scope": _scope_of(field),
            "generation": snapshot.get("generation"),
            "boot_id": boot_id or BOOT_ID,
            "note": (NOTE_FIRST_BOOT if first_boot else (NOTE_NEW_FIELD if prev_row is None else None)),
        })
    return rows


def _baseline_from(snapshot):
    return {f: _encode((snapshot.get("fields") or {}).get(f, {}).get("value")) for f in models.SNAPSHOT_FIELDS
            if f in (snapshot.get("fields") or {})}


def _write(rows):
    """Escribe vía S4 y devuelve (n_written, rejected). Lanza: el llamador clasifica."""
    if not rows:
        return 0, []
    res = db.config_ledger_append(rows)
    if isinstance(res, dict):
        return int(res.get("n_written") or 0), list(res.get("rejected") or [])
    return len(rows), []


def boot(env=None, today=None, extra=None):
    """El diff al ARRANQUE (I). Nunca lanza: todo fallo queda en _LEDGER_STATE y en el dict devuelto.
    Devuelve {state, boot_id, booted_at, first_boot, n_fields, n_rows_written, changed_fields[], rejected[],
    error, snapshot}. `env`/`today`/`extra` inyectables para los smokes (producción: os.environ, fecha UTC).
    Serializado por _LOCK (corrector): comparte baseline con observe()."""
    with _LOCK:
        return _boot_locked(env, today, extra)


def _boot_locked(env=None, today=None, extra=None):
    S = _LEDGER_STATE
    out = {"state": None, "boot_id": BOOT_ID, "booted_at": _now_iso(), "first_boot": None,
           "n_fields": len(models.SNAPSHOT_FIELDS), "n_rows_written": 0, "changed_fields": [],
           "rejected": [], "error": None, "snapshot": None}
    try:
        snap = take_snapshot(env, today, extra)
        out["snapshot"] = snap
        S["last"] = _baseline_from(snap)
        S["last_signature"] = snap.get("panel_signature")
        S["booted_at"] = out["booted_at"]
        enabled, _src = _enabled(env)
        if not enabled:
            S["state"] = out["state"] = STATE_KILL
            return out
        last = db.config_ledger_last_by_field() or {}
        out["first_boot"] = not last
        rows = diff_rows(snap, last, CHANGED_BY_BOOT, boot_id=BOOT_ID)
        n, rejected = _write(rows)
        out["n_rows_written"] = n
        out["changed_fields"] = [r["field"] for r in rows]
        out["rejected"] = rejected
        S["n_written_boot"] += n
        S["rejected"] = rejected
        S["state"] = out["state"] = STATE_OK
        S["last_error"] = None
    except Exception as e:   # un fallo del ledger JAMÁS impide el arranque
        st = STATE_TABLE_MISSING if _is_table_missing(e) else f"error: {type(e).__name__}"
        S["state"] = out["state"] = st
        S["last_error"] = out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def observe(snapshot=None, env=None, today=None):
    """El diff EN CORRIDA (E): compara `snapshot` (el de stage.models; None → se toma uno) con la baseline
    `_LEDGER_STATE['last']` y appendea SÓLO lo que difiere, `changed_by 'system:runtime-diff'`. Sin baseline
    (lifespan no corrió) la toma de la BD una vez. JAMÁS lanza. Devuelve {state, n_written, changed_fields[],
    baseline, error}. Serializado por _LOCK (corrector): dos workers que observan el MISMO cambio a la vez no
    duplican una fila runtime-diff — el segundo compara contra la baseline ya avanzada y escribe 0."""
    with _LOCK:
        return _observe_locked(snapshot, env, today)


def _observe_locked(snapshot=None, env=None, today=None):
    S = _LEDGER_STATE
    out = {"state": S["state"], "n_written": 0, "changed_fields": [], "baseline": "memory", "error": None}
    try:
        S["observed_at"] = _now_iso()
        S["n_observed"] += 1
        snap = snapshot if isinstance(snapshot, dict) and snapshot.get("fields") else take_snapshot(env, today)
        enabled, _src = _enabled(env)
        if not enabled:
            out["state"] = STATE_KILL
            S["last"] = _baseline_from(snap)
            return out
        if S["last"] is None:
            last = db.config_ledger_last_by_field() or {}
            S["last"] = {f: (r.get("value") if isinstance(r, dict) else str(r)) for f, r in last.items()}
            out["baseline"] = "db"
        current = _baseline_from(snap)
        changed = [f for f in models.SNAPSHOT_FIELDS if f in current and current.get(f) != S["last"].get(f)]
        if not changed:
            return out
        last_rows = {f: {"value": S["last"].get(f)} for f in S["last"]}
        rows = [r for r in diff_rows(snap, last_rows, CHANGED_BY_RUNTIME, boot_id=BOOT_ID) if r["field"] in changed]
        for r in rows:
            r["note"] = "runtime-diff (cambio sin reinicio: reloj/auto-retire)"
        n, rejected = _write(rows)
        out["n_written"] = n
        out["changed_fields"] = [r["field"] for r in rows]
        S["n_written_runtime"] += n
        if rejected:
            S["rejected"] = rejected
        S["last"] = current
        S["last_signature"] = snap.get("panel_signature")
        if S["state"] in (STATE_NOT_BOOTED,):
            S["state"] = STATE_OK
        out["state"] = S["state"]
    except Exception as e:
        st = STATE_TABLE_MISSING if _is_table_missing(e) else f"error: {type(e).__name__}"
        out["state"] = st
        out["error"] = S["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def current(env=None, today=None, extra=None):
    """El bloque `current` de /config-history (I) y `models_effective` de consulta_sistema — la MISMA
    función, así las dos puertas dicen lo mismo: {recorded_at (el último boot; null sin lifespan), boot_id,
    generation, generation_source, panel_signature, fields, warnings, unknown_models, actor_state}."""
    snap = take_snapshot(env, today, extra)
    return {"recorded_at": _LEDGER_STATE["booted_at"], "boot_id": BOOT_ID,
            "generation": snap["generation"], "generation_source": snap["generation_source"],
            "table_version": snap["table_version"], "table_as_of": snap["table_as_of"],
            "panel_signature": snap["panel_signature"], "fields": snap["fields"],
            "warnings": snap["warnings"], "unknown_models": snap["unknown_models"],
            "actor_state": ACTOR_STATE}


def state_view():
    """El estado del ESCRITOR para /config-history.ledger_state y consulta_sistema.config.ledger."""
    S = _LEDGER_STATE
    return {"state": S["state"], "boot_id": BOOT_ID, "booted_at": S["booted_at"],
            "n_written_boot": S["n_written_boot"], "n_written_runtime": S["n_written_runtime"],
            "n_observed": S["n_observed"], "observed_at": S["observed_at"],
            "rejected": list(S["rejected"]), "last_error": S["last_error"], "states_rule": STATES_RULE}


def listing(limit=LEDGER_LIST_LIMIT):
    """Lectura de la tabla para /config-history y consulta_sistema: {rows (recorded_at DESC, serializados),
    state (None = lectura OK; si no, el estado que manda), n_rows (COUNT real si la tabla existe), last_recorded_at}.
    Nunca lanza."""
    out = {"rows": [], "state": None, "n_rows": None, "last_recorded_at": None}
    try:
        rows = db.config_ledger_list(limit=limit) or []
        ser = []
        for r in rows:
            d = dict(r)
            for k, v in list(d.items()):
                if isinstance(v, datetime.datetime):
                    if v.tzinfo is None:
                        v = v.replace(tzinfo=datetime.timezone.utc)
                    d[k] = v.isoformat(timespec="seconds")
            ser.append(d)
        out["rows"] = ser
        out["last_recorded_at"] = ser[0].get("recorded_at") if ser else None
        table = getattr(db, LEDGER_TABLE, None)
        if table is not None:
            from sqlalchemy import func, select
            with db.engine().begin() as cx:
                out["n_rows"] = int(cx.execute(select(func.count()).select_from(table)).scalar() or 0)
        else:
            out["n_rows"] = len(ser)
    except Exception as e:
        out["state"] = STATE_TABLE_MISSING if _is_table_missing(e) else f"error: {type(e).__name__}"
    return out
