"""
db.py — identity + session store for the webapp backend (block 2, ADR-0047/0048).

Postgres on Dokploy in prod (decision 1, ADR-0047), SQLite for dev/smokes — one code path via
SQLAlchemy Core. Engine URL from WITT_BACKEND_DB_URL (e.g. postgresql+psycopg://user:pw@host/witt);
defaults to a local SQLite file (gitignored) so dev works with zero setup.

Security model (decisions 3/4/9-bis of the webapp handoff):
  - 5 flat-permission accounts; the ONE asymmetry (create users / reset passwords / disable) lives in
    seed_users.py, run by Emmanuel LOCALLY — it is deliberately NOT exposed over HTTP.
  - The only secret is username+password (corte de secrets). Passwords are hashed with stdlib
    hashlib.scrypt (n=2^14, r=8, p=1) + per-user random salt; no external crypto dependency.
  - Sessions are opaque bearer tokens (secrets.token_urlsafe). The DB stores ONLY sha256(token) —
    a leaked DB does not leak usable tokens. Expiry enforced on every lookup.
"""
import datetime
import hashlib
import json
import hmac
import os
import secrets
from pathlib import Path

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text,
                        create_engine, delete, func, select)

_SERVICE_DIR = Path(__file__).resolve().parent
DB_URL = os.environ.get("WITT_BACKEND_DB_URL", f"sqlite:///{_SERVICE_DIR / 'backend.db'}")
SESSION_TTL_HOURS = int(os.environ.get("WITT_SESSION_TTL_HOURS", "72"))

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("user_id", String(64), primary_key=True),          # login name: marcelo|natalia|martin|emmanuel|sharon
    Column("display_name", String(128), nullable=False),
    Column("role", String(16), nullable=False),               # rater_profile: 'medico' | 'dev' (flat permissions)
    Column("pw_hash", String(64), nullable=False),            # hex(scrypt)
    Column("pw_salt", String(32), nullable=False),            # hex(16 bytes)
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("disabled", Boolean, nullable=False, default=False),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),       # sha256(bearer token) — raw token never stored
    Column("user_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

# --- run model + event log (block 3, ADR-0050) ------------------------------------------------------
# The backend persists the frozen record and the audit verdict (ADR-0047 decision 2: the webapp only
# reads). run_events is the ONE log both the live SSE trace and the replay read — two readers, one
# source, so they cannot contradict each other. Events and records are append-only; measurement fields
# freeze at frozen_at (closure); ratings[] (a later block) append after it.

RUN_STATES = ("queued", "running", "awaiting_closure", "closed", "failed", "cancelled")

runs = Table(
    "runs", metadata,
    Column("run_id", String(64), primary_key=True),
    Column("run_no", Integer),                                # ADR-0076: el NÚMERO de corrida — la identidad
                                                              # legible (1, 2, 3… al nacer); único por índice.
                                                              # run_id sigue siendo la llave técnica.
    Column("user_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("question", Text, nullable=False),
    Column("entities_csv", Text, nullable=False, default=""),
    Column("state", String(24), nullable=False),              # RUN_STATES
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("frozen_at", DateTime(timezone=True)),             # closure stamp (explicit, user-driven)
    Column("closed_by", String(64)),
    Column("last_event_at", DateTime(timezone=True)),         # heartbeat: 'no event for N min' detector
    Column("claimed_by", String(64)),                         # ADR-0078: QUÉ worker (nombre de hilo) la
    Column("claimed_at", DateTime(timezone=True)),            # reclamó y CUÁNDO — null = nadie declaró
    Column("cancel_requested", Boolean, nullable=False, default=False),
    Column("cancelled_by", String(64)),                       # LOTE-01·A3: a cancellation without an author
    Column("cancel_reason", Text),                            # is a hole in the registry (ERP rule)
    Column("usage_json", Text),                               # LOTE-01·A4: spend persists on EVERY exit path
    Column("epistemic_summary_json", Text),                   # LOTE-02·3: derived AT FREEZE, never at serve
    Column("error", Text),
    Column("plan_json", Text),                                # ADR-0061: el plan declarado, copiado al encolar
    Column("bundle_json", Text),                              # the full evidence bundle (ADR-0043/0044)
    Column("frozen_record_json", Text),                       # the frozen record the UI renders (read-only)
)

plans = Table(
    # ADR-0061 (tapón 3): el plan declarado ANTES de encolar — el checkpoint humano del boceto M3.
    # Server-side por procedencia: el cliente refiere plan_id, jamás re-manda el objeto (tamper).
    "plans", metadata,
    Column("plan_id", String(64), primary_key=True),
    Column("user_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("question", Text, nullable=False),
    Column("entities_csv", Text, nullable=False, default=""),
    Column("plan_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("run_id", String(64)),                             # sellado al consumirse (un plan, una corrida)
)

run_events = Table(
    "run_events", metadata,
    Column("run_id", String(64), ForeignKey("runs.run_id"), primary_key=True),
    Column("seq", Integer, primary_key=True),                 # monotonic per run — replay == live order
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("type", String(64), nullable=False),               # run.state | stage.* | audit.* | error
    Column("agent", String(64)),
    Column("tool", String(64)),
    Column("level", String(16), nullable=False, default="info"),
    Column("degraded", String(64)),                           # epistemic state travels WITH the event
    Column("payload_json", Text),
)

# --- ratings (M5, tapón 4 de PENDIENTES DE BACK; ADR-0064) -------------------------------------------
# The two-zone rule of the frozen record (registro-congelado.md): run MEASUREMENTS freeze at frozen_at
# and never change; ratings[] APPEND after it. Structurally that means ratings live in their OWN
# append-only table and are MERGED into the record at read time — the frozen blob itself never mutates.
# Provenance fields (rated_by, rater_profile, is_author, instrument, saw_answer_before_rating) are
# DERIVED server-side from the session + the run, never taken from the client (same principle as
# ADR-0056: the signer is derived; a falsifiable `by` is ignored).

RATING_INPUT_STATES = ("value", "cannot-rate")
RATING_OUTPUT_STATES = ("value", "cannot-rate", "not-applicable")
RATABLE_STATES = ("awaiting_closure", "closed", "failed", "cancelled")   # never queued/running

run_ratings = Table(
    "run_ratings", metadata,
    Column("run_id", String(64), ForeignKey("runs.run_id"), primary_key=True),
    Column("seq", Integer, primary_key=True),                 # append-only: corrections are NEW rows
    Column("rated_by", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("rated_at", DateTime(timezone=True), nullable=False),
    Column("rater_profile", String(16), nullable=False),      # snapshot of user.role at rating time
    Column("is_author", Boolean, nullable=False),             # derived: rated_by == run.user_id
    Column("blind", Boolean, nullable=False, default=False),  # webapp instrument is NOT blind (v1);
    Column("saw_answer_before_rating", Boolean, nullable=False),  # the blind instrument is the CSV bank
    Column("instrument", String(32), nullable=False),         # m5-cierre (author) | m5-consenso (rest)
    Column("rating_input", Integer),                          # 1-5 | null ([?] no la puedo calificar)
    Column("rating_input_state", String(16), nullable=False),
    Column("rating_output", Integer),                         # 1-5 | null (cannot-rate / not-applicable)
    Column("rating_output_state", String(16), nullable=False),
    # DOS notas, no una (M5 v2, ADR-0075). El banco de calibración v1 midió que el texto libre fue lo
    # ÚNICO que produjo diagnóstico accionable (68 celdas de comentario dieron TODOS los hallazgos; los
    # cinco ejes categóricos casi nada) y que la ATRIBUCIÓN sólo fue posible porque había DOS columnas
    # separadas (P_comentario sobre la pregunta / R_que_falta sobre la respuesta). Con un solo campo no
    # se sabe de qué habla el comentario. `note` queda re-clavada a la RESPUESTA; `note_question` es la
    # de la PREGUNTA, y va SIEMPRE VISIBLE y opcional: medido sobre las hojas reales, un disparador
    # condicional habría OCULTADO 7 de los 9 comentarios de pregunta que Martín sí escribió (9/11 = 82%
    # de sus filas), que fue su aporte principal.
    Column("note", Text, nullable=False, default=""),
    Column("note_question", Text, nullable=False, default=""),
)

# APUNTES (2026-09-04, pedido del fundador): el cuaderno de teorías e ideas. NO son las notas
# de calificación de arriba y por eso no comparten tabla ni palabra: aquéllas van clavadas a
# UNA corrida terminada, son append-only y se enmascaran (el juicio no se contamina); un
# apunte es texto LIBRE del autor, editable, que puede citar varias corridas, genes y nichos
# —o ninguno— y existe antes de que haya corrida alguna.
#
# Los enlaces van en CSV como en runs.entities_csv y plans.entities_csv (mismo patrón
# incumbente; son listas cortas). Se guardan como el autor los escribió: la RESOLUCIÓN contra
# el store verificado la hace /resolve cuando el lector la pide — un apunte puede citar un gen
# que la DI todavía no conoce, y eso es información, no error.
#
# `visibility` por APUNTE (no política global): 'private' por default — quien escribe decide
# qué comparte, apunte por apunte. Un apunte compartido lo LEE cualquier cuenta; escribirlo
# sigue siendo sólo del autor.
notes = Table(
    "notes", metadata,
    Column("note_id", String(64), primary_key=True),
    Column("author_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("title", String(300), nullable=False, default=""),
    Column("body", Text, nullable=False, default=""),
    Column("visibility", String(16), nullable=False, default="private"),  # private | shared
    Column("run_ids_csv", Text, nullable=False, default=""),    # corridas citadas
    Column("entities_csv", Text, nullable=False, default=""),   # genes citados (sin resolver)
    Column("niches_csv", Text, nullable=False, default=""),     # nichos citados
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# COMENTARIOS DE CORRIDA (ADR-0077, 2026-09-06): la conversación del equipo SOBRE la pregunta de
# una corrida. Anexo append-only y PÚBLICO (toda sesión válida lee y escribe; permisos planos,
# ADR-0047). No toca la corrida, ni el registro congelado, ni las calificaciones (M5: juicio con
# instrumento), ni los apuntes (teorías que existen ANTES de la pregunta). Sin borrado ni edición:
# lo dicho queda dicho, con autor y hora.
run_comments = Table(
    "run_comments", metadata,
    Column("comment_id", String(64), primary_key=True),
    Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
    Column("author_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# BORRADORES DE PREGUNTA (2026-09-04): lo que el agente redacta DESDE un apunte. Se persisten
# porque el fundador quiere DEPURAR la estructura con resultados: sin registro no hay
# calibración. Cada borrador guarda la VERSIÓN DE LA ESPECIFICACIÓN que lo produjo, así que
# refinar la spec no reescribe la historia — un borrador viejo sigue siendo atribuible a la
# regla que lo redactó.
#
# `run_id` se sella al consumirse, igual que plans.run_id: ese sello es el que cierra el lazo
# de calibración — el borrador se vuelve corrida, la corrida se califica en el EJE PREGUNTA
# (rating_input, re-anclado al TAMAÑO en ADR-0075), y el `fits_one_run` que el agente afirmó
# queda enfrentado a lo que el humano midió.
note_questions = Table(
    "note_questions", metadata,
    Column("question_id", String(64), primary_key=True),
    Column("note_id", String(64), ForeignKey("notes.note_id"), nullable=False),
    Column("author_id", String(64), ForeignKey("users.user_id"), nullable=False),
    Column("spec_version", String(16), nullable=False),   # QUESTION_SPEC_VERSION que lo redactó
    Column("model", String(64), nullable=False),
    Column("state", String(16), nullable=False),          # drafted | errored
    Column("question", Text, nullable=False, default=""),
    Column("entities_csv", Text, nullable=False, default=""),
    Column("draft_json", Text, nullable=False),           # la estructura COMPLETA, verbatim
    Column("usage_json", Text),                           # el gasto, declarado
    Column("error", Text),                                # el agente puede fallar sin tumbar nada
    Column("run_id", String(64)),                         # sellado al consumirse (una corrida)
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, future=True)
    return _engine


def init_db():
    metadata.create_all(engine())
    _migrate()


def _migrate():
    """Additive column migrations for PRE-EXISTING tables — create_all never ALTERs, and the prod
    Postgres already holds runs (ADR-0050). Idempotent: each ADD COLUMN is tried and silently skipped
    when the column exists (works on SQLite and Postgres). Additive-only by policy; a destructive
    migration would need its own ADR."""
    from sqlalchemy import text
    # ADR-0078: el tipo fecha se compila con el DIALECTO (SQLite -> DATETIME, Postgres -> TIMESTAMP WITH
    # TIME ZONE). Un literal DATETIME fallaría en Postgres, el except lo callaría, la columna no existiría
    # y claim_next_queued rompería en prod — un fallback disfrazado de migración idempotente.
    _dt_type = DateTime(timezone=True).compile(dialect=engine().dialect)
    for stmt in ("ALTER TABLE runs ADD COLUMN cancelled_by VARCHAR(64)",
                 "ALTER TABLE runs ADD COLUMN cancel_reason TEXT",
                 "ALTER TABLE runs ADD COLUMN usage_json TEXT",
                 "ALTER TABLE runs ADD COLUMN epistemic_summary_json TEXT",
                 "ALTER TABLE runs ADD COLUMN plan_json TEXT",
                 # ADR-0076: el número de corrida. Su backfill y su índice único van abajo.
                 "ALTER TABLE runs ADD COLUMN run_no INTEGER",
                 # M5 v2 (ADR-0075): la nota de la PREGUNTA, separada de la de la respuesta. DEFAULT ''
                 # para que el ADD COLUMN sea legal sobre la tabla que YA tiene filas en el Postgres de
                 # producción (la calificación real de 4d046355) sin reescribirla — y para que esa fila
                 # quede con '' = "el instrumento no lo pidió", jamás confundible con "no tenía nada que
                 # decir": las filas pre-v2 se distinguen porque su `note` es la única que existió.
                 "ALTER TABLE run_ratings ADD COLUMN note_question TEXT DEFAULT ''",
                 # ADR-0078: quién reclamó la corrida y cuándo — el insumo del reaper y de la vista.
                 "ALTER TABLE runs ADD COLUMN claimed_by VARCHAR(64)",
                 f"ALTER TABLE runs ADD COLUMN claimed_at {_dt_type}"):
        try:
            with engine().begin() as cx:
                cx.execute(text(stmt))
        except Exception:
            pass  # column already there
    # ADR-0076 — backfill del NÚMERO de corrida para las que nacieron antes de la columna: en orden de
    # creación (la más vieja = 1; empate por run_id, así el resultado es determinista), continuando
    # después del máximo que ya exista. Es asignación de identidad sobre un hecho que ya estaba en el
    # registro (created_at), no una re-medición; corre UNA vez por corrida (sólo las que tienen NULL).
    # Después, el índice ÚNICO: dos corridas con el mismo número serían el defecto que este número quita.
    try:
        with engine().begin() as cx:
            maximo = cx.execute(select(func.max(runs.c.run_no))).scalar() or 0
            faltan = cx.execute(select(runs.c.run_id)
                                .where(runs.c.run_no.is_(None))
                                .order_by(runs.c.created_at.asc(), runs.c.run_id.asc())).all()
            for i, r in enumerate(faltan, start=1):
                cx.execute(runs.update().where(runs.c.run_id == r._mapping["run_id"])
                           .values(run_no=maximo + i))
            cx.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_runs_run_no ON runs (run_no)"))
    except Exception as e:  # una corrida sin número se DECLARA en la UI; aquí queda la huella
        import sys as _sys
        print(f"[db._migrate] ADR-0076 backfill/índice de run_no no aplicó: {e!r}", file=_sys.stderr)
    # Backfill (LOTE-02·3): derive the epistemic summary for runs frozen BEFORE this column existed.
    # Derived exclusively FROM frozen values (retrieval_summary/audit/confidence of the frozen record),
    # so the at-freeze discipline holds — this is a re-read of frozen data, not a re-measurement.
    import json as _json
    try:
        with engine().begin() as cx:
            rows = cx.execute(select(runs.c.run_id, runs.c.frozen_record_json)
                              .where(runs.c.frozen_record_json.isnot(None),
                                     runs.c.epistemic_summary_json.is_(None))).all()
            for r in rows:
                rec = _json.loads(r._mapping["frozen_record_json"])
                conf = rec.get("confidence") or {}
                summ = {"retrieval_mode": (rec.get("retrieval_summary") or {}).get("mode"),
                        "verdict": (rec.get("audit") or {}).get("verdict"),
                        "confidence_state": conf.get(
                            "state", "value" if (rec.get("answer") or {}).get("stated_confidence")
                            is not None else "absent-not-calibratable"),
                        "panel_n_valid": (rec.get("audit") or {}).get("n_valid")}
                cx.execute(runs.update().where(runs.c.run_id == r._mapping["run_id"])
                           .values(epistemic_summary_json=_json.dumps(summ, ensure_ascii=False)))
    except Exception:
        pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _scrypt(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                          n=2 ** 14, r=8, p=1, dklen=32).hex()


def upsert_user(user_id: str, display_name: str, role: str, password: str):
    """Create or update an account (seed_users.py only — never over HTTP)."""
    if role not in ("medico", "dev"):
        raise ValueError("role must be 'medico' or 'dev' (flat permissions, no observador in v1)")
    salt = secrets.token_bytes(16).hex()
    row = {"user_id": user_id, "display_name": display_name, "role": role,
           "pw_hash": _scrypt(password, salt), "pw_salt": salt,
           "created_at": _now(), "disabled": False}
    with engine().begin() as cx:
        existing = cx.execute(select(users.c.user_id).where(users.c.user_id == user_id)).first()
        if existing:
            cx.execute(users.update().where(users.c.user_id == user_id).values(
                display_name=display_name, role=role, pw_hash=row["pw_hash"],
                pw_salt=salt, disabled=False))
        else:
            cx.execute(users.insert().values(**row))


def set_disabled(user_id: str, disabled: bool = True):
    with engine().begin() as cx:
        cx.execute(users.update().where(users.c.user_id == user_id).values(disabled=disabled))
        if disabled:  # a disabled account keeps no live sessions
            cx.execute(delete(sessions).where(sessions.c.user_id == user_id))


def list_users():
    with engine().begin() as cx:
        return [dict(r._mapping) for r in cx.execute(
            select(users.c.user_id, users.c.display_name, users.c.role,
                   users.c.created_at, users.c.disabled))]


def check_password(user_id: str, password: str):
    """Constant-time verify. Returns the user row (dict) or None."""
    with engine().begin() as cx:
        row = cx.execute(select(users).where(users.c.user_id == user_id)).first()
    if row is None or row._mapping["disabled"]:
        _scrypt(password, "00" * 16)  # burn the same work on unknown users (timing uniformity)
        return None
    m = row._mapping
    if hmac.compare_digest(_scrypt(password, m["pw_salt"]), m["pw_hash"]):
        return {"user_id": m["user_id"], "display_name": m["display_name"], "role": m["role"]}
    return None


def create_session(user_id: str) -> dict:
    """Mint an opaque bearer token; only its sha256 is persisted. Returns the raw token ONCE."""
    token = secrets.token_urlsafe(32)
    expires = _now() + datetime.timedelta(hours=SESSION_TTL_HOURS)
    with engine().begin() as cx:
        cx.execute(sessions.insert().values(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user_id, created_at=_now(), expires_at=expires))
    return {"token": token, "expires_at": expires.isoformat(timespec="seconds")}


def validate_token(token: str):
    """Bearer token -> user dict, or None (unknown / expired / disabled)."""
    if not token:
        return None
    th = hashlib.sha256(token.encode()).hexdigest()
    with engine().begin() as cx:
        row = cx.execute(
            select(users.c.user_id, users.c.display_name, users.c.role,
                   users.c.disabled, sessions.c.expires_at)
            .select_from(sessions.join(users, sessions.c.user_id == users.c.user_id))
            .where(sessions.c.token_hash == th)).first()
        if row is None:
            return None
        m = row._mapping
        exp = m["expires_at"]
        if exp.tzinfo is None:  # SQLite drops tzinfo; stored values are UTC by construction
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        if m["disabled"] or exp < _now():
            cx.execute(delete(sessions).where(sessions.c.token_hash == th))
            return None
    return {"user_id": m["user_id"], "display_name": m["display_name"], "role": m["role"]}


def revoke_token(token: str):
    with engine().begin() as cx:
        cx.execute(delete(sessions).where(
            sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest()))


# --- run helpers (block 3, ADR-0050) -----------------------------------------------------------------

def _dt_utc(v):
    """SQLite drops tzinfo; stored values are UTC by construction — normalize on read."""
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=datetime.timezone.utc)
    return v


def create_run(run_id: str, user_id: str, question: str, entities=None, plan_json=None):
    """ADR-0076: el NÚMERO de corrida se asigna AQUÍ, al nacer — MAX(run_no)+1 dentro de la misma
    transacción del INSERT. Si dos corridas se encolan a la vez y leen el mismo máximo (Postgres en
    READ COMMITTED lo permite), el índice único ix_runs_run_no rechaza a la segunda y ésta reintenta
    con el número siguiente. Sin fallback a null: una corrida sin número sería la ambigüedad que el
    número elimina. Devuelve el número asignado."""
    from sqlalchemy.exc import IntegrityError
    ultimo_error = None
    for _intento in range(5):
        try:
            with engine().begin() as cx:
                siguiente = (cx.execute(select(func.max(runs.c.run_no))).scalar() or 0) + 1
                cx.execute(runs.insert().values(run_id=run_id, run_no=siguiente, user_id=user_id,
                                                question=question,
                                                entities_csv=",".join(entities or []), state="queued",
                                                created_at=_now(), cancel_requested=False,
                                                plan_json=plan_json))
            return siguiente
        except IntegrityError as e:
            # sólo se reintenta la CARRERA del número; un run_id repetido es otro defecto y sube tal cual
            if "run_no" not in str(e.orig).lower():
                raise
            ultimo_error = e
    raise ultimo_error


def create_plan(plan_id: str, user_id: str, question: str, entities, plan_json: str):
    with engine().begin() as cx:
        cx.execute(plans.insert().values(plan_id=plan_id, user_id=user_id, question=question,
                                         entities_csv=",".join(entities or []),
                                         plan_json=plan_json, created_at=_now()))


def get_plan(plan_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(plans).where(plans.c.plan_id == plan_id)).first()
    return dict(row._mapping) if row else None


def mark_plan_used(plan_id: str, run_id: str):
    """Un plan se consume por UNA corrida: re-usarlo silencioso haría pasar un juicio viejo como
    fresco. El sello no borra nada — deja la traza plan->corrida."""
    with engine().begin() as cx:
        n = cx.execute(plans.update()
                       .where(plans.c.plan_id == plan_id, plans.c.run_id.is_(None))
                       .values(run_id=run_id)).rowcount
    return n == 1


def plan_history(limit=200):
    """Insumo DETERMINISTA de las estimaciones del plan (LOTE-01: 'estimaciones con historia').
    Corridas que completaron el pipeline (awaiting_closure/closed), con costo, duración y qué decisor
    de fallback disparó — la mediana se calcula en runs.plan_estimates(), NUNCA la estima un modelo
    (constitución: proyección = tool/script desde insumos declarados)."""
    with engine().begin() as cx:
        rows = cx.execute(select(runs.c.started_at, runs.c.finished_at, runs.c.usage_json,
                                 runs.c.frozen_record_json)
                          .where(runs.c.state.in_(("awaiting_closure", "closed")))
                          .order_by(runs.c.created_at.desc()).limit(limit)).all()
    out = []
    for r in rows:
        d = r._mapping
        try:
            cost = (json.loads(d["usage_json"]) or {}).get("estimated_cost_usd") if d["usage_json"] else None
        except Exception:
            cost = None
        try:
            trigger = ((json.loads(d["frozen_record_json"]) or {}).get("fallback") or {}).get("trigger")                 if d["frozen_record_json"] else None
        except Exception:
            trigger = None
        dur = None
        if d["started_at"] and d["finished_at"]:
            dur = ( _dt_utc(d["finished_at"]) - _dt_utc(d["started_at"]) ).total_seconds()
        out.append({"cost_usd": cost, "duration_s": dur, "trigger": trigger})
    return out


def claim_next_queued(worker_id=None):
    """Atomically claim the oldest queued run (optimistic UPDATE ... WHERE state='queued'). Returns the
    run row (dict) or None. FIFO by created_at.

    ADR-0078: `worker_id` (el nombre del hilo) queda en runs.claimed_by y el instante en claimed_at —
    la procedencia del reclamo. Sin worker_id (llamadores viejos: smokes, harness) claimed_by queda
    NULL = "nadie declaró quién", que es distinto de un nombre y se sirve así. El dict devuelto lleva
    los valores ESCRITOS (no el SELECT previo al UPDATE), para que el llamador vea lo que quedó."""
    with engine().begin() as cx:
        row = cx.execute(select(runs).where(runs.c.state == "queued")
                         .order_by(runs.c.created_at).limit(1)).first()
        if row is None:
            return None
        ahora = _now()
        n = cx.execute(runs.update()
                       .where(runs.c.run_id == row._mapping["run_id"], runs.c.state == "queued")
                       .values(state="running", started_at=ahora,
                               claimed_by=worker_id, claimed_at=ahora)).rowcount
        if n != 1:  # another worker won the race
            return None
        d = dict(row._mapping)
        d.update(state="running", started_at=ahora, claimed_by=worker_id, claimed_at=ahora)
        return d


REAP_REASONS = ("worker-lost", "worker-lost-restart")


def reap_stale_running(stale_s, now=None, reason="worker-lost", stale_s_source=None):
    """ADR-0078 — el segador de corridas huérfanas. Una corrida 'running' cuyo último latido
    (last_event_at; si es null, started_at; si también, created_at) es más viejo que `stale_s` segundos
    perdió a su worker (proceso reiniciado, hilo muerto): pasa a state='failed' con finished_at, error
    'worker-lost: …' y UN evento run.state {state:'failed', reason, stale_s, stale_s_source, idle_s,
    ref_field} vía add_event — la misma bitácora que lee la traza.

    `reason` ∈ REAP_REASONS: 'worker-lost' (ronda periódica: sin latido por > stale_s) |
    'worker-lost-restart' (arranque del proceso: con `--workers 1`, ADR-0048, NINGUNA fila running tiene
    worker en un proceso recién nacido — se llama con stale_s=0). El prefijo del error es SIEMPRE
    'worker-lost:' para que la vista lo distinga de un fallo del pipeline (failure_reason en _run_view).

    Corrector ADR-0078 (2026-09-14), la carrera reaper ↔ worker vivo, en las DOS direcciones:
      (a) el UPDATE exige que el campo de referencia siga valiendo lo que se midió (WHERE state='running'
          AND <ref_field> = <valor leído>): si el worker latió entre el SELECT y el UPDATE, rowcount 0 y
          no se toca;
      (b) la fila segada queda con cancel_requested=True (cancelled_by 'run-reaper', cancel_reason =
          reason): si el hilo seguía vivo, _check_cancel lo aborta en la siguiente frontera de etapa y
          deja de gastar modelo; su cierre pasa por finish_run (WHERE state='running'), que ya no pisa.

    NUNCA re-encola: re-ejecutar solo sería gastar modelo sin que nadie lo pidiera (la casa: nada se
    re-ejecuta solo). El usage_json de la corrida se deja como esté (lo que gastó antes de morir, si
    quedó escrito; si no, ausente-declarado — no se inventa). Devuelve la lista de run_ids segados
    (vacía = nada que segar). `now` inyectable para pruebas offline."""
    if reason not in REAP_REASONS:
        raise ValueError(f"reap reason {reason!r} not in {REAP_REASONS}")
    ahora = now or _now()
    stale_s = float(stale_s)
    with engine().begin() as cx:
        vivas = cx.execute(select(runs.c.run_id, runs.c.last_event_at, runs.c.started_at,
                                  runs.c.created_at)
                           .where(runs.c.state == "running")).all()
    segadas = []
    for r in vivas:
        m = r._mapping
        ref_field = next((k for k in ("last_event_at", "started_at", "created_at") if m[k] is not None),
                         None)
        if ref_field is None:   # fila sin ninguna fecha: no se puede medir la edad — no se toca
            continue
        idle_s = (ahora - _dt_utc(m[ref_field])).total_seconds()
        if idle_s <= stale_s:
            continue
        if reason == "worker-lost-restart":
            error = "worker-lost: proceso reiniciado, la corrida running no tiene worker (ADR-0078)"
        else:
            error = f"worker-lost: sin latido por >{int(stale_s)} s (ADR-0078)"
        with engine().begin() as cx:
            n = cx.execute(runs.update()
                           .where(runs.c.run_id == m["run_id"], runs.c.state == "running",
                                  getattr(runs.c, ref_field) == m[ref_field])
                           .values(state="failed", finished_at=ahora, error=error,
                                   cancel_requested=True, cancelled_by="run-reaper",
                                   cancel_reason=reason)).rowcount
        if n != 1:   # el worker sí vivía (latió o cerró la corrida en medio): no se pisa
            continue
        add_event(m["run_id"], "run.state",
                  payload={"state": "failed", "reason": reason, "stale_s": stale_s,
                           "stale_s_source": stale_s_source, "idle_s": round(idle_s, 1),
                           "ref_field": ref_field, "error": error},
                  agent="run-reaper", level="error")
        segadas.append(m["run_id"])
    return segadas


def get_run(run_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(runs).where(runs.c.run_id == run_id)).first()
    if row is None:
        return None
    d = dict(row._mapping)
    for k in ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at", "claimed_at"):
        d[k] = _dt_utc(d.get(k))
    return d


def list_runs(user_id=None, limit=50):
    """List rows carry the SAME field set the detail view derives from (LOTE-01·A1): heartbeat inputs,
    cancellation authorship and usage — a stuck run must be distinguishable from the LIST, and the
    datetime normalization must match the detail (SQLite drops tzinfo).

    2026-08-29: entities_csv y plan_json ENTRAN al SELECT — la lista los omitía, así que sus
    derivados (genes por renglón, plan_declared, plan_niches) salían vacíos SOLO en la lista
    mientras el detalle sí los servía: la promesa misma-vista de este docstring estaba rota
    para esos campos. _run_view deriva y DESCARTA el blob (plan_json jamás viaja al renglón).
    2026-09-05 (ADR-0076): run_no ENTRA al SELECT — mismo riesgo, misma lección.
    2026-09-14 (ADR-0078): claimed_by/claimed_at ENTRAN al SELECT — la lista debe poder decir qué
    worker tiene cada corrida, igual que el detalle."""
    with engine().begin() as cx:
        q = select(runs.c.run_id, runs.c.run_no, runs.c.user_id, runs.c.question, runs.c.entities_csv,
                   runs.c.state,
                   runs.c.created_at, runs.c.started_at, runs.c.finished_at, runs.c.frozen_at,
                   runs.c.last_event_at, runs.c.claimed_by, runs.c.claimed_at,
                   runs.c.cancelled_by, runs.c.cancel_reason,
                   runs.c.usage_json, runs.c.epistemic_summary_json, runs.c.error, runs.c.plan_json)
        if user_id:
            q = q.where(runs.c.user_id == user_id)
        rows = cx.execute(q.order_by(runs.c.created_at.desc()).limit(limit)).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at", "claimed_at"):
            d[k] = _dt_utc(d.get(k))
        out.append(d)
    return out


def update_run(run_id: str, **values):
    with engine().begin() as cx:
        cx.execute(runs.update().where(runs.c.run_id == run_id).values(**values))


def finish_run(run_id: str, expected_state="running", **values) -> bool:
    """ADR-0078 corrector — cierre OPTIMISTA de una corrida por su worker: UPDATE … WHERE run_id=? AND
    state=expected_state. Devuelve True si la fila se escribió; False si el estado ya no era el esperado
    (el reaper la segó, alguien la canceló…): el llamador NO pisa y deja un evento run.state.conflict.
    Un registro con dos veredictos terminales contradictorios era el hueco que update_run permitía."""
    with engine().begin() as cx:
        n = cx.execute(runs.update()
                       .where(runs.c.run_id == run_id, runs.c.state == expected_state)
                       .values(**values)).rowcount
    return n == 1


def request_cancel(run_id: str, by=None, reason=None) -> bool:
    """Flag a queued/running run for cancellation (checked between stages). A queued run cancels
    immediately; a running one cancels at its next stage boundary. LOTE-01·A3: the author and reason
    are part of the registry — a cancellation without them is a hole in the record."""
    with engine().begin() as cx:
        row = cx.execute(select(runs.c.state).where(runs.c.run_id == run_id)).first()
        if row is None or row._mapping["state"] not in ("queued", "running"):
            return False
        cx.execute(runs.update().where(runs.c.run_id == run_id)
                   .values(cancel_requested=True, cancelled_by=by, cancel_reason=reason))
        if row._mapping["state"] == "queued":
            cx.execute(runs.update().where(runs.c.run_id == run_id, runs.c.state == "queued")
                       .values(state="cancelled", finished_at=_now()))
    return True


def cancel_requested(run_id: str) -> bool:
    with engine().begin() as cx:
        row = cx.execute(select(runs.c.cancel_requested).where(runs.c.run_id == run_id)).first()
    return bool(row and row._mapping["cancel_requested"])


def runs_usage(frm=None, to=None):
    """All runs (no cap) with their usage for the M8 aggregation (LOTE-02·2) — the LIST serves max 50;
    a client-side total would be a figure without its full denominator, so the sum lives here."""
    with engine().begin() as cx:
        q = select(runs.c.run_id, runs.c.user_id, runs.c.question, runs.c.state,
                   runs.c.created_at, runs.c.usage_json)
        if frm is not None:
            q = q.where(runs.c.created_at >= frm)
        if to is not None:
            q = q.where(runs.c.created_at <= to)
        rows = cx.execute(q).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d["created_at"] = _dt_utc(d["created_at"])
        out.append(d)
    return out


def run_state_tally():
    """Conteo de corridas por estado (gratis — un GROUP BY). Insumo de la consulta abierta
    (ADR-0070): el inventario de corridas es un hecho de la BD, no un juicio."""
    with engine().begin() as cx:
        rows = cx.execute(select(runs.c.state, func.count()).group_by(runs.c.state)).all()
    return {r[0]: r[1] for r in rows}


def closed_runs(limit=1000):
    """CLOSED runs only — the precedent corpus (block 6, ADR-0053): a run becomes precedent ONLY after
    explicit closure (frozen_at stamped), never before."""
    with engine().begin() as cx:
        rows = cx.execute(select(runs.c.run_id, runs.c.question, runs.c.user_id, runs.c.frozen_at,
                                 runs.c.closed_by, runs.c.frozen_record_json)
                          .where(runs.c.state == "closed")
                          .order_by(runs.c.frozen_at.desc()).limit(limit)).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d["frozen_at"] = _dt_utc(d["frozen_at"])
        out.append(d)
    return out


def add_event(run_id: str, type: str, payload=None, agent=None, tool=None,
              level="info", degraded=None) -> int:
    """Append one event to THE run log (monotonic seq) and refresh the heartbeat. Returns seq."""
    import json as _json
    with engine().begin() as cx:
        seq = (cx.execute(select(func.max(run_events.c.seq))
                          .where(run_events.c.run_id == run_id)).scalar() or 0) + 1
        cx.execute(run_events.insert().values(
            run_id=run_id, seq=seq, ts=_now(), type=type, agent=agent, tool=tool, level=level,
            degraded=degraded,
            payload_json=_json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None))
        cx.execute(runs.update().where(runs.c.run_id == run_id).values(last_event_at=_now()))
    return seq


def events_after(run_id: str, after_seq: int = 0, limit: int = 500):
    """The ONE log both live SSE and replay read (same rows, same order)."""
    import json as _json
    with engine().begin() as cx:
        rows = cx.execute(select(run_events)
                          .where(run_events.c.run_id == run_id, run_events.c.seq > after_seq)
                          .order_by(run_events.c.seq).limit(limit)).all()
    out = []
    for r in rows:
        m = dict(r._mapping)
        m["ts"] = _dt_utc(m["ts"]).isoformat(timespec="seconds")
        m["payload"] = _json.loads(m.pop("payload_json")) if m.get("payload_json") else None
        out.append(m)
    return out


# --- ratings helpers (M5, ADR-0064) -------------------------------------------------------------------

def add_rating(run: dict, user: dict, rating_input, rating_input_state,
               rating_output, rating_output_state, note: str = "", note_question: str = "") -> dict:
    """Append ONE rating row (validated by the caller). Provenance is DERIVED here, never client-stated:
    is_author from the run's author, rater_profile from the session user's role at rating time,
    instrument from authorship (m5-cierre = the author's closure rating, m5-consenso = everyone else),
    saw_answer_before_rating from whether a frozen record exists (a failed run has no answer to see).
    Two attempts on the seq race (two simultaneous raters), same monotonic-seq pattern as run_events."""
    run_id = run["run_id"]
    is_author = run["user_id"] == user["user_id"]
    row = {
        "run_id": run_id, "rated_by": user["user_id"],
        "rater_profile": user["role"], "is_author": is_author,
        "blind": False,   # v1: the webapp shows the answer; the blind instrument is the CSV bank
        "saw_answer_before_rating": bool(run.get("frozen_record_json")),
        "instrument": "m5-cierre" if is_author else "m5-consenso",
        "rating_input": rating_input, "rating_input_state": rating_input_state,
        "rating_output": rating_output, "rating_output_state": rating_output_state,
        "note": note or "",                     # sobre la RESPUESTA
        "note_question": note_question or "",   # sobre la PREGUNTA (M5 v2, ADR-0075)
    }
    last_err = None
    for _attempt in (1, 2):
        try:
            with engine().begin() as cx:
                seq = (cx.execute(select(func.max(run_ratings.c.seq))
                                  .where(run_ratings.c.run_id == run_id)).scalar() or 0) + 1
                now = _now()
                cx.execute(run_ratings.insert().values(seq=seq, rated_at=now, **row))
            return {**row, "seq": seq, "rated_at": now.isoformat(timespec="seconds")}
        except Exception as e:   # PK race on seq — retry once with a fresh max
            last_err = e
    raise last_err


def ratings_for(run_id: str):
    """All rating rows for a run, chronological (append-only log — corrections are later rows)."""
    with engine().begin() as cx:
        rows = cx.execute(select(run_ratings).where(run_ratings.c.run_id == run_id)
                          .order_by(run_ratings.c.seq)).all()
    out = []
    for r in rows:
        m = dict(r._mapping)
        m["rated_at"] = _dt_utc(m["rated_at"]).isoformat(timespec="seconds")
        out.append(m)
    return out


def consensus_view(run_id: str, author_id: str):
    """The M5 consensus block (registro-congelado contract: {invited, received, open} + who is missing).
    invited = enabled accounts other than the author (the author rates at closure, not by invitation);
    received = DISTINCT non-author raters; open = received < invited. Values are NOT aggregated here —
    'nunca un promedio limpio' (M5): the UI shows individual values, this block only counts."""
    enabled = [u["user_id"] for u in list_users() if not u["disabled"]]
    invited = [u for u in enabled if u != author_id]
    with engine().begin() as cx:
        raters = sorted({r._mapping["rated_by"] for r in cx.execute(
            select(run_ratings.c.rated_by).where(run_ratings.c.run_id == run_id))})
    received = [u for u in raters if u != author_id]
    return {"invited": len(invited), "received": len(received),
            "open": len(received) < len(invited),
            "raters": raters, "missing": sorted(set(invited) - set(raters))}


def user_has_rated(run_id: str, user_id: str) -> bool:
    with engine().begin() as cx:
        row = cx.execute(select(run_ratings.c.seq)
                         .where(run_ratings.c.run_id == run_id,
                                run_ratings.c.rated_by == user_id).limit(1)).first()
    return row is not None


def runs_pending_rating(user_id: str, limit: int = 100):
    """The M5 'PENDIENTES DE CALIFICAR' queue: ratable runs (terminal or awaiting closure) where THIS
    user has no rating yet. Includes the user's OWN runs (an author who skipped the closure rating still
    owes one) — the UI may split by authorship."""
    with engine().begin() as cx:
        rated = select(run_ratings.c.run_id).where(run_ratings.c.rated_by == user_id)
        rows = cx.execute(select(runs.c.run_id, runs.c.user_id, runs.c.question, runs.c.state,
                                 runs.c.created_at, runs.c.frozen_at, runs.c.epistemic_summary_json)
                          .where(runs.c.state.in_(RATABLE_STATES), ~runs.c.run_id.in_(rated))
                          .order_by(runs.c.created_at.desc()).limit(limit)).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("created_at", "frozen_at"):
            d[k] = _dt_utc(d.get(k)).isoformat(timespec="seconds") if d.get(k) else None
        out.append(d)
    return out


# --- APUNTES (2026-09-04) -----------------------------------------------------------------------
# El cuaderno de teorías. Reglas de la casa que el store hace cumplir: escribir es SÓLO del autor
# (un apunte compartido se lee, no se edita), y los enlaces se guardan verbatim — resolverlos es
# trabajo de /resolve en el momento de leer, no del guardado.

NOTE_VISIBILITIES = ("private", "shared")


def _csv(valores) -> str:
    """Lista -> CSV normalizado: sin vacíos, sin duplicados, ORDEN DE ESCRITURA conservado (el
    orden en que el autor citó es información suya, no se alfabetiza)."""
    vistos, out = set(), []
    for v in valores or []:
        v = (v or "").strip()
        if v and v not in vistos:
            vistos.add(v)
            out.append(v)
    return ",".join(out)


def _note_view(row) -> dict:
    """Fila -> forma de API: los CSV se sirven como LISTAS (el cliente no parsea CSV) y las fechas
    en ISO. El cuerpo viaja completo: un apunte truncado en silencio sería una mentira."""
    d = dict(row._mapping)
    for k_csv, k_lista in (("run_ids_csv", "run_ids"), ("entities_csv", "entities"),
                           ("niches_csv", "niches")):
        crudo = d.pop(k_csv, "") or ""
        d[k_lista] = [x for x in crudo.split(",") if x]
    for k in ("created_at", "updated_at"):
        d[k] = _dt_utc(d[k]).isoformat(timespec="seconds") if d.get(k) else None
    return d


def create_note(note_id: str, author_id: str, title: str, body: str, visibility: str,
                run_ids=None, entities=None, niches=None) -> dict:
    ahora = _now()
    with engine().begin() as cx:
        cx.execute(notes.insert().values(
            note_id=note_id, author_id=author_id, title=title, body=body,
            visibility=visibility if visibility in NOTE_VISIBILITIES else "private",
            run_ids_csv=_csv(run_ids), entities_csv=_csv(entities), niches_csv=_csv(niches),
            created_at=ahora, updated_at=ahora))
    return get_note(note_id)


def get_note(note_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(notes).where(notes.c.note_id == note_id)).first()
    return _note_view(row) if row else None


def list_notes(reader_id: str, limit: int = 200):
    """Lo que ESTE lector puede ver: sus propios apuntes (de cualquier visibilidad) más los
    ajenos marcados 'shared'. Los privados de otra cuenta no salen ni en conteo."""
    with engine().begin() as cx:
        rows = cx.execute(
            select(notes)
            .where((notes.c.author_id == reader_id) | (notes.c.visibility == "shared"))
            .order_by(notes.c.updated_at.desc())
            .limit(limit)).all()
    return [_note_view(r) for r in rows]


def update_note(note_id: str, campos: dict) -> dict:
    """Actualiza SÓLO las llaves presentes (PATCH real: omitir un campo lo deja intacto; mandarlo
    vacío lo vacía — son cosas distintas y la puerta las distingue)."""
    valores = {}
    for k in ("title", "body", "visibility"):
        if k in campos:
            valores[k] = campos[k]
    for k, col in (("run_ids", "run_ids_csv"), ("entities", "entities_csv"),
                   ("niches", "niches_csv")):
        if k in campos:
            valores[col] = _csv(campos[k])
    if valores:
        valores["updated_at"] = _now()
        with engine().begin() as cx:
            cx.execute(notes.update().where(notes.c.note_id == note_id).values(**valores))
    return get_note(note_id)


def delete_note(note_id: str) -> bool:
    with engine().begin() as cx:
        n = cx.execute(delete(notes).where(notes.c.note_id == note_id)).rowcount
    return n == 1


def notes_citing_run(run_id: str, reader_id: str):
    """El hipervínculo AL REVÉS: qué apuntes visibles para este lector citan esta corrida. El
    filtro fino se hace en Python sobre la lista ya acotada por visibilidad — un LIKE sobre CSV
    daría falsos positivos (r-1 contra r-12) y esto no es una tabla de millones."""
    return [n for n in list_notes(reader_id) if run_id in n["run_ids"]]


# --- BORRADORES DE PREGUNTA (2026-09-04) ---------------------------------------------------------
# El lazo de calibración vive aquí: el borrador guarda la versión de spec que lo redactó y, al
# consumirse, el run_id. Con eso se puede preguntar "las preguntas que redactó la spec v1, ¿qué
# TAMAÑO les puso el humano?" — que es la depuración que el fundador pidió.

def _question_view(row) -> dict:
    d = dict(row._mapping)
    d["entities"] = [x for x in (d.pop("entities_csv", "") or "").split(",") if x]
    for k in ("draft_json", "usage_json"):
        crudo = d.pop(k, None)
        llave = k.removesuffix("_json")
        try:
            d[llave] = json.loads(crudo) if crudo else None
        except (ValueError, TypeError):
            # un blob ilegible se DECLARA, no se esconde ni se re-parsea a la fuerza
            d[llave] = None
            d[f"{llave}_unreadable"] = True
    d["created_at"] = _dt_utc(d["created_at"]).isoformat(timespec="seconds") if d.get("created_at") else None
    return d


# --- comentarios de corrida (ADR-0077) --------------------------------------------------------------

def _comments_select():
    """El nombre para mostrar sale de users (procedencia: la cuenta), jamás lo manda el cliente."""
    return (select(run_comments.c.comment_id, run_comments.c.run_id, run_comments.c.author_id,
                   users.c.display_name.label("author_name"), run_comments.c.body,
                   run_comments.c.created_at)
            .select_from(run_comments.join(users, users.c.user_id == run_comments.c.author_id)))


def _comment_view(row) -> dict:
    d = dict(row._mapping)
    d["created_at"] = (_dt_utc(d["created_at"]).isoformat(timespec="seconds")
                       if d.get("created_at") else None)
    return d


def create_run_comment(comment_id: str, run_id: str, author_id: str, body: str) -> dict:
    """Append-only: el cuerpo se guarda VERBATIM (saltos de línea incluidos) con autor y hora del
    servidor. No hay update ni delete: un comentario retirado sería un hueco en la conversación."""
    with engine().begin() as cx:
        cx.execute(run_comments.insert().values(comment_id=comment_id, run_id=run_id,
                                                author_id=author_id, body=body, created_at=_now()))
    return get_run_comment(comment_id)


def get_run_comment(comment_id: str):
    with engine().begin() as cx:
        row = cx.execute(_comments_select().where(run_comments.c.comment_id == comment_id)).first()
    return _comment_view(row) if row else None


def list_run_comments(run_id: str):
    """La conversación en orden de llegada (empate por id: determinista)."""
    with engine().begin() as cx:
        rows = cx.execute(_comments_select().where(run_comments.c.run_id == run_id)
                          .order_by(run_comments.c.created_at.asc(),
                                    run_comments.c.comment_id.asc())).all()
    return [_comment_view(r) for r in rows]


def count_run_comments(run_ids) -> dict:
    """{run_id: n} en UNA consulta agrupada — la lista de /runs no dispara N+1."""
    ids = [r for r in run_ids if r]
    if not ids:
        return {}
    with engine().begin() as cx:
        rows = cx.execute(select(run_comments.c.run_id, func.count())
                          .where(run_comments.c.run_id.in_(ids))
                          .group_by(run_comments.c.run_id)).all()
    return {r[0]: int(r[1]) for r in rows}


def create_note_question(question_id: str, note_id: str, author_id: str, spec_version: str,
                         model: str, state: str, question: str, entities, draft_json: str,
                         usage_json=None, error=None) -> dict:
    with engine().begin() as cx:
        cx.execute(note_questions.insert().values(
            question_id=question_id, note_id=note_id, author_id=author_id,
            spec_version=spec_version, model=model, state=state, question=question,
            entities_csv=_csv(entities), draft_json=draft_json, usage_json=usage_json,
            error=error, created_at=_now()))
    return get_note_question(question_id)


def get_note_question(question_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(note_questions)
                         .where(note_questions.c.question_id == question_id)).first()
    return _question_view(row) if row else None


def questions_of_note(note_id: str):
    """Todos los borradores de un apunte, el más nuevo primero: la historia de intentos es parte
    de la depuración — un borrador viejo no se borra al pedir otro."""
    with engine().begin() as cx:
        rows = cx.execute(select(note_questions)
                          .where(note_questions.c.note_id == note_id)
                          .order_by(note_questions.c.created_at.desc())).all()
    return [_question_view(r) for r in rows]


def mark_question_used(question_id: str, run_id: str) -> bool:
    """Un borrador se consume por UNA corrida (mismo sello que mark_plan_used). El sello no borra
    nada: deja la traza borrador->corrida, que es la que permite calibrar."""
    with engine().begin() as cx:
        n = cx.execute(note_questions.update()
                       .where(note_questions.c.question_id == question_id,
                              note_questions.c.run_id.is_(None))
                       .values(run_id=run_id)).rowcount
    return n == 1


def question_calibration():
    """El tablero de depuración del AGENTE, por versión de spec. Enfrenta lo que el agente AFIRMÓ
    (fits_one_run) con lo que el humano MIDIÓ (rating_input = el eje pregunta, re-anclado al
    TAMAÑO en ADR-0075). Todo son CONTEOS: promediar calificaciones ordinales sería inventar.

    Un borrador sin corrida, o con corrida sin calificar, no se cuenta como acierto ni como
    fallo — se declara pendiente. La ausencia jamás se rellena."""
    with engine().begin() as cx:
        rows = cx.execute(select(note_questions.c.question_id, note_questions.c.spec_version,
                                 note_questions.c.state, note_questions.c.draft_json,
                                 note_questions.c.run_id)).all()
        # la calificación del EJE PREGUNTA de cada corrida (la más reciente por corrida)
        califs = cx.execute(select(run_ratings.c.run_id, run_ratings.c.seq,
                                   run_ratings.c.rating_input,
                                   run_ratings.c.rating_input_state)
                            .order_by(run_ratings.c.run_id, run_ratings.c.seq)).all()
    ultima = {}
    for r in califs:
        ultima[r.run_id] = (r.rating_input, r.rating_input_state)

    por_version = {}
    for r in rows:
        v = por_version.setdefault(r.spec_version, {
            "spec_version": r.spec_version, "n_borradores": 0, "n_errored": 0,
            "n_usados": 0, "n_calificados": 0,
            "tamano": {str(k): 0 for k in range(1, 6)},   # conteos del eje pregunta, jamás promedio
            "no_calificable": 0,
            "agente_dijo_cabe": {"si": 0, "no": 0, "sin_juicio": 0},
            "cabe_vs_medido": {"acerto": 0, "fallo": 0, "pendiente": 0},
        })
        v["n_borradores"] += 1
        if r.state == "errored":
            v["n_errored"] += 1
        try:
            draft = json.loads(r.draft_json) if r.draft_json else {}
        except (ValueError, TypeError):
            draft = {}
        cabe = draft.get("fits_one_run")
        v["agente_dijo_cabe"]["si" if cabe is True else "no" if cabe is False else "sin_juicio"] += 1
        if not r.run_id:
            v["cabe_vs_medido"]["pendiente"] += 1
            continue
        v["n_usados"] += 1
        nota, estado = ultima.get(r.run_id, (None, None))
        if nota is None:
            v["cabe_vs_medido"]["pendiente"] += 1
            if estado == "cannot-rate":
                v["no_calificable"] += 1
            continue
        v["n_calificados"] += 1
        v["tamano"][str(nota)] = v["tamano"].get(str(nota), 0) + 1
        # 4-5 = cupo en una corrida; 1-3 = no cupo (3 = "hubiera salido mejor partida en dos").
        # El corte va DECLARADO en la salida: no es una verdad, es el corte que usamos.
        midio_cabe = nota >= 4
        if cabe is None:
            v["cabe_vs_medido"]["pendiente"] += 1
        else:
            v["cabe_vs_medido"]["acerto" if bool(cabe) == midio_cabe else "fallo"] += 1
    return {
        "por_version": sorted(por_version.values(), key=lambda x: x["spec_version"]),
        "eje": "rating_input (EJE PREGUNTA) — re-anclado al TAMAÑO en ADR-0075",
        "anclas": {"5": "cabía completa: una pregunta, una respuesta", "4": "cabía, apretada",
                   "3": "hubiera salido mejor partida en dos", "2": "pedía de más para una sola corrida",
                   "1": "pedía muchísimo de más"},
        "corte_declarado": "cupo = nota >= 4; el 3 cuenta como NO cupo (su ancla ya dice 'partida en dos')",
        "note": "conteos, jamás promedios: promediar una escala ordinal de 5 anclas inventa una medición",
    }
