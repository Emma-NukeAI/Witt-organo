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

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, MetaData, String, Table,
                        Text, UniqueConstraint, case, create_engine, delete, func, inspect as sa_inspect, or_, select)

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

# ADR-0079 (investigación = cadena de turnos sobre una raíz). db SÓLO persiste y consulta estas
# columnas; la DERIVACIÓN (thread_id, turn_no, turn_kind, origin, snapshot de contexto) es de runs.py
# al encolar — jamás del cliente. Los enums viven aquí porque la columna vive aquí.
TURN_KINDS = ("root", "refine", "rerun", "branch")
RUN_ORIGINS = ("production", "dev-offline", "replay", "smoke", "simulation", "fixture")
# Columnas que nacen con ADR-0079. Las filas anteriores quedan NULL en TODAS = "sin investigación" /
# origin NULL = 'unknown-pre-adr-0079': ausencia DECLARADA (ADR-0074: nada se backfillea en silencio).
THREAD_COLUMNS = ("parent_run_id", "thread_id", "turn_no", "turn_kind", "thread_context_json",
                  "origin", "root_question_id")

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
    # ADR-0079 — la investigación (T-<run_no raíz>): una corrida puede nacer DESDE otra terminada.
    Column("parent_run_id", String(64)),                      # la corrida de la que nace; NULL = raíz o pre-ADR
    Column("thread_id", String(64)),                          # run_id de la raíz; la raíz apunta a sí misma
    Column("turn_no", Integer),                               # 1 en la raíz; max(hilo)+1 en cada hijo
    Column("turn_kind", String(16)),                          # TURN_KINDS
    Column("thread_context_json", Text),                      # snapshot del padre que el modelo VIO (servidor)
    Column("origin", String(24)),                             # RUN_ORIGINS | 'invalid-env:<v>'; NULL = pre-ADR
    Column("root_question_id", String(64)),                   # apunte->pregunta raíz, conservada por investigación
    # ADR-0082 (F.4): la COPIA server-side del consejo al encolar — {plan_id, r1_state, r1: plans.council_json,
    # ledger: plans.council_ledger_json, membership_version, n_members, members[], full_council, catalog_sha,
    # membership_source, composed_at, source}. La compone app.create_run, la persiste runs.new_run (C5), JAMÁS el
    # cliente. NULL = corrida sin plan o anterior a 1.11 ('not-applicable (no-ledger)' en el frozen, declarado).
    Column("council_json", Text),
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
    # ADR-0082 (E.1) — la RONDA 1 del consejo es un JOB del plan (ni corrida ni tabla `jobs` genérica): el plan YA es
    # el objeto que el humano aprueba. Columnas ADITIVAS; las filas anteriores quedan NULL en todas y council_state
    # NULL se LEE 'pre-adr-0082' (COUNCIL_STATE_PRE_ADR) — ausencia declarada, jamás backfill (ADR-0074).
    Column("origin", String(24)),                             # runs.run_origin() al crear el plan (mismo derivador)
    Column("council_state", String(96)),                      # council.COUNCIL_STATES_EXACT | prefijos 'errored (' 'not-requested ('
                                                              # 96 y no 40 (ADR E.1): el literal E.3 'not-requested (origin <o>
                                                              # not in WITT_COUNCIL_ORIGINS)' mide 56-74 chars — declarado
    Column("council_json", Text),                             # r1: rounds[0] + agregación + requisitos SIN decisiones
    Column("council_ledger_json", Text),                      # decisiones humanas + knowledge_now (F.1) — íntegro
    Column("council_usage_json", Text),                       # gasto MEDIDO de r1 (se escribe tras CADA miembro recogido)
    Column("council_claimed_by", String(64)),                 # boot:pid:hilo del council-worker que reclamó
    Column("council_claimed_at", DateTime(timezone=True)),
    Column("council_started_at", DateTime(timezone=True)),
    Column("council_finished_at", DateTime(timezone=True)),
    Column("council_last_event_at", DateTime(timezone=True)), # latido del job (plan_add_event lo refresca)
    Column("council_approved_by", String(64)),                # quién aprobó el ledger (o lo saltó)
    Column("council_approved_at", DateTime(timezone=True)),
    Column("council_error", Text),                            # 'errored (<kind>)': el porqué, sin secretos
)

# ADR-0082 (E.1): la traza de la RONDA 1 del plan — espejo de run_events (mismas columnas, misma lectura) con FK a
# plans y SIN FK a runs (Context 5: reutilizar run_events exigiría una corrida que no existe). Nace por create_all
# (tabla nueva, esquema completo desde el día uno; _migrate no la toca). PK (plan_id, seq): seq monotónico por plan,
# asignado en la MISMA transacción del INSERT (plan_add_event) — un solo escritor lógico (el hilo orquestador del
# worker) por plan; plan_events.seq y run_events.seq no se mezclan jamás (M).
plan_events = Table(
    "plan_events", metadata,
    Column("plan_id", String(64), ForeignKey("plans.plan_id"), primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("type", String(64), nullable=False),               # council.state | stage.council.* | council.ledger | council.skip
    Column("agent", String(64)),
    Column("tool", String(64)),
    Column("level", String(16), nullable=False, default="info"),
    Column("degraded", String(64)),                           # espejo exacto de run_events (misma forma de fila)
    Column("payload_json", Text),
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

# BITÁCORA DE CONFIGURACIÓN (ADR-0081 (I)): la clase MEDICIÓN de /config-history. Cada fila es UN campo
# del snapshot efectivo (models.snapshot(), lista cerrada SNAPSHOT_FIELDS) que CAMBIÓ respecto a la última
# fila de ese campo — la escribe app.config_ledger_boot() al arrancar (changed_by 'system:boot-diff') y
# config_ledger_observe() al inicio de cada execute_run (changed_by 'system:runtime-diff', p. ej. el
# auto-retiro de un asiento). Append-only: aquí NO existe update ni delete (nada reescribe la historia).
# `value`/`previous_value` van como JSON (json.dumps): 'null' = valor None DECLARADO; SQL NULL en
# previous_value = "primera observación de este campo" — tres estados, jamás confundibles. Ningún valor
# que parezca llave entra (CONFIG_LEDGER_SECRET_MARKERS): se rechaza y se DECLARA en rejected[].
# create_all la crea; sin ALTER (_migrate no la toca): tabla nueva, esquema completo desde el día uno.
config_history = Table(
    "config_history", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("recorded_at", DateTime(timezone=True), nullable=False),   # medido al escribir (UTC)
    Column("field", String(64), nullable=False),                      # ∈ models.SNAPSHOT_FIELDS
    Column("value", Text, nullable=False),                            # JSON del valor efectivo
    Column("previous_value", Text),                                   # JSON del anterior; NULL = 1a vez
    Column("source", Text, nullable=False),                           # 'env:<VAR>' | 'default:<gen>' | …
    Column("changed_by", String(64), nullable=False),                 # 'system:boot-diff' | 'system:runtime-diff'
    Column("scope", String(24), nullable=False),                      # ámbito declarado por el llamador
    Column("generation", String(32), nullable=False),                 # models.GENERATION efectiva
    Column("boot_id", String(32), nullable=False),                    # identidad del arranque (proceso)
    Column("note", Text),                                             # 'first-boot-snapshot' | NULL
    Index("ix_config_history_field_recorded", "field", "recorded_at"),
)

# --- ADR-0084 (H): la CUOTA MENSUAL del localizador web — UNA fila por (mes UTC 'YYYY-MM', proveedor) ---------------------
# Contador LOCAL de consultas ENVIADAS por este despliegue (web_locator.QUOTA_RULE): la reserva es UN `UPDATE … SET n_queries =
# n_queries + 1 WHERE month=:m AND provider=:p AND n_queries < :cap` (rowcount 1 = granted; 0 = tope alcanzado) — atómico en
# SQLite y en Postgres, sin carrera entre hilos (`--workers 1` con hilos) ni entre procesos; el registro posterior (n_results,
# cost_usd_projected) suma sobre la MISMA fila. Nace por create_all (patrón config_history): sin ALTER, sin backfill; _migrate no
# la toca. Las sondas CLI (LG1/LG3/LG5) no pasan por aquí; la verdad del saldo es el dashboard del proveedor.
web_locator_usage = Table(
    "web_locator_usage", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("month", String(7), nullable=False),                       # 'YYYY-MM' (mes calendario UTC)
    Column("provider", String(16), nullable=False),                   # 'brave' | 'anthropic'
    Column("n_queries", Integer, nullable=False, default=0),          # consultas RESERVADAS (enviadas o a punto de enviarse)
    Column("n_results", Integer, nullable=False, default=0),          # URLs devueltas (record= tras la llamada)
    Column("cost_usd_projected", Float, nullable=False, default=0.0),  # PROYECCIÓN (consultas facturables × tarifa)
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("month", "provider", name="uq_web_locator_usage_month_provider"),
)
WEB_LOCATOR_USAGE_TABLE = "web_locator_usage"
WEB_LOCATOR_USAGE_FIELDS = ("month", "provider", "n_queries", "n_results", "cost_usd_projected", "updated_at")

# ADR-0086 (F): las IMÁGENES ATESTIGUADAS que aporta una persona. La fila guarda IDENTIDAD y PROCEDENCIA; los BYTES viven
# fuera (almacenamiento privado, attestations.Storage) y aquí sólo viaja su llave. Nace por create_all: CERO ALTER sobre
# tablas existentes (una migración aditiva que un Postgres viejo tolera). Retirar NO borra la fila: pone la lápida
# (withdrawn_at/by/reason) y borra los bytes — el registro es inmutable, los píxeles no.
plan_attested_images = Table(
    "plan_attested_images", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("image_id", String(80), nullable=False),                  # attested:<sha corto> (identidad legible)
    Column("plan_id", String(64), nullable=False),
    Column("sha256", String(64), nullable=False),                    # de los bytes ALMACENADOS (post-strip): lo que se sirve
    Column("sha256_received", String(64), nullable=True),            # del archivo que subió la persona (para que lo coteje)
    Column("bytes", Integer, nullable=False, default=0),
    Column("bytes_received", Integer, nullable=True),
    Column("media_type", String(32), nullable=False),                # MEDIDO por magic bytes
    Column("media_type_declared", String(64), nullable=True),        # lo que dijo el cliente: se registra, no decide
    Column("dims_w", Integer, nullable=True),
    Column("dims_h", Integer, nullable=True),
    Column("caption", Text, nullable=False),                         # ATESTIGUADO: lo que la persona dice de su imagen
    Column("caption_chars", Integer, nullable=True),
    Column("consent_kind", String(32), nullable=False),
    Column("consent_declared", Boolean, nullable=False, default=False),
    Column("consent_text", Text, nullable=True),
    Column("third_party_ack", Boolean, nullable=False, default=False),
    Column("patient_material", Boolean, nullable=False, default=False),
    Column("deidentified_declared", Boolean, nullable=False, default=False),
    Column("license_declared", String(32), nullable=False),
    Column("share_scope", String(16), nullable=False),               # author-only | team (la persona lo declara al subir)
    Column("requirement_id", String(64), nullable=True),             # el requisito del consejo al que se adjuntó
    Column("date_taken", String(32), nullable=True),
    Column("method", Text, nullable=True),
    Column("exif_state", String(64), nullable=True),                 # stripped (…) | none-found | declared-not-stripped
    Column("exif_removed_json", Text, nullable=True),
    Column("storage_backend", String(16), nullable=False),           # local | minio (el de CUANDO se guardó)
    Column("storage_key", String(255), nullable=False),
    Column("storage_state", String(48), nullable=False),
    Column("uploaded_by", String(64), nullable=False),
    Column("uploaded_by_role", String(32), nullable=True),
    Column("uploaded_at", DateTime(timezone=True), nullable=False),
    Column("ledger_state", String(24), nullable=False, default="staged"),   # staged | attached | inherited
    Column("attached_to", String(32), nullable=True),                # knowledge_now | requirement | null (aún no adjuntada)
    Column("attached_at", DateTime(timezone=True), nullable=True),
    Column("attached_by", String(64), nullable=True),
    Column("inherited_from_plan_id", String(64), nullable=True),
    Column("inherited_from_run_id", String(64), nullable=True),
    Column("withdrawn_at", DateTime(timezone=True), nullable=True),  # LÁPIDA: la identidad se queda, los bytes se van
    Column("withdrawn_by", String(64), nullable=True),
    Column("withdraw_reason", Text, nullable=True),
    Column("withdraw_cascade_n", Integer, nullable=True),
    UniqueConstraint("plan_id", "sha256", name="uq_attested_plan_sha"),
)
Index("ix_attested_plan", plan_attested_images.c.plan_id)
Index("ix_attested_uploader", plan_attested_images.c.uploaded_by, plan_attested_images.c.uploaded_at)
ATTESTED_IMAGES_TABLE = "plan_attested_images"


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
                 f"ALTER TABLE runs ADD COLUMN claimed_at {_dt_type}",
                 # ADR-0079: la investigación. Aditivas, SIN backfill: una corrida anterior queda NULL en
                 # todas = "sin investigación" (ausencia declarada, no se le inventa raíz ni origen).
                 "ALTER TABLE runs ADD COLUMN parent_run_id VARCHAR(64)",
                 "ALTER TABLE runs ADD COLUMN thread_id VARCHAR(64)",
                 "ALTER TABLE runs ADD COLUMN turn_no INTEGER",
                 "ALTER TABLE runs ADD COLUMN turn_kind VARCHAR(16)",
                 "ALTER TABLE runs ADD COLUMN thread_context_json TEXT",
                 "ALTER TABLE runs ADD COLUMN origin VARCHAR(24)",
                 "ALTER TABLE runs ADD COLUMN root_question_id VARCHAR(64)",
                 # ADR-0082 (E.1): columnas aditivas del consejo en plans y runs — la lista vive en
                 # council_migration_statements() para que el smoke la compile con el dialecto postgresql.
                 *council_migration_statements(engine().dialect)):
        try:
            with engine().begin() as cx:
                cx.execute(text(stmt))
        except Exception:
            pass  # column already there
    # ADR-0082 (E.1): el índice del reclamo FIFO y de las consultas por estado (claim_next_council_plan,
    # count_plans_council, plans_council_pending, reap_stale_council_plans). IF NOT EXISTS = idempotente.
    for stmt in ("CREATE INDEX IF NOT EXISTS ix_plans_council_state ON plans (council_state, created_at)",):
        try:
            with engine().begin() as cx:
                cx.execute(text(stmt))
        except Exception as e:
            import sys as _sys
            print(f"[db._migrate] ADR-0082 índice no aplicó: {e!r}", file=_sys.stderr)
    # ADR-0079: índices de consulta de la investigación (hijos de una corrida, turnos de un hilo). No
    # únicos: un padre tiene N hijos (branch) y un hilo N turnos. IF NOT EXISTS = idempotente.
    # Corrector ADR-0079: índice ÚNICO (thread_id, turn_no) — el mismo patrón que ix_runs_run_no: dos hijos
    # encolados a la vez que leyeran el mismo máximo del hilo compartirían turn_no (y el cursor `after` =
    # turn_no exclusivo perdería uno de los dos); el índice rechaza al segundo y runs.new_run re-deriva.
    # Las filas pre-ADR (NULL, NULL) no chocan: NULL es distinto de NULL en SQLite y Postgres.
    for stmt in ("CREATE INDEX IF NOT EXISTS ix_runs_thread_id ON runs (thread_id)",
                 "CREATE INDEX IF NOT EXISTS ix_runs_parent_run_id ON runs (parent_run_id)",
                 "CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_thread_turn ON runs (thread_id, turn_no)"):
        try:
            with engine().begin() as cx:
                cx.execute(text(stmt))
        except Exception as e:
            import sys as _sys
            print(f"[db._migrate] ADR-0079 índice no aplicó: {e!r}", file=_sys.stderr)
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


# ADR-0082 (E.1): las columnas del consejo por tabla (nombre → tipo SQL; 'dt' se compila por dialecto). Una sola lista
# alimenta el ALTER de _migrate, el chequeo de esquema (council_schema_state) y el smoke (SQL compilado para postgresql).
PLAN_COUNCIL_COLUMNS = ("origin", "council_state", "council_json", "council_ledger_json", "council_usage_json",
                        "council_claimed_by", "council_claimed_at", "council_started_at", "council_finished_at",
                        "council_last_event_at", "council_approved_by", "council_approved_at", "council_error")
_PLAN_COUNCIL_TYPES = {"origin": "VARCHAR(24)", "council_state": "VARCHAR(96)", "council_json": "TEXT",
                       "council_ledger_json": "TEXT", "council_usage_json": "TEXT", "council_claimed_by": "VARCHAR(64)",
                       "council_claimed_at": "dt", "council_started_at": "dt", "council_finished_at": "dt",
                       "council_last_event_at": "dt", "council_approved_by": "VARCHAR(64)", "council_approved_at": "dt",
                       "council_error": "TEXT"}
RUN_COUNCIL_COLUMNS = ("council_json",)
COUNCIL_STATE_MAXLEN = 96      # == String(96) de plans.council_state (el literal más largo del ADR E.3 mide 74)
PLAN_COUNCIL_DT_COLUMNS = tuple(c for c, t in _PLAN_COUNCIL_TYPES.items() if t == "dt")


def council_migration_statements(dialect=None):
    """ADR-0082 (E.1): las sentencias `ALTER TABLE … ADD COLUMN` del consejo (plans + runs), con el tipo FECHA compilado
    para el DIALECTO dado (lección ADR-0078: un literal DATETIME fallaría en Postgres, el except lo callaría y la columna
    no existiría). `dialect=None` → el del engine. Sin funciones exclusivas de SQLite: el smoke las compila con
    postgresql.dialect() y mide 'TIMESTAMP WITH TIME ZONE'."""
    dialect = dialect or engine().dialect
    dt = DateTime(timezone=True).compile(dialect=dialect)
    out = [f"ALTER TABLE runs ADD COLUMN {c} TEXT" for c in RUN_COUNCIL_COLUMNS]
    for col in PLAN_COUNCIL_COLUMNS:
        t = _PLAN_COUNCIL_TYPES[col]
        out.append(f"ALTER TABLE plans ADD COLUMN {col} {dt if t == 'dt' else t}")
    return out


# corrector ADR-0082 (E.1/LG8): caché por tabla de "la superficie E.1 está completa" — una vez lista, create_plan/create_run
# no vuelven a inspeccionar el esquema (un smoke que simula la BD sin migrar la resetea explícitamente)
_COUNCIL_SCHEMA_READY = {"plans": False, "runs": False}


def _missing_council_columns(table):
    """Columnas E.1 AUSENTES en `table` ('plans' | 'runs') según council_schema_state(); set() cuando la superficie está
    completa (cacheado). En una BD sin migrar el INSERT las omite en vez de fallar con 500 — el estado del consejo se sirve
    'not-requested (council db unavailable)' (council_state_of → None), que antes era inalcanzable (corrector ADR-0082)."""
    if _COUNCIL_SCHEMA_READY.get(table):
        return set()
    st = council_schema_state()
    miss = set(st.get("plans_missing" if table == "plans" else "runs_missing") or [])
    if not miss and "error" not in st:
        _COUNCIL_SCHEMA_READY[table] = True
    return miss


def council_schema_state():
    """¿La BD conectada tiene la superficie E.1? {plans_missing[], runs_missing[], plan_events_table: bool, ready: bool}
    — insumo de un 503 'council-db-unavailable' honesto (app) y del smoke (_migrate idempotente ×2)."""
    insp = sa_inspect(engine())
    try:
        pcols = {c["name"] for c in insp.get_columns("plans")}
        rcols = {c["name"] for c in insp.get_columns("runs")}
        has_pe = bool(insp.has_table("plan_events"))
    except Exception as e:
        return {"plans_missing": list(PLAN_COUNCIL_COLUMNS), "runs_missing": list(RUN_COUNCIL_COLUMNS),
                "plan_events_table": False, "ready": False, "error": f"{type(e).__name__}: {e}"}
    pm = [c for c in PLAN_COUNCIL_COLUMNS if c not in pcols]
    rm = [c for c in RUN_COUNCIL_COLUMNS if c not in rcols]
    return {"plans_missing": pm, "runs_missing": rm, "plan_events_table": has_pe,
            "ready": not pm and not rm and has_pe}


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


def create_run(run_id: str, user_id: str, question: str, entities=None, plan_json=None,
               parent_run_id=None, thread_id=None, turn_no=None, turn_kind=None,
               thread_context_json=None, origin=None, root_question_id=None, council_json=None):
    """ADR-0076: el NÚMERO de corrida se asigna AQUÍ, al nacer — MAX(run_no)+1 dentro de la misma
    transacción del INSERT. Si dos corridas se encolan a la vez y leen el mismo máximo (Postgres en
    READ COMMITTED lo permite), el índice único ix_runs_run_no rechaza a la segunda y ésta reintenta
    con el número siguiente. Sin fallback a null: una corrida sin número sería la ambigüedad que el
    número elimina. Devuelve el número asignado.

    ADR-0079: los campos de la investigación (THREAD_COLUMNS) se PERSISTEN tal como los deriva el
    llamador (runs.py, servidor) — db no deriva thread_id ni turn_kind. Default None en todos para no
    romper a los llamadores actuales; un None aquí queda NULL = ausencia declarada, así que el llamador
    que encola una RAÍZ debe pasar explícitamente thread_id=run_id, turn_no=1, turn_kind='root' y su
    origin. Lo único que db valida es el enum de turn_kind (una fila con un tipo fuera de TURN_KINDS
    sería un hueco en el registro).

    ADR-0082 (F.4): `council_json` es la COPIA server-side del consejo del plan (str JSON compuesto por app.create_run),
    persistida tal cual al nacer; None = corrida sin plan/consejo (NULL declarado)."""
    from sqlalchemy.exc import IntegrityError
    if turn_kind is not None and turn_kind not in TURN_KINDS:
        raise ValueError(f"turn_kind {turn_kind!r} not in {TURN_KINDS} (ADR-0079)")
    ultimo_error = None
    for _intento in range(5):
        try:
            values = dict(run_id=run_id, user_id=user_id, question=question,
                          entities_csv=",".join(entities or []), state="queued",
                          created_at=_now(), cancel_requested=False, plan_json=plan_json,
                          parent_run_id=parent_run_id, thread_id=thread_id, turn_no=turn_no, turn_kind=turn_kind,
                          thread_context_json=thread_context_json, origin=origin, root_question_id=root_question_id,
                          council_json=council_json)
            for col in _missing_council_columns("runs"):   # corrector ADR-0082 (E.1): BD sin migrar → columna omitida
                values.pop(col, None)
            with engine().begin() as cx:
                siguiente = (cx.execute(select(func.max(runs.c.run_no))).scalar() or 0) + 1
                cx.execute(runs.insert().values(run_no=siguiente, **values))
            return siguiente
        except IntegrityError as e:
            # sólo se reintenta la CARRERA del número; un run_id repetido es otro defecto y sube tal cual
            if "run_no" not in str(e.orig).lower():
                raise
            ultimo_error = e
    raise ultimo_error


def create_plan(plan_id: str, user_id: str, question: str, entities, plan_json: str,
                origin=None, council_state=None):
    """ADR-0082 (E.1/E.3): `origin` (runs.run_origin()['value'], el MISMO derivador de la corrida) y `council_state`
    inicial ('queued' encola la ronda 1; 'not-requested (…)' / 'disabled (kill-switch WITT_COUNCIL=0)' la declaran) los
    decide app.create_plan — db sólo persiste. Sin ellos (llamadores viejos) quedan NULL: origin desconocido y
    council_state NULL = 'pre-adr-0082' al leer (declarado)."""
    if council_state is not None and len(council_state) > COUNCIL_STATE_MAXLEN:
        raise ValueError(f"council_state excede {COUNCIL_STATE_MAXLEN} caracteres (Postgres lo rechazaría): {council_state!r}")
    values = dict(plan_id=plan_id, user_id=user_id, question=question, entities_csv=",".join(entities or []),
                  plan_json=plan_json, created_at=_now(), origin=origin, council_state=council_state)
    for col in _missing_council_columns("plans"):      # corrector ADR-0082 (E.1): BD sin migrar → columnas omitidas, no 500
        values.pop(col, None)
    with engine().begin() as cx:
        cx.execute(plans.insert().values(**values))


_PLAN_DT_KEYS = ("created_at",) + PLAN_COUNCIL_DT_COLUMNS


def _plan_row(row) -> dict:
    """Fila de plans → dict con TODAS las columnas (las del consejo incluidas, NULL = None) y las fechas normalizadas a
    UTC (SQLite pierde tzinfo). council_state se sirve CRUDO: NULL sigue siendo None — la lectura 'pre-adr-0082' la hace
    council_state_of() / el consumidor (tres estados: columna ausente ≠ NULL ≠ valor)."""
    d = dict(row._mapping)
    for k in _PLAN_DT_KEYS:
        if k in d:
            d[k] = _dt_utc(d.get(k))
    return d


def get_plan(plan_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(plans).where(plans.c.plan_id == plan_id)).first()
    return _plan_row(row) if row else None


def mark_plan_used(plan_id: str, run_id: str):
    """Un plan se consume por UNA corrida: re-usarlo silencioso haría pasar un juicio viejo como
    fresco. El sello no borra nada — deja la traza plan->corrida."""
    with engine().begin() as cx:
        n = cx.execute(plans.update()
                       .where(plans.c.plan_id == plan_id, plans.c.run_id.is_(None))
                       .values(run_id=run_id)).rowcount
    return n == 1


# --- consejo de criterio (ADR-0082 E.1): la RONDA 1 es un JOB del PLAN -----------------------------------------
# db SÓLO persiste y consulta: quién reclama (council_jobs.worker_loop), qué se escribe tras cada miembro
# (council_jobs.execute_round1) y qué decide el humano (app: ledger/skip) viven fuera. Vocabulario de estados: el de
# lib.council (COUNCIL_STATES_EXACT + prefijos 'errored (' / 'not-requested ('); aquí sólo los literales que db escribe.

COUNCIL_STATE_PRE_ADR = "pre-adr-0082"           # lectura de council_state NULL (plan anterior al ADR; jamás backfill)
COUNCIL_PENDING_STATES = ("queued", "running")   # la ronda 1 está viva: dedup (E.3), 409 council_round1_pending (F.3)
COUNCIL_REAP_REASONS = ("worker-lost", "worker-lost-restart")   # == REAP_REASONS (definida más abajo): los mismos
                                                                # dos motivos que el reaper de corridas (ADR-0078)
COUNCIL_REAP_STATE = {r: f"errored ({r})" for r in COUNCIL_REAP_REASONS}


def council_state_of(row):
    """Los TRES estados de plans.council_state (ADR-0043): columna AUSENTE del dict (BD sin migrar) → None (el llamador
    lo declara 'not-requested (council db unavailable)'); NULL → 'pre-adr-0082'; valor → tal cual."""
    if row is None or "council_state" not in row:
        return None
    return row.get("council_state") or COUNCIL_STATE_PRE_ADR


def _check_council_state(value):
    if value is not None and (not isinstance(value, str) or not value or len(value) > COUNCIL_STATE_MAXLEN):
        raise ValueError(f"council_state inválido o > {COUNCIL_STATE_MAXLEN} chars (Postgres lo rechazaría): {value!r}")


def update_plan_council(plan_id: str, expected_state=None, **values) -> bool:
    """UPDATE parcial de las columnas del consejo de UN plan (sólo PLAN_COUNCIL_COLUMNS; una llave ajena → ValueError:
    plan_json/run_id/user_id no se tocan por aquí). Devuelve True si la fila se escribió. Es la escritura INCREMENTAL del
    worker (council_json/council_usage_json tras cada miembro, council_state al cerrar) y la del skip (app).
    `expected_state` (corrector ADR-0082 E.2, patrón db.finish_run de ADR-0078): el UPDATE exige además
    `council_state == expected_state` — cierre CONDICIONAL del job; rowcount 0 = el reaper ya sentenció (o el humano saltó)
    mientras el worker seguía vivo y el llamador NO pisa el veredicto terminal."""
    extra = sorted(set(values) - set(PLAN_COUNCIL_COLUMNS))
    if extra:
        raise ValueError(f"update_plan_council: columnas fuera de PLAN_COUNCIL_COLUMNS: {extra}")
    if not values:
        return get_plan(plan_id) is not None
    _check_council_state(values.get("council_state"))
    where = [plans.c.plan_id == plan_id]
    if expected_state is not None:
        where.append(plans.c.council_state == expected_state)
    with engine().begin() as cx:
        n = cx.execute(plans.update().where(*where).values(**values)).rowcount
    return n == 1


def _claim_council_query(origins=None, plan_id=None):
    """El SELECT del reclamo (expuesto para compilarlo con postgresql en el smoke): el plan 'queued' más viejo (FIFO por
    created_at, empate por plan_id) cuyo origin ∈ origins (None = sin filtro, 'all' declarado por el llamador);
    `plan_id` acota el reclamo a ESE plan (si sigue 'queued'). ADR-0082 (C9, hueco de C6): `run_id IS NULL` — un plan
    'queued' que ya respalda una corrida (bajo WITT_COUNCIL=0 la puerta deja correr sin aprobar, L.2) NO se reclama al
    reencender el consejo: sus 17 llamadas serían gasto huérfano sobre un ledger que ya nadie puede aprobar."""
    q = select(plans).where(plans.c.council_state == "queued", plans.c.run_id.is_(None))
    if origins is not None:
        q = q.where(plans.c.origin.in_(list(origins)))
    if plan_id is not None:
        q = q.where(plans.c.plan_id == plan_id)
    return q.order_by(plans.c.created_at.asc(), plans.c.plan_id.asc()).limit(1)


def claim_next_council_plan(worker_id, origins=None, plan_id=None):
    """ADR-0082 (E.2): reclamo OPTIMISTA del job de ronda 1 más viejo — `UPDATE plans SET council_state='running',
    council_claimed_by, council_claimed_at, council_started_at, council_last_event_at WHERE plan_id=? AND
    council_state='queued'`; rowcount 0 = otro worker ganó la carrera → None (el llamador vuelve a sondear). FIFO por
    created_at. `origins` = WITT_COUNCIL_ORIGINS (lista) o None = sin filtro: un plan 'queued' de un origen que este
    proceso NO atiende se queda 'queued' (Context 9: un job que reclamara CUALQUIER plan dispararía 17 llamadas por
    fixture). `worker_id` = boot:pid:hilo (procedencia del reclamo; None = 'nadie declaró quién', servido así). El
    latido arranca en el reclamo (council_last_event_at) para que el reaper mida desde aquí. `plan_id` reclama ESE plan
    si sigue 'queued' (operador / smokes), con la misma compuerta optimista. Devuelve la fila con los valores ESCRITOS,
    o None."""
    with engine().begin() as cx:
        row = cx.execute(_claim_council_query(origins, plan_id)).first()
        if row is None:
            return None
        ahora = _now()
        n = cx.execute(plans.update()
                       .where(plans.c.plan_id == row._mapping["plan_id"], plans.c.council_state == "queued",
                              plans.c.run_id.is_(None))
                       .values(council_state="running", council_claimed_by=worker_id, council_claimed_at=ahora,
                               council_started_at=ahora, council_last_event_at=ahora)).rowcount
        if n != 1:   # otro worker ganó entre el SELECT y el UPDATE
            return None
        d = _plan_row(row)
        d.update(council_state="running", council_claimed_by=worker_id, council_claimed_at=ahora,
                 council_started_at=ahora, council_last_event_at=ahora)
        return d


def plan_add_event(plan_id: str, type: str, payload=None, agent=None, tool=None, level="info", degraded=None) -> int:
    """Appendea UN evento a la traza del PLAN (plan_events; seq monotónico por plan, asignado en la MISMA transacción
    del INSERT) y refresca el latido plans.council_last_event_at — el espejo de add_event. Un solo escritor lógico por
    plan (el hilo orquestador del worker: council.run_round emite desde ahí; Context 6 / R16). Devuelve seq."""
    import json as _json
    with engine().begin() as cx:
        seq = (cx.execute(select(func.max(plan_events.c.seq))
                          .where(plan_events.c.plan_id == plan_id)).scalar() or 0) + 1
        ahora = _now()
        cx.execute(plan_events.insert().values(
            plan_id=plan_id, seq=seq, ts=ahora, type=type, agent=agent, tool=tool, level=level, degraded=degraded,
            payload_json=_json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None))
        cx.execute(plans.update().where(plans.c.plan_id == plan_id).values(council_last_event_at=ahora))
    return seq


def plan_events_after(plan_id: str, after_seq: int = 0, limit: int = 500):
    """El ÚNICO log que leen el SSE /plans/{id}/stream y el replay /plans/{id}/events — misma forma de fila que
    events_after: {plan_id, seq, ts (ISO), type, agent, tool, level, degraded, payload (dict|None)}."""
    import json as _json
    with engine().begin() as cx:
        rows = cx.execute(select(plan_events)
                          .where(plan_events.c.plan_id == plan_id, plan_events.c.seq > int(after_seq))
                          .order_by(plan_events.c.seq).limit(int(limit))).all()
    out = []
    for r in rows:
        m = dict(r._mapping)
        m["ts"] = _dt_utc(m["ts"]).isoformat(timespec="seconds")
        m["payload"] = _json.loads(m.pop("payload_json")) if m.get("payload_json") else None
        out.append(m)
    return out


def plan_events_count(plan_id: str) -> int:
    with engine().begin() as cx:
        v = cx.execute(select(func.count()).select_from(plan_events)
                       .where(plan_events.c.plan_id == plan_id)).scalar()
    return int(v or 0)


def _council_running_rows():
    """Las filas 'running' con sus fechas de referencia (el SELECT del reaper; separado para que el smoke simule la
    carrera reaper ↔ worker vivo devolviendo un latido ya viejo)."""
    with engine().begin() as cx:
        return [dict(r._mapping) for r in cx.execute(
            select(plans.c.plan_id, plans.c.council_last_event_at, plans.c.council_started_at,
                   plans.c.council_claimed_at, plans.c.created_at, plans.c.council_claimed_by)
            .where(plans.c.council_state == "running")).all()]


def reap_stale_council_plans(stale_s, now=None, reason="worker-lost", stale_s_source=None):
    """ADR-0082 (E.2) — el segador de jobs de ronda 1 huérfanos, mismo patrón que reap_stale_running (ADR-0078): un plan
    'running' cuyo último latido (council_last_event_at; si null, council_started_at; si null, council_claimed_at; si
    null, created_at) es más viejo que `stale_s` segundos perdió a su worker → council_state 'errored (worker-lost)' |
    'errored (worker-lost-restart)' (COUNCIL_REAP_STATE), council_finished_at, council_error, y UN evento council.state
    {state, plan_id, reason, stale_s, stale_s_source, idle_s, ref_field, claimed_by, error} en plan_events (agent
    'council-reaper', level 'error'). La carrera resuelta: el UPDATE exige `council_state='running' AND <ref_field> =
    <valor leído>` — si el worker latió entre el SELECT y el UPDATE, rowcount 0 y no se toca. JAMÁS re-encola (nada se
    re-ejecuta solo); council_json / council_usage_json quedan como estén (lo que los miembros que respondieron gastaron
    SOBREVIVE: persistencia incremental). `now` inyectable. Devuelve los plan_id segados."""
    if reason not in COUNCIL_REAP_REASONS:
        raise ValueError(f"reap reason {reason!r} not in {COUNCIL_REAP_REASONS}")
    ahora = now or _now()
    stale_s = float(stale_s)
    segados = []
    for m in _council_running_rows():
        ref_field = next((k for k in ("council_last_event_at", "council_started_at", "council_claimed_at",
                                      "created_at") if m.get(k) is not None), None)
        if ref_field is None:   # sin ninguna fecha no se puede medir la edad — no se toca
            continue
        idle_s = (ahora - _dt_utc(m[ref_field])).total_seconds()
        if idle_s <= stale_s:
            continue
        if reason == "worker-lost-restart":
            error = "worker-lost: proceso reiniciado, el job de ronda 1 'running' no tiene worker (ADR-0082 E.2)"
        else:
            error = f"worker-lost: sin latido por >{int(stale_s)} s (ADR-0082 E.2)"
        with engine().begin() as cx:
            n = cx.execute(plans.update()
                           .where(plans.c.plan_id == m["plan_id"], plans.c.council_state == "running",
                                  getattr(plans.c, ref_field) == m[ref_field])
                           .values(council_state=COUNCIL_REAP_STATE[reason], council_finished_at=ahora,
                                   council_error=error)).rowcount
        if n != 1:   # el worker sí vivía (latió o cerró el job en medio): no se pisa
            continue
        plan_add_event(m["plan_id"], "council.state",
                       payload={"state": COUNCIL_REAP_STATE[reason], "plan_id": m["plan_id"], "reason": reason,
                                "stale_s": stale_s, "stale_s_source": stale_s_source, "idle_s": round(idle_s, 1),
                                "ref_field": ref_field, "claimed_by": m.get("council_claimed_by"), "error": error},
                       agent="council-reaper", level="error")
        segados.append(m["plan_id"])
    return segados


def set_plan_ledger(plan_id: str, ledger_json: str, approved_by=None, council_state=None) -> bool:
    """ADR-0082 (F.1/F.2): escribe plans.council_ledger_json (decisiones humanas + knowledge_now, ÍNTEGRO) de forma
    ATÓMICA contra el sello: `UPDATE … WHERE plan_id=? AND run_id IS NULL`. Con `approved_by`, sella
    council_approved_by/at (hora del servidor); con `council_state` (el skip: 'skipped-by-human') escribe la columna.
    False = el plan ya respalda una corrida (o no existe) → 409 plan_already_used en app. Un borrador (approved_by None)
    se guarda igual y se puede completar después."""
    _check_council_state(council_state)
    values = {"council_ledger_json": ledger_json}
    if approved_by:
        values.update(council_approved_by=approved_by, council_approved_at=_now())
    elif council_state is None:
        # corrector ADR-0082 (F.1): un BORRADOR guardado DESPUÉS de una aprobación vuelve el ledger a 'draft' — las columnas del
        # aprobador se limpian en el MISMO UPDATE (antes GET /plans/{id} servía approved_by del aprobador anterior junto a
        # ledger.state 'draft' y run_gate cerrado: dos verdades para un solo hecho)
        values.update(council_approved_by=None, council_approved_at=None)
    if council_state:
        values["council_state"] = council_state
    with engine().begin() as cx:
        n = cx.execute(plans.update()
                       .where(plans.c.plan_id == plan_id, plans.c.run_id.is_(None))
                       .values(**values)).rowcount
    return n == 1


def _plans_council_pending_query(user_id, question, entities_csv, since):
    """El SELECT del dedup (expuesto para el smoke): mismo usuario, MISMA pregunta y entities_csv exactos, ronda 1 viva
    (COUNCIL_PENDING_STATES), creado desde `since`. El padre (plan_json.thread_parent_run_id) se compara en Python: el
    JSON no se consulta en SQL (dialecto neutral)."""
    return (select(plans)
            .where(plans.c.user_id == user_id, plans.c.question == question, plans.c.entities_csv == entities_csv,
                   plans.c.council_state.in_(COUNCIL_PENDING_STATES), plans.c.created_at >= since)
            .order_by(plans.c.created_at.desc(), plans.c.plan_id.asc()))


def plans_council_pending(user_id, question, entities_csv, parent_run_id, since):
    """ADR-0082 (E.3) — el dedup del doble clic: el plan VIVO más reciente del MISMO usuario con la MISMA (question,
    entities_csv, parent_run_id) en council_state ∈ {queued, running} creado desde `since` (tz-aware), o None.
    parent_run_id = plan_json.thread_parent_run_id (None en la raíz); un plan_json ilegible no casa (se salta)."""
    if isinstance(since, datetime.datetime) and since.tzinfo is None:
        since = since.replace(tzinfo=datetime.timezone.utc)
    with engine().begin() as cx:
        rows = cx.execute(_plans_council_pending_query(user_id, question, entities_csv or "", since)).all()
    for r in rows:
        d = _plan_row(r)
        try:
            pj = json.loads(d.get("plan_json") or "{}")
        except (ValueError, TypeError):
            continue
        padre = pj.get("thread_parent_run_id") if isinstance(pj, dict) else None
        if (padre or None) != (parent_run_id or None):
            continue
        if _dt_utc(d["created_at"]) < since:   # SQLite compara texto: se re-mide en Python
            continue
        return d
    return None


def count_plans_council(user_id=None, states=None) -> int:
    """COUNT de planes con consejo: `states` (tupla de council_state) acota; None = TODOS los que tienen council_state
    NOT NULL. app: count_plans_council(user_id=<u>, states=('queued',)) = el tope WITT_COUNCIL_MAX_QUEUED_PER_USER."""
    q = select(func.count()).select_from(plans)
    if user_id is not None:
        q = q.where(plans.c.user_id == user_id)
    if states is None:
        q = q.where(plans.c.council_state.isnot(None))
    else:
        q = q.where(plans.c.council_state.in_(tuple(states)))
    with engine().begin() as cx:
        v = cx.execute(q).scalar()
    return int(v or 0)


def _plans_origin_where(q, include_origins, include_unknown=True):
    """El filtro por procedencia de _origin_where, sobre plans (origin NULL = plan anterior al ADR, INCLUIDO por default
    y declarable por el consumidor)."""
    if include_origins is None:
        return q
    cond = plans.c.origin.in_(list(include_origins))
    if include_unknown:
        cond = cond | plans.c.origin.is_(None)
    return q.where(cond)


def plans_council_usage(frm=None, to=None, include_origins=None):
    """ADR-0082 (H) — para GET /usage.plans_council: TODOS los planes con council_state NOT NULL en el periodo
    (created_at), con su gasto de ronda 1 y su sello: [{plan_id, user_id, created_at, origin, council_state,
    council_usage_json, run_id}]. La SUMA y la cotización (in×p_in + out×p_out + caché por multiplicadores) las hace
    app; aquí sólo filas. run_id NOT NULL = el r1 ya está en su corrida (by_stage.council_r1 copiado): el agregador
    lo separa para no sumar dos veces (LOTE-01·A4 aplicado al plan)."""
    q = select(plans.c.plan_id, plans.c.user_id, plans.c.created_at, plans.c.origin, plans.c.council_state,
               plans.c.council_usage_json, plans.c.run_id).where(plans.c.council_state.isnot(None))
    if frm is not None:
        q = q.where(plans.c.created_at >= frm)
    if to is not None:
        q = q.where(plans.c.created_at <= to)
    q = _plans_origin_where(q, include_origins)
    with engine().begin() as cx:
        rows = cx.execute(q.order_by(plans.c.created_at.asc(), plans.c.plan_id.asc())).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d["created_at"] = _dt_utc(d["created_at"])
        out.append(d)
    return out


def plans_with_council(include_origins=None, limit=1000):
    """ADR-0082 (I) — el corpus de PLANES del índice del consejo: planes con council_json (ronda 1 agregada), corridos o
    no (un requisito emitido en un plan nunca corrido también es observación). include_origins None = sin filtro
    (origin NULL incluido y declarable). Filas ligeras + los dos blobs del consejo (council_json, council_ledger_json)."""
    q = (select(plans.c.plan_id, plans.c.user_id, plans.c.question, plans.c.entities_csv, plans.c.created_at,
                plans.c.run_id, plans.c.origin, plans.c.council_state, plans.c.council_json, plans.c.council_ledger_json,
                plans.c.council_finished_at)
         .where(plans.c.council_json.isnot(None)))
    q = _plans_origin_where(q, include_origins)
    with engine().begin() as cx:
        rows = cx.execute(q.order_by(plans.c.created_at.desc(), plans.c.plan_id.asc()).limit(int(limit))).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("created_at", "council_finished_at"):
            d[k] = _dt_utc(d.get(k))
        out.append(d)
    return out


def closed_runs_with_council(limit=1000, include_origins=None):
    """ADR-0082 (I) — closed_runs() acotado a las corridas que llevan runs.council_json (la copia del consejo al encolar,
    F.4) y con esa columna en la fila. El `frozen.council` vive dentro de frozen_record_json (lo parsea el consumidor:
    council_index); aquí no se abre el blob."""
    with engine().begin() as cx:
        q = (select(runs.c.run_id, runs.c.run_no, runs.c.question, runs.c.user_id, runs.c.frozen_at,
                    runs.c.closed_by, runs.c.frozen_record_json, runs.c.origin, runs.c.thread_id,
                    runs.c.turn_no, runs.c.turn_kind, runs.c.parent_run_id, runs.c.council_json)
             .where(runs.c.state == "closed", runs.c.council_json.isnot(None)))
        q = _origin_where(q, include_origins)
        rows = cx.execute(q.order_by(runs.c.frozen_at.desc()).limit(int(limit))).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d["frozen_at"] = _dt_utc(d["frozen_at"])
        out.append(d)
    return out


def _origin_where(q, include_origins, include_unknown=True):
    """ADR-0079 — filtro OPCIONAL por procedencia de la corrida. include_origins=None = sin filtro (el
    llamador decide; db no impone 'production'). Con lista: origin IN lista, y las filas con origin NULL
    (anteriores al ADR, 'unknown-pre-adr-0079') se INCLUYEN por default — su ausencia se declara con
    excluded_by_origin(), no se esconde. include_unknown=False las saca también."""
    if include_origins is None:
        return q
    cond = runs.c.origin.in_(list(include_origins))
    if include_unknown:
        cond = cond | runs.c.origin.is_(None)
    return q.where(cond)


def excluded_by_origin(include_origins, states=None, frm=None, to=None, run_ids=None):
    """ADR-0079 — el CONTADOR que acompaña a todo filtro por origin: lo que un consumidor dejó fuera
    se DECLARA en su respuesta, jamás desaparece en silencio. Sobre la misma base que el consumidor
    (mismos states / rango de fechas / run_ids) devuelve:
      {origins_included: [...], excluded_by_origin: {origin: n}, origin_unknown_included: n, n_included: n}
    origin_unknown_included = filas con origin NULL (pre-ADR) que el filtro sí dejó pasar. Con
    include_origins=None no hay exclusión: excluded_by_origin={} y origins_included=None (declarado)."""
    q = select(runs.c.origin, func.count())
    if states is not None:
        q = q.where(runs.c.state.in_(tuple(states)))
    if frm is not None:
        q = q.where(runs.c.created_at >= frm)
    if to is not None:
        q = q.where(runs.c.created_at <= to)
    if run_ids is not None:
        ids = [r for r in run_ids if r]
        if not ids:
            return {"origins_included": (sorted(include_origins) if include_origins is not None else None),
                    "excluded_by_origin": {}, "origin_unknown_included": 0, "n_included": 0}
        q = q.where(runs.c.run_id.in_(ids))
    with engine().begin() as cx:
        rows = cx.execute(q.group_by(runs.c.origin)).all()
    incl = set(include_origins) if include_origins is not None else None
    excluded, unknown, n_incl = {}, 0, 0
    for origin, n in rows:
        n = int(n)
        if origin is None:
            unknown += n
            n_incl += n
        elif incl is None or origin in incl:
            n_incl += n
        else:
            excluded[origin] = excluded.get(origin, 0) + n
    return {"origins_included": (sorted(incl) if incl is not None else None),
            "excluded_by_origin": dict(sorted(excluded.items())),
            "origin_unknown_included": unknown, "n_included": n_incl}


def plan_history(limit=200, include_origins=None):
    """Insumo DETERMINISTA de las estimaciones del plan (LOTE-01: 'estimaciones con historia').
    Corridas que completaron el pipeline (awaiting_closure/closed), con costo, duración y qué decisor
    de fallback disparó — la mediana se calcula en runs.plan_estimates(), NUNCA la estima un modelo
    (constitución: proyección = tool/script desde insumos declarados).
    ADR-0079: include_origins opcional (None = sin filtro) — una mediana de producción no debería
    absorber corridas de smoke; el llamador decide y declara con excluded_by_origin()."""
    with engine().begin() as cx:
        q = (select(runs.c.started_at, runs.c.finished_at, runs.c.usage_json, runs.c.frozen_record_json)
             .where(runs.c.state.in_(("awaiting_closure", "closed"))))
        q = _origin_where(q, include_origins)
        rows = cx.execute(q.order_by(runs.c.created_at.desc()).limit(limit)).all()
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


def _root_join(*cols):
    """ADR-0081 (F): `SELECT <cols>, root.run_no AS root_run_no FROM runs LEFT OUTER JOIN runs AS root ON
    root.run_id = runs.thread_id`. La RAÍZ de la investigación es la fila cuyo run_id es el thread_id de
    la corrida: la raíz real apunta a sí misma (root == la propia fila ⇒ root_run_no == run_no); el hijo
    de una raíz VIRTUAL (padre pre-ADR-0079 con thread_id NULL) la encuentra por run_id y hereda su
    run_no; una corrida pre-ADR (thread_id NULL) no casa con nadie ⇒ root_run_no NULL DECLARADO, jamás
    rellenado. OUTER: el JOIN nunca quita filas. La llave `root_run_no` nace aquí, en la BD — no en la
    vista (app._run_view es passthrough) ni por corrida (runs._root_run_no hacía db.get_run por renglón);
    lista y detalle la sirven por construcción porque ambos SELECT pasan por esta función (lección
    ADR-0055/0076: una columna que una consulta sirve y la otra no es la asimetría lista/detalle)."""
    root = runs.alias("root")
    return (select(*cols, root.c.run_no.label("root_run_no"))
            .select_from(runs.outerjoin(root, root.c.run_id == runs.c.thread_id)))


def _detail_select():
    """El SELECT del DETALLE (get_run): TODAS las columnas de runs + root_run_no (ADR-0081 (F))."""
    return _root_join(runs)


def get_run(run_id: str):
    with engine().begin() as cx:
        row = cx.execute(_detail_select().where(runs.c.run_id == run_id)).first()
    if row is None:
        return None
    d = dict(row._mapping)
    for k in ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at", "claimed_at"):
        d[k] = _dt_utc(d.get(k))
    return d


def list_runs(user_id=None, limit=50, thread_id=None, after=None):
    """List rows carry the SAME field set the detail view derives from (LOTE-01·A1): heartbeat inputs,
    cancellation authorship and usage — a stuck run must be distinguishable from the LIST, and the
    datetime normalization must match the detail (SQLite drops tzinfo).

    2026-08-29: entities_csv y plan_json ENTRAN al SELECT — la lista los omitía, así que sus
    derivados (genes por renglón, plan_declared, plan_niches) salían vacíos SOLO en la lista
    mientras el detalle sí los servía: la promesa misma-vista de este docstring estaba rota
    para esos campos. _run_view deriva y DESCARTA el blob (plan_json jamás viaja al renglón).
    2026-09-05 (ADR-0076): run_no ENTRA al SELECT — mismo riesgo, misma lección.
    2026-09-14 (ADR-0078): claimed_by/claimed_at ENTRAN al SELECT — la lista debe poder decir qué
    worker tiene cada corrida, igual que el detalle.
    2026-09-15 (ADR-0079): las SIETE columnas de la investigación (THREAD_COLUMNS) ENTRAN al SELECT —
    tercera vez la misma lección (ADR-0055/0076). thread_context_json viaja aquí como plan_json: la
    lista y el detalle comparten columnas, y _run_view lo deriva y DESCARTA (va a su lista de exclusión;
    el snapshot jamás viaja por renglón).

    ADR-0079 — `thread_id`: la lista se vuelve la de los TURNOS de esa investigación, orden turn_no ASC
    (empate por run_no: ambos nacen juntos y crecen juntos), y `after` es el cursor = turn_no EXCLUSIVO
    (turnos con turn_no > after). Sin thread_id el orden sigue siendo created_at DESC y `after` no
    aplica (ValueError: el cursor de turno no tiene sentido sobre la lista general). limit=None = sin
    tope (GET /runs?thread= lee la investigación entera; el llamador pide limit+1 para medir has_more).
    runs_by_thread() es la variante con cursor por run_no/created_at y has_more ya medido."""
    if after is not None and thread_id is None:
        raise ValueError("after (cursor de turn_no) sólo aplica con thread_id (ADR-0079)")
    if limit is not None and int(limit) < 1:
        # corrector ADR-0079: LIMIT -1 es "sin tope" en SQLite y error de sintaxis en Postgres — un tope
        # negativo no es un tope; se rechaza aquí igual que en runs_by_thread
        raise ValueError("limit must be >= 1")
    with engine().begin() as cx:
        q = _list_select()
        if user_id:
            q = q.where(runs.c.user_id == user_id)
        if thread_id is not None:
            q = q.where(runs.c.thread_id == thread_id)
            if after is not None:
                q = q.where(runs.c.turn_no > int(after))
            q = q.order_by(runs.c.turn_no.asc(), runs.c.run_no.asc())
        else:
            q = q.order_by(runs.c.created_at.desc())
        if limit is not None:
            q = q.limit(int(limit))
        rows = cx.execute(q).all()
    return [_list_row(r) for r in rows]


_RUN_DT_KEYS = ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at", "claimed_at")


def _list_select():
    """El SELECT de la LISTA — una sola definición para list_runs y las consultas de la investigación
    (ADR-0079: get_children / thread_turns / runs_by_thread), así ninguna se queda sin una columna que
    la otra sí sirve. Todo lo que no es bundle/registro congelado; get_run (_detail_select) es el detalle.
    ADR-0081 (F): `root_run_no` ENTRA por el JOIN a la raíz (_root_join) — misma definición que el detalle;
    los `.where()/.order_by()/.limit()` que los llamadores encadenan siguen refiriéndose a `runs.c.*`."""
    return _root_join(runs.c.run_id, runs.c.run_no, runs.c.user_id, runs.c.question, runs.c.entities_csv,
                      runs.c.state,
                      runs.c.created_at, runs.c.started_at, runs.c.finished_at, runs.c.frozen_at,
                      runs.c.last_event_at, runs.c.claimed_by, runs.c.claimed_at,
                      runs.c.cancelled_by, runs.c.cancel_reason,
                      runs.c.usage_json, runs.c.epistemic_summary_json, runs.c.error, runs.c.plan_json,
                      runs.c.closed_by,
                      # ADR-0079
                      runs.c.parent_run_id, runs.c.thread_id, runs.c.turn_no, runs.c.turn_kind,
                      runs.c.thread_context_json, runs.c.origin, runs.c.root_question_id,
                      # ADR-0082 (F.4/J): runs.council_json ENTRA al SELECT de la lista — cuarta vez la misma lección
                      # (ADR-0055/0076/0079): _run_view deriva plan_council_state / council_n_valid y DESCARTA el blob;
                      # lista == detalle (smoke_runs_list_http lo mide).
                      runs.c.council_json)


def _list_row(r) -> dict:
    d = dict(r._mapping)
    for k in _RUN_DT_KEYS:
        d[k] = _dt_utc(d.get(k))
    return d


# --- investigación (ADR-0079): consultas de hijos y turnos. db NO deriva thread_id/turn_no/turn_kind —
# eso lo hace runs.py al encolar; aquí sólo se lee lo persistido. -------------------------------------

def get_children(run_id: str):
    """Corridas cuyo parent_run_id es ESTA corrida, en orden de creación (empate por run_id:
    determinista). Insumo de turn_kind='branch' (el padre ya tenía otro hijo) — pero la decisión es del
    llamador. Lista vacía = sin hijos."""
    with engine().begin() as cx:
        rows = cx.execute(_list_select().where(runs.c.parent_run_id == run_id)
                          .order_by(runs.c.created_at.asc(), runs.c.run_id.asc())).all()
    return [_list_row(r) for r in rows]


def has_children(run_id: str) -> bool:
    """Corrector ADR-0079: ¿esta corrida ya tiene algún hijo? Insumo de turn_kind='branch' en runs.derive_thread.
    Un EXISTS en vez de get_children: aquélla cargaba _list_select completo (con el blob thread_context_json)
    sólo para probar no-vacío."""
    with engine().begin() as cx:
        v = cx.execute(select(func.count()).select_from(runs).where(runs.c.parent_run_id == run_id)).scalar()
    return bool(v)


def thread_turns(thread_id: str):
    """Todos los turnos de una investigación, por turn_no y luego created_at (empate por run_id). Una
    corrida pre-ADR no está en ningún hilo (thread_id NULL) y por eso no sale aquí — su ausencia se
    declara en la vista, no se le inventa hilo."""
    with engine().begin() as cx:
        rows = cx.execute(_list_select().where(runs.c.thread_id == thread_id)
                          .order_by(runs.c.turn_no.asc(), runs.c.created_at.asc(),
                                    runs.c.run_id.asc())).all()
    return [_list_row(r) for r in rows]


def max_turn_no(thread_id: str):
    """MAX(turn_no) del hilo, o None si el hilo no tiene turnos (ausencia declarada: el llamador hace
    (max_turn_no(...) or 0) + 1 y decide el caso del padre pre-ADR sin thread_id)."""
    with engine().begin() as cx:
        v = cx.execute(select(func.max(runs.c.turn_no)).where(runs.c.thread_id == thread_id)).scalar()
    return int(v) if v is not None else None


def runs_by_thread(thread_id: str, limit=None, after_run_no=None):
    """Turnos de una investigación PAGINABLES por run_no — variante de biblioteca; NO es la puerta HTTP.
    Corrector ADR-0079: `GET /runs?thread=&after=` pagina con db.list_runs(thread_id, after) y su cursor es
    turn_no EXCLUSIVO; aquí el cursor se llama `after_run_no` (int, run_no del último renglón visto) para que
    los dos no se confundan — antes ambos se llamaban `after` con semánticas distintas. Orden estable turn_no,
    run_no (ambos se asignan al nacer y crecen juntos; run_no desempata sin ambigüedad). limit=None = sin tope.
    Devuelve {items, n, limit, has_more, next_after (run_no del último; None si no hay más)}: se lee limit+1
    para saber si queda página, sin un COUNT extra."""
    q = _list_select().where(runs.c.thread_id == thread_id)
    if after_run_no is not None:
        if isinstance(after_run_no, bool) or not isinstance(after_run_no, int):
            raise ValueError("after_run_no must be a run_no (int)")
        q = q.where(runs.c.run_no > after_run_no)
    q = q.order_by(runs.c.turn_no.asc(), runs.c.run_no.asc())
    if limit is not None:
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        q = q.limit(limit + 1)
    with engine().begin() as cx:
        rows = [_list_row(r) for r in cx.execute(q).all()]
    has_more = limit is not None and len(rows) > limit
    items = rows[:limit] if limit is not None else rows
    return {"items": items, "n": len(items), "limit": limit, "has_more": has_more,
            "next_after": (items[-1]["run_no"] if has_more and items else None)}


# --- índice de investigaciones (ADR-0081 (G)): la lista de hilos con denominador, servida por la BD ---
# Antes no existía GET /threads: la webapp agrupaba las 50 corridas de /runs en el cliente (sin
# denominador, sin paginación, "etiqueta desconocida" cuando la raíz no cargó). Aquí UNA consulta
# agregada por hilo + UNA consulta ligera (sin blobs) sobre los hilos de la página; la agregación fina
# (autores, orígenes, estados, último turno) se hace en Python sobre <= limit_cap hilos — sin
# string_agg/group_concat: dialecto neutral (SQLite en dev/smokes, Postgres en prod).

THREADS_INDEX_CAP = 50   # = app.RUNS_LIST_CAP (ADR-0081 (G): "limit_cap = RUNS_LIST_CAP, reutilizado")
ORIGIN_UNKNOWN_LABEL = "unknown-pre-adr-0079"   # = app.ORIGIN_UNKNOWN (ADR-0079 (A)): origin NULL = pre-contrato
THREADS_INDEX_ORDER = "root_run_no DESC NULLS LAST, thread_id ASC"
THREADS_INDEX_CURSOR_RULE = ("after = root_run_no EXCLUSIVO (se sirven hilos con root_run_no < after); un hilo "
                             "con root_run_no null (raíz sin fila o sin número) va al final y no es alcanzable "
                             "por cursor — se declara, no se inventa número")
THREADS_INDEX_MINE_RULE = ("mine = investigaciones con >= 1 turno cuyo user_id es el de la sesión (la raíz "
                           "virtual pre-ADR-0079 cuenta como turno); n_threads_total es el denominador del "
                           "MISMO filtro")
THREADS_INDEX_N_TURNS_RULE = ("n_turns == GET /threads/{id}: COUNT(*) de las filas con este thread_id "
                              "(root_counted true cuando la raíz real es una de ellas) + 1 si la raíz es "
                              "VIRTUAL (root_pre_adr_0079 true: padre con thread_id NULL, root_counted false); "
                              "n_closed / n_with_record / authors / origins / states incluyen igualmente esa raíz "
                              "virtual. n_with_record = frozen_record_json IS NOT NULL (no valida el JSON; "
                              "GET /threads/{id} sí lo parsea)")
THREADS_INDEX_COSTS = "not-aggregated (GET /threads/{id})"
THREADS_INDEX_ROW_FIELDS = (
    "thread_id", "root_run_id", "root_run_no", "label", "root_pre_adr_0079", "root_counted",
    "root_question", "root_user_id", "root_state", "root_question_id",
    "n_turns", "n_closed", "n_with_record", "n_turns_without_record", "last_turn_no",
    "first_created_at", "last_created_at", "last_turn", "authors", "origins", "states")
THREADS_INDEX_ENVELOPE_FIELDS = (
    "threads", "n", "limit", "limit_cap", "after", "has_more", "next_after", "order", "cursor_rule",
    "mine", "mine_rule", "n_turns_rule", "n_threads_total", "n_runs_without_thread",
    "n_runs_without_thread_rule", "costs")
ROOT_QUESTION_MAX = 120


def _threads_index_query(user_id=None, after=None):
    """La consulta AGREGADA de threads_index, sin ORDER/LIMIT (la comparte el conteo total) — expuesta
    para que el smoke la compile con el dialecto postgresql. GROUP BY runs.thread_id, root.run_id: agrupar
    por la PK del alias es lo que hace que Postgres acepte las columnas `root.*` sin agregar (dependencia
    funcional, PG >= 9.1); SQLite las tolera por columnas desnudas. Declarado: el smoke offline NO mide la
    dependencia funcional (G7 / LG8 la miden en Postgres). Devuelve (query, root)."""
    root = runs.alias("root")
    q = (select(runs.c.thread_id,
                root.c.run_id.label("root_run_id"),
                root.c.run_no.label("root_run_no"),
                root.c.question.label("root_question"),
                root.c.user_id.label("root_user_id"),
                root.c.state.label("root_state"),
                root.c.created_at.label("root_created_at"),
                root.c.thread_id.label("root_thread_id"),          # NULL ⇒ raíz VIRTUAL pre-ADR-0079
                root.c.root_question_id.label("root_question_id"),
                root.c.origin.label("root_origin"),
                case((root.c.frozen_record_json.isnot(None), 1), else_=0).label("root_has_record"),
                func.count().label("n_turns_counted"),
                func.sum(case((runs.c.state == "closed", 1), else_=0)).label("n_closed_counted"),
                func.count(runs.c.frozen_record_json).label("n_with_record_counted"),
                func.max(runs.c.turn_no).label("last_turn_no"),
                func.min(runs.c.created_at).label("first_created_at"),
                func.max(runs.c.created_at).label("last_created_at"))
         .select_from(runs.outerjoin(root, root.c.run_id == runs.c.thread_id))
         .where(runs.c.thread_id.isnot(None))
         .group_by(runs.c.thread_id, root.c.run_id))
    if user_id is not None:
        # >= 1 turno del usuario (subconsulta IN, neutral) O la raíz virtual es suya (no está en el grupo)
        mios = select(runs.c.thread_id).where(runs.c.user_id == user_id, runs.c.thread_id.isnot(None))
        q = q.where(or_(runs.c.thread_id.in_(mios), root.c.user_id == user_id))
    if after is not None:
        q = q.where(root.c.run_no < after)
    return q, root


def _threads_index_light_query(thread_ids):
    """La segunda consulta LIGERA (sin blobs) de threads_index: los turnos de los hilos de la página —
    expuesta para el smoke (compilación postgresql)."""
    return (select(runs.c.thread_id, runs.c.run_id, runs.c.run_no, runs.c.turn_no, runs.c.state,
                   runs.c.user_id, runs.c.origin)
            .where(runs.c.thread_id.in_(list(thread_ids))))


def _iso(v):
    v = _dt_utc(v)
    return v.isoformat(timespec="seconds") if v is not None else None


def threads_index(user_id=None, limit=50, after=None):
    """ADR-0081 (G): el ÍNDICE de investigaciones (la puerta GET /threads?mine=&limit=&after= lo sirve tal
    cual). Orden `root_run_no DESC NULLS LAST, thread_id` (la identidad de una investigación es su T-N);
    el NULLS LAST se emula con CASE (una definición para SQLite y Postgres). Cursor `after` = root_run_no
    EXCLUSIVO; `has_more` MEDIDO con limit+1; limit None o > THREADS_INDEX_CAP ⇒ el tope (declarado en
    limit/limit_cap); limit < 1 ⇒ ValueError; `after` que no sea int ⇒ ValueError (la puerta los vuelve
    400/422). `user_id` ⇒ `mine` (THREADS_INDEX_MINE_RULE). Sin costos ni gap_flags_union: abren los blobs
    por turno y viven en GET /threads/{id} (costs 'not-aggregated').

    Fila (THREADS_INDEX_ROW_FIELDS): thread_id · root_run_id · root_run_no · label 'T-<n>'|None ·
    root_pre_adr_0079 (True = raíz virtual; False = raíz real; None = la fila raíz NO existe) · root_counted
    (¿la raíz entró al COUNT?) · root_question (<= ROOT_QUESTION_MAX) · root_user_id · root_state ·
    root_question_id · n_turns (== GET /threads/{id}, THREADS_INDEX_N_TURNS_RULE) · n_closed · n_with_record ·
    n_turns_without_record · last_turn_no · first_created_at/last_created_at (ISO, segundos) · last_turn
    {run_id, run_no, turn_no, state}|None · authors (ordenados) · origins {origin|ORIGIN_UNKNOWN_LABEL: n} ·
    states {state: n}. Sobre (THREADS_INDEX_ENVELOPE_FIELDS)."""
    if limit is None:
        limit = THREADS_INDEX_CAP
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an int")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    limit = min(limit, THREADS_INDEX_CAP)
    if after is not None and (isinstance(after, bool) or not isinstance(after, int)):
        raise ValueError("after must be a root_run_no (int)")
    q, root = _threads_index_query(user_id, after)
    q_total, _ = _threads_index_query(user_id, None)
    q_page = (q.order_by(case((root.c.run_no.is_(None), 1), else_=0),   # NULLS LAST, dialecto neutral
                         root.c.run_no.desc(), runs.c.thread_id.asc())
              .limit(limit + 1))
    with engine().begin() as cx:
        crudas = [dict(r._mapping) for r in cx.execute(q_page).all()]
        n_total = cx.execute(select(func.count()).select_from(q_total.subquery())).scalar() or 0
        n_sin_hilo = cx.execute(select(func.count()).select_from(runs)
                                .where(runs.c.thread_id.is_(None))).scalar() or 0
        has_more = len(crudas) > limit
        crudas = crudas[:limit]
        ids = [c["thread_id"] for c in crudas]
        turnos = ([dict(r._mapping) for r in cx.execute(_threads_index_light_query(ids)).all()]
                  if ids else [])
    por_hilo = {}
    for t in turnos:
        por_hilo.setdefault(t["thread_id"], []).append(t)
    filas = []
    for c in crudas:
        tid = c["thread_id"]
        raiz_existe = c["root_run_id"] is not None
        raiz_virtual = raiz_existe and c["root_thread_id"] is None
        raiz_contada = raiz_existe and c["root_thread_id"] == tid
        extra = 1 if raiz_virtual else 0     # la raíz virtual no está en el grupo: entra +1, como get_thread
        autores, origenes, estados = set(), {}, {}
        ultimo = None
        for t in por_hilo.get(tid, []):
            autores.add(t["user_id"])
            ko = t["origin"] or ORIGIN_UNKNOWN_LABEL
            origenes[ko] = origenes.get(ko, 0) + 1
            estados[t["state"]] = estados.get(t["state"], 0) + 1
            llave = (t["turn_no"] if t["turn_no"] is not None else -1, t["run_no"] if t["run_no"] is not None else -1)
            if ultimo is None or llave > ultimo[0]:
                ultimo = (llave, t)
        if raiz_virtual:
            autores.add(c["root_user_id"])
            ko = c["root_origin"] or ORIGIN_UNKNOWN_LABEL
            origenes[ko] = origenes.get(ko, 0) + 1
            estados[c["root_state"]] = estados.get(c["root_state"], 0) + 1
        n_turns = int(c["n_turns_counted"]) + extra
        n_closed = int(c["n_closed_counted"] or 0) + (1 if raiz_virtual and c["root_state"] == "closed" else 0)
        n_rec = int(c["n_with_record_counted"] or 0) + (1 if raiz_virtual and c["root_has_record"] else 0)
        pregunta = c["root_question"]
        if isinstance(pregunta, str) and len(pregunta) > ROOT_QUESTION_MAX:
            pregunta = pregunta[:ROOT_QUESTION_MAX]
        filas.append({
            "thread_id": tid,
            "root_run_id": c["root_run_id"],
            "root_run_no": c["root_run_no"],
            "label": f"T-{c['root_run_no']}" if c["root_run_no"] is not None else None,
            "root_pre_adr_0079": (raiz_virtual if raiz_existe else None),
            "root_counted": raiz_contada,
            "root_question": pregunta,
            "root_user_id": c["root_user_id"],
            "root_state": c["root_state"],
            "root_question_id": c["root_question_id"],
            "n_turns": n_turns,
            "n_closed": n_closed,
            "n_with_record": n_rec,
            "n_turns_without_record": n_turns - n_rec,
            "last_turn_no": (int(c["last_turn_no"]) if c["last_turn_no"] is not None else None),
            "first_created_at": _iso(min([c["first_created_at"]] + ([c["root_created_at"]] if raiz_virtual else []))),
            "last_created_at": _iso(c["last_created_at"]),
            "last_turn": ({"run_id": ultimo[1]["run_id"], "run_no": ultimo[1]["run_no"],
                           "turn_no": ultimo[1]["turn_no"], "state": ultimo[1]["state"]} if ultimo else None),
            "authors": sorted(a for a in autores if a is not None),
            "origins": origenes,
            "states": estados,
        })
    ultimo_no = filas[-1]["root_run_no"] if filas else None
    return {
        "threads": filas, "n": len(filas), "limit": limit, "limit_cap": THREADS_INDEX_CAP,
        "after": after, "has_more": has_more,
        "next_after": (ultimo_no if has_more else None),
        "order": THREADS_INDEX_ORDER, "cursor_rule": THREADS_INDEX_CURSOR_RULE,
        "mine": user_id is not None, "mine_rule": THREADS_INDEX_MINE_RULE,
        "n_turns_rule": THREADS_INDEX_N_TURNS_RULE,
        "n_threads_total": int(n_total),
        "n_runs_without_thread": int(n_sin_hilo),
        "n_runs_without_thread_rule": ("COUNT(*) de runs con thread_id NULL = corridas anteriores a ADR-0079 "
                                       "(incluye a las raíces VIRTUALES: son filas pre-contrato)"),
        "costs": THREADS_INDEX_COSTS,
    }


def count_runs_without_thread():
    """ADR-0081 (G): corridas sin investigación (thread_id NULL) = anteriores a ADR-0079, incluidas las que
    hoy sirven de raíz VIRTUAL. Un COUNT, sin blobs."""
    with engine().begin() as cx:
        v = cx.execute(select(func.count()).select_from(runs).where(runs.c.thread_id.is_(None))).scalar()
    return int(v or 0)


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


def runs_usage(frm=None, to=None, include_origins=None):
    """All runs (no cap) with their usage for the M8 aggregation (LOTE-02·2) — the LIST serves max 50;
    a client-side total would be a figure without its full denominator, so the sum lives here.
    ADR-0079: include_origins opcional (None = sin filtro); cada renglón trae su origin para que el
    agregador declare lo que sumó (y excluded_by_origin(frm=, to=) lo que no)."""
    with engine().begin() as cx:
        q = select(runs.c.run_id, runs.c.user_id, runs.c.question, runs.c.state,
                   runs.c.created_at, runs.c.usage_json, runs.c.origin, runs.c.thread_id)
        if frm is not None:
            q = q.where(runs.c.created_at >= frm)
        if to is not None:
            q = q.where(runs.c.created_at <= to)
        q = _origin_where(q, include_origins)
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


def closed_runs(limit=1000, include_origins=None):
    """CLOSED runs only — the precedent corpus (block 6, ADR-0053): a run becomes precedent ONLY after
    explicit closure (frozen_at stamped), never before.
    ADR-0079: include_origins opcional (None = sin filtro). El corpus de precedente y la calibración
    por default sólo deben ver 'production' — esa decisión es del consumidor (precedent/calibration),
    que la declara junto con excluded_by_origin(include_origins, states=('closed',)). Cada renglón
    trae run_no, origin, thread_id, turn_no, turn_kind y parent_run_id para que el consumidor los exponga
    sin otra consulta (T5: turn_kind/parent_run_id faltaban — el item de precedente salía turn_kind NULL
    en una raíz REAL, que se lee 'sin investigación'; la lesión lista/detalle de ADR-0055/0076)."""
    with engine().begin() as cx:
        q = (select(runs.c.run_id, runs.c.run_no, runs.c.question, runs.c.user_id, runs.c.frozen_at,
                    runs.c.closed_by, runs.c.frozen_record_json, runs.c.origin, runs.c.thread_id,
                    runs.c.turn_no,
                    # T5 (integrador, ADR-0079): las dos columnas de investigación que faltaban en este
                    # SELECT — medido por smoke_precedent 'ADR-0079b' (turn_kind None en una raíz real).
                    runs.c.turn_kind, runs.c.parent_run_id)
             .where(runs.c.state == "closed"))
        q = _origin_where(q, include_origins)
        rows = cx.execute(q.order_by(runs.c.frozen_at.desc()).limit(limit)).all()
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


def _frozen_niche_codes(frozen_record_json):
    """ADR-0080: los códigos de nicho de dominio (N*) que un registro congelado DECLARA en `frozen.niches`
    — los DOS ejes (2026-09-05): `catalogo.domain_niches.{primary,secondary}` (medición del catálogo) ∪
    `panel.counts` (juicio del panel). Ninguno se inventa: un registro sin la llave, o ilegible, → set()."""
    if not frozen_record_json:
        return set()
    try:
        rec = json.loads(frozen_record_json)
    except (ValueError, TypeError):
        return set()
    nich = (rec.get("niches") or {}) if isinstance(rec, dict) else {}
    out = set()
    cat = nich.get("catalogo") or {}
    for axis in ((cat.get("domain_niches") or {}).get("primary") or {},
                 (cat.get("domain_niches") or {}).get("secondary") or {}):
        out.update(str(k).strip() for k in axis if str(k).strip())
    panel = nich.get("panel") or {}
    out.update(str(k).strip() for k in (panel.get("counts") or {}) if str(k).strip())
    return out


def calibration_coverage(niche_codes, min_required, include_origins=None):
    """ADR-0080 (A) — MEDICIÓN para la compuerta de competencia: cuántas corridas CLOSED con >=1 rating
    (run_ratings) tienen `frozen.niches` (catálogo o panel) que INTERSECA los nichos del plan.

        {n: int|None, min_required, sufficient: bool, niche_codes, n_closed_rated_total, reason?,
         include_origins, class: 'medicion'}

    Sin nichos (plan ausente, juicio errado o niches=[]) → {n: None, sufficient: False, reason: 'no-niches'}:
    no hay contra qué medir, y eso se declara — jamás un 0 que se leería como 'cero corridas'.
    `include_origins` None = SIN filtro por procedencia (declarado en la salida; ADR-0079: el filtro es
    decisión del consumidor). Sólo cuenta: no promedia calificaciones (ADR-0064/0075)."""
    codes = sorted({str(c).strip() for c in (niche_codes or []) if str(c).strip()})
    base = {"min_required": min_required, "niche_codes": codes, "include_origins": include_origins,
            "class": "medicion"}
    if not codes:
        return {**base, "n": None, "sufficient": False, "reason": "no-niches"}
    with engine().begin() as cx:
        rated = select(run_ratings.c.run_id).distinct()
        q = (select(runs.c.run_id, runs.c.frozen_record_json)
             .where(runs.c.state == "closed", runs.c.run_id.in_(rated)))
        q = _origin_where(q, include_origins)
        rows = cx.execute(q).all()
    wanted = set(codes)
    n = sum(1 for r in rows if _frozen_niche_codes(r._mapping["frozen_record_json"]) & wanted)
    return {**base, "n": n, "n_closed_rated_total": len(rows),
            "sufficient": isinstance(min_required, int) and n >= min_required}


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


def question_calibration(include_origins=None):
    """El tablero de depuración del AGENTE, por versión de spec. Enfrenta lo que el agente AFIRMÓ
    (fits_one_run) con lo que el humano MIDIÓ (rating_input = el eje pregunta, re-anclado al
    TAMAÑO en ADR-0075). Todo son CONTEOS: promediar calificaciones ordinales sería inventar.

    Un borrador sin corrida, o con corrida sin calificar, no se cuenta como acierto ni como
    fallo — se declara pendiente. La ausencia jamás se rellena.

    ADR-0079: include_origins opcional (None = sin filtro). Con lista, un borrador cuya corrida tiene
    origin fuera de la lista se SACA del tablero (no cuenta ni como usado ni como pendiente) y se
    declara en 'excluded_by_origin'; las corridas con origin NULL (pre-ADR) se incluyen y se cuentan en
    'origin_unknown_included'. Un borrador sin corrida no tiene origen que filtrar: sigue pendiente."""
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

    usados = [r.run_id for r in rows if r.run_id]
    origen_tally = excluded_by_origin(include_origins, run_ids=usados)
    origen_de = {}
    if usados:
        with engine().begin() as cx:
            for rid, org in cx.execute(select(runs.c.run_id, runs.c.origin)
                                       .where(runs.c.run_id.in_(usados))).all():
                origen_de[rid] = org
    incl = set(include_origins) if include_origins is not None else None
    n_excluidos_por_origen = 0

    por_version = {}
    for r in rows:
        if (incl is not None and r.run_id and origen_de.get(r.run_id) is not None
                and origen_de[r.run_id] not in incl):
            n_excluidos_por_origen += 1
            continue
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
        # ADR-0079: lo que el filtro por procedencia dejó fuera, declarado (jamás en silencio)
        "origins_included": origen_tally["origins_included"],
        "excluded_by_origin": origen_tally["excluded_by_origin"],
        "n_borradores_excluidos_por_origen": n_excluidos_por_origen,
        "origin_unknown_included": origen_tally["origin_unknown_included"],
    }


# --- bitácora de configuración (ADR-0081 (I)): la tabla config_history --------------------------------
# Append-only por construcción: este módulo NO define update ni delete sobre config_history (el smoke lo
# mide). Quién escribe y cuándo lo decide app.config_ledger_boot()/config_ledger_observe() (S5); aquí
# viven la codificación (JSON, tres estados), el cinturón contra secretos y las lecturas.

CONFIG_LEDGER_TABLE = "config_history"
CONFIG_LEDGER_LIST_LIMIT = 500
# Cinturón (ADR-0081 (I)): un VALOR que contenga cualquiera de estas marcas (sin distinguir mayúsculas)
# NO entra a la tabla — se rechaza y se declara en rejected[] sin copiar el valor. Es un cinturón, no una
# prueba: el snapshot (models.SNAPSHOT_FIELDS) es una lista cerrada que jamás incluye una llave.
CONFIG_LEDGER_SECRET_MARKERS = ("sk-", "key", "token")
CONFIG_LEDGER_REQUIRED = ("field", "value", "source", "changed_by", "scope", "generation", "boot_id")
CONFIG_LEDGER_OPTIONAL = ("previous_value", "note", "recorded_at")
CONFIG_LEDGER_ROW_FIELDS = ("id", "recorded_at", "field", "value", "previous_value", "previous_recorded",
                            "source", "changed_by", "scope", "generation", "boot_id", "note")
_CONFIG_LEDGER_MAXLEN = {"field": 64, "changed_by": 64, "scope": 24, "generation": 32, "boot_id": 32}
# La columna es TEXTO y así se lee (tal cual, sin decodificar): el valor TIPADO vive en el snapshot vivo
# (/config-history.current.fields), la bitácora es su huella textual. Codificación COMPARTIDA con el
# escritor (config_ledger._encode, S5) para que el diff compare texto contra texto sin dos verdades.
CONFIG_LEDGER_ENCODING = ("value/previous_value: str tal cual · None → 'null' (valor declarado ausente) · "
                          "bool → 'true'|'false' · otros → JSON (sort_keys); previous_value SQL NULL "
                          "(previous_recorded false) = primera observación del campo, distinto de 'null'")


def config_ledger_encode(value) -> str:
    """El texto de la columna (CONFIG_LEDGER_ENCODING). Un str entra TAL CUAL (el escritor ya codificó);
    None → 'null'; bool → 'true'|'false'; lo demás → JSON canónico."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def config_ledger_secret_like(value_text):
    """La marca de CONFIG_LEDGER_SECRET_MARKERS que aparece en el texto (minúsculas), o None."""
    bajo = (value_text or "").lower()
    for marca in CONFIG_LEDGER_SECRET_MARKERS:
        if marca in bajo:
            return marca
    return None


def config_ledger_table_exists() -> bool:
    """¿Existe la tabla en la BD conectada? Insumo de ledger_state 'table-missing' (ADR-0081 (I))."""
    try:
        return bool(sa_inspect(engine()).has_table(CONFIG_LEDGER_TABLE))
    except Exception:
        return False


def _config_ledger_row(r) -> dict:
    d = dict(r._mapping)
    return {
        "id": d["id"],
        "recorded_at": _iso(d["recorded_at"]),
        "field": d["field"],
        "value": d["value"],                                     # texto tal cual (CONFIG_LEDGER_ENCODING)
        "previous_value": d["previous_value"],                   # texto | None (SQL NULL)
        "previous_recorded": d["previous_value"] is not None,   # SQL NULL = primera observación
        "source": d["source"], "changed_by": d["changed_by"], "scope": d["scope"],
        "generation": d["generation"], "boot_id": d["boot_id"], "note": d["note"],
    }


def _config_ledger_stamp(v):
    """recorded_at que trae la fila (datetime con o sin zona, o ISO str) → datetime UTC. None → ahora."""
    if v is None:
        return _now()
    if isinstance(v, str):
        v = datetime.datetime.fromisoformat(v)
    if not isinstance(v, datetime.datetime):
        raise ValueError("recorded_at debe ser datetime o ISO str")
    return _dt_utc(v)


def config_ledger_append(rows):
    """APPENDEA filas a config_history. Cada fila: {field, value, source, changed_by, scope, generation,
    boot_id[, previous_value][, note][, recorded_at]}. `value`: texto (un str entra tal cual; None/bool/otros
    se codifican con config_ledger_encode — la MISMA regla que el escritor). `previous_value`: None o llave
    AUSENTE = primera observación del campo → SQL NULL (previous_recorded false); un texto = el anterior
    ('null' = anterior declarado ausente, distinto de SQL NULL). `recorded_at`: opcional (datetime o ISO) —
    el escritor puede sellar un lote con UNA marca (el arranque); ausente → se mide al escribir.

    Validación ESTRUCTURAL (llave requerida ausente, llave desconocida, texto más largo que su columna —
    Postgres lo rechazaría y SQLite no: se rechaza aquí para que el smoke lo vea) -> ValueError y NO se
    escribe ninguna fila del lote. Cinturón: una fila cuyo `value` (o previous_value) codificado parezca
    llave (CONFIG_LEDGER_SECRET_MARKERS) se OMITE y se declara en rejected[] {field, reason
    'secret-like-value', marker, value_len[, where]} — jamás copia el valor; las demás filas del lote sí
    entran. Devuelve {n_written, rejected[], recorded_at (la marca de la última fila escrita | None)}."""
    rows = list(rows or [])
    preparadas, rechazadas = [], []
    for i, fila in enumerate(rows):
        if not isinstance(fila, dict):
            raise ValueError(f"config_ledger_append: fila {i} no es dict")
        faltan = [k for k in CONFIG_LEDGER_REQUIRED if k not in fila]
        if faltan:
            raise ValueError(f"config_ledger_append: fila {i} sin llaves requeridas {faltan}")
        extra = sorted(set(fila) - set(CONFIG_LEDGER_REQUIRED) - set(CONFIG_LEDGER_OPTIONAL))
        if extra:
            raise ValueError(f"config_ledger_append: fila {i} con llaves desconocidas {extra}")
        for k, tope in _CONFIG_LEDGER_MAXLEN.items():
            v = fila[k]
            if not isinstance(v, str) or not v:
                raise ValueError(f"config_ledger_append: fila {i} {k!r} debe ser str no vacío")
            if len(v) > tope:
                raise ValueError(f"config_ledger_append: fila {i} {k!r} excede {tope} caracteres")
        if not isinstance(fila["source"], str) or not fila["source"]:
            raise ValueError(f"config_ledger_append: fila {i} 'source' debe ser str no vacío")
        if "note" in fila and fila["note"] is not None and not isinstance(fila["note"], str):
            raise ValueError(f"config_ledger_append: fila {i} 'note' debe ser str o None")
        sello = _config_ledger_stamp(fila.get("recorded_at"))
        valor = config_ledger_encode(fila["value"])
        marca = config_ledger_secret_like(valor)
        if marca is not None:
            rechazadas.append({"field": fila["field"], "reason": "secret-like-value", "marker": marca,
                               "value_len": len(valor)})
            continue
        previo = fila.get("previous_value")
        previo = config_ledger_encode(previo) if previo is not None else None   # None/ausente → SQL NULL
        if previo is not None and config_ledger_secret_like(previo) is not None:
            rechazadas.append({"field": fila["field"], "reason": "secret-like-value",
                               "marker": config_ledger_secret_like(previo), "value_len": len(previo),
                               "where": "previous_value"})
            continue
        preparadas.append({"recorded_at": sello, "field": fila["field"], "value": valor,
                           "previous_value": previo, "source": fila["source"],
                           "changed_by": fila["changed_by"], "scope": fila["scope"],
                           "generation": fila["generation"], "boot_id": fila["boot_id"],
                           "note": fila.get("note")})
    if preparadas:
        with engine().begin() as cx:
            for p in preparadas:
                cx.execute(config_history.insert().values(**p))
    return {"n_written": len(preparadas), "rejected": rechazadas,
            "recorded_at": (_iso(preparadas[-1]["recorded_at"]) if preparadas else None)}


def config_ledger_last_by_field():
    """La ÚLTIMA fila por campo (MAX(id) por field: id es autoincrement y la tabla es append-only, así que
    el mayor id ES el más reciente — sin depender de empates de recorded_at). {field: fila decodificada
    (CONFIG_LEDGER_ROW_FIELDS)}. {} con tabla vacía."""
    ultimos = (select(func.max(config_history.c.id)).group_by(config_history.c.field)).scalar_subquery()
    with engine().begin() as cx:
        rows = cx.execute(select(config_history).where(config_history.c.id.in_(ultimos))).all()
    return {r._mapping["field"]: _config_ledger_row(r) for r in rows}


def config_ledger_list(limit=CONFIG_LEDGER_LIST_LIMIT):
    """Las filas más recientes primero (recorded_at DESC, id DESC), decodificadas. limit < 1 -> ValueError."""
    limit = int(limit)
    if limit < 1:
        raise ValueError("limit must be >= 1")
    with engine().begin() as cx:
        rows = cx.execute(select(config_history)
                          .order_by(config_history.c.recorded_at.desc(), config_history.c.id.desc())
                          .limit(limit)).all()
    return [_config_ledger_row(r) for r in rows]


def config_ledger_stats():
    """{table, n_rows, last_recorded_at (ISO|None)} — el bloque provenance.db de /config-history."""
    with engine().begin() as cx:
        n = cx.execute(select(func.count()).select_from(config_history)).scalar() or 0
        ult = cx.execute(select(func.max(config_history.c.recorded_at))).scalar()
    return {"table": CONFIG_LEDGER_TABLE, "n_rows": int(n), "last_recorded_at": _iso(ult)}


# --- ADR-0084 (H): cuota mensual del localizador web ---------------------------------------------------------------

def web_locator_usage_table_exists() -> bool:
    """¿Existe la tabla en la BD conectada? Insumo de /usage.web_locator.month_to_date.state 'table-missing' (declarado)."""
    try:
        return bool(sa_inspect(engine()).has_table(WEB_LOCATOR_USAGE_TABLE))
    except Exception:
        return False


def _web_locator_insert_row(cx, month, provider):
    """El INSERT de la fila del mes (costura para el smoke: aquí se simula al PERDEDOR de la carrera UNIQUE)."""
    t = web_locator_usage
    cx.execute(t.insert().values(month=month, provider=provider, n_queries=0, n_results=0, cost_usd_projected=0.0, updated_at=_now()))


def _web_locator_ensure_row(month, provider):
    """INSERT idempotente de la fila (month, provider) — SELECT + INSERT es SQL portable (SQLite y Postgres, sin RETURNING ni
    ON CONFLICT); una carrera entre dos procesos la resuelve la UNIQUE: el perdedor cae al except y la fila ya existe.
    corrector ADR-0084: el INSERT corre en su PROPIA transacción corta, ANTES de la del UPDATE condicional — en PostgreSQL una
    violación de UNIQUE aborta la transacción entera hasta ROLLBACK (InFailedSqlTransaction en la siguiente sentencia); compartir
    la transacción convertía una carrera legítima (dos hilos creando la PRIMERA fila del mes) en una fila 'error' de la ronda.
    → (row_present_before: bool, inserted: bool, lost_race: bool)."""
    t = web_locator_usage
    exists = select(t.c.id).where(t.c.month == month, t.c.provider == provider).limit(1)
    with engine().begin() as cx:
        if cx.execute(exists).first() is not None:
            return True, False, False
    try:
        with engine().begin() as cx:   # transacción PROPIA: si el INSERT falla se revierte SOLA y la del UPDATE nace limpia
            _web_locator_insert_row(cx, month, provider)
        return False, True, False
    except Exception:   # UNIQUE (month, provider): otro proceso la insertó entre el SELECT y el INSERT — la fila existe
        return False, False, True


def _web_locator_row(cx, month, provider):
    t = web_locator_usage
    r = cx.execute(select(t.c.n_queries, t.c.n_results, t.c.cost_usd_projected)
                   .where(t.c.month == month, t.c.provider == provider)).first()
    if r is None:
        return 0, 0, 0.0
    return int(r[0] or 0), int(r[1] or 0), float(r[2] or 0.0)


def web_locator_reserve(provider, month, cap, record=None):
    """ADR-0084 (H) — el `quota_fn` que runs inyecta al harness (web_locator.locate lo llama ANTES de la red y DESPUÉS con
    `record=`). Devuelve {granted, n_before, n_after, cap}.
      · record None (RESERVAR): INSERT idempotente de la fila del mes + `UPDATE … SET n_queries = n_queries + 1 WHERE month
        AND provider AND n_queries < :cap` — rowcount 1 = granted True; 0 = tope alcanzado (granted False, n_after == cap).
        cap == 0 (WITT_WEB_MONTHLY_CAP=0) = sin tope DECLARADO: se cuenta (n_queries + 1) y granted True siempre.
      · record {n_results, cost, n_requests_extra?} (REGISTRAR, tras la llamada): suma n_results y cost_usd_projected sobre la fila y —
        corrector ADR-0084 — suma n_requests_extra a n_queries (peticiones FACTURADAS por encima de la reserva: reintento 429, anthropic
        max_uses > 1; la fila puede rebasar el tope por ese delta declarado, web_locator.QUOTA_RULE); granted None.
    Un cache_hit del tool NO llega aquí (web_locator.locate sondea la caché antes de reservar: 'not-consumed (cache-hit)')."""
    provider = str(provider or "")[:16]
    month = str(month or "")[:7]
    cap = int(cap or 0)
    t = web_locator_usage
    _web_locator_ensure_row(month, provider)   # transacción propia (corrector): la del UPDATE de abajo nace limpia
    with engine().begin() as cx:
        if record is not None:
            n_res = int((record or {}).get("n_results") or 0)
            cost = float((record or {}).get("cost") or 0.0)
            n_extra = max(0, int((record or {}).get("n_requests_extra") or 0))
            cx.execute(t.update().where(t.c.month == month, t.c.provider == provider)
                       .values(n_results=t.c.n_results + n_res, cost_usd_projected=t.c.cost_usd_projected + cost,
                               n_queries=t.c.n_queries + n_extra, updated_at=_now()))
            n_q, _r, _c = _web_locator_row(cx, month, provider)
            return {"granted": None, "n_before": n_q, "n_after": n_q, "cap": cap}
        upd = t.update().where(t.c.month == month, t.c.provider == provider)
        if cap > 0:
            upd = upd.where(t.c.n_queries < cap)
        n = cx.execute(upd.values(n_queries=t.c.n_queries + 1, updated_at=_now())).rowcount
        n_q, _r, _c = _web_locator_row(cx, month, provider)
        granted = n == 1
        return {"granted": granted, "n_before": (n_q - 1) if granted else n_q, "n_after": n_q, "cap": cap}


def web_locator_month_to_date(provider, month):
    """{month, provider, n_queries, n_results, cost_usd_projected, updated_at (ISO|None), row_present} de la fila del mes —
    ceros MEDIDOS con row_present False cuando nada se ha enviado (la ausencia de fila = 0 consultas de este despliegue)."""
    t = web_locator_usage
    with engine().begin() as cx:
        r = cx.execute(select(t).where(t.c.month == str(month or "")[:7], t.c.provider == str(provider or "")[:16])).first()
    if r is None:
        return {"month": month, "provider": provider, "n_queries": 0, "n_results": 0, "cost_usd_projected": 0.0,
                "updated_at": None, "row_present": False}
    d = dict(r._mapping)
    return {"month": d["month"], "provider": d["provider"], "n_queries": int(d["n_queries"] or 0),
            "n_results": int(d["n_results"] or 0), "cost_usd_projected": round(float(d["cost_usd_projected"] or 0.0), 6),
            "updated_at": _iso(d["updated_at"]), "row_present": True}


def web_locator_usage_months(limit=12):
    """Las filas (mes, proveedor) más recientes primero — insumo de /usage.web_locator (ADR-0084 (I))."""
    limit = max(1, int(limit))
    t = web_locator_usage
    with engine().begin() as cx:
        rows = cx.execute(select(t).order_by(t.c.month.desc(), t.c.provider).limit(limit)).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        out.append({"month": d["month"], "provider": d["provider"], "n_queries": int(d["n_queries"] or 0),
                    "n_results": int(d["n_results"] or 0), "cost_usd_projected": round(float(d["cost_usd_projected"] or 0.0), 6),
                    "updated_at": _iso(d["updated_at"])})
    return out


# =====================================================================================================================
# ADR-0086 (F) · imágenes atestiguadas: escribir, leer, adjuntar y RETIRAR (nunca borrar la fila)
# =====================================================================================================================
def attested_schema_state() -> str:
    """'ready' | 'table-missing' | 'error: …' — insumo del 503 declarado de las puertas y del estado del bloque congelado."""
    try:
        return "ready" if sa_inspect(engine()).has_table(ATTESTED_IMAGES_TABLE) else "table-missing"
    except Exception as e:
        return f"error: {type(e).__name__}"


def _attested_row_out(d):
    """La fila como la leen attestations.* (fechas en ISO; los booleanos como tales; ningún byte)."""
    out = dict(d)
    for k in ("uploaded_at", "attached_at", "withdrawn_at"):
        out[k] = _iso(out.get(k))
    for k in ("consent_declared", "third_party_ack", "patient_material", "deidentified_declared"):
        out[k] = bool(out.get(k))
    return out


def attested_image_insert(row: dict) -> bool:
    """INSERT de una imagen recién subida (la fila la arma attestations.build_row). False si ese plan ya tiene ese sha
    (UNIQUE): subir dos veces el MISMO archivo al mismo plan no crea dos identidades."""
    t = plan_attested_images
    vals = {c.name: row.get(c.name) for c in t.columns if c.name != "id"}
    for k in ("uploaded_at", "attached_at", "withdrawn_at"):
        v = vals.get(k)
        if isinstance(v, str) and v:
            try:
                vals[k] = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                vals[k] = _now()
    vals["uploaded_at"] = vals.get("uploaded_at") or _now()
    with engine().begin() as cx:
        if cx.execute(select(t.c.id).where(t.c.plan_id == row["plan_id"], t.c.sha256 == row["sha256"])).first():
            return False
        cx.execute(t.insert().values(**vals))
    return True


def attested_images_of_plan(plan_id: str, include_withdrawn: bool = True, attached_only: bool = False):
    """Las imágenes de un plan en orden de subida (uploaded_at, sha256) — el MISMO orden que ve el panel."""
    t = plan_attested_images
    q = select(t).where(t.c.plan_id == plan_id)
    if not include_withdrawn:
        q = q.where(t.c.withdrawn_at.is_(None))
    if attached_only:
        q = q.where(t.c.attached_to.isnot(None))
    q = q.order_by(t.c.uploaded_at.asc(), t.c.sha256.asc())
    with engine().connect() as cx:
        return [_attested_row_out(dict(r._mapping)) for r in cx.execute(q).fetchall()]


def attested_image_get(plan_id: str, sha256: str):
    """UNA fila por (plan, sha) o None — la puerta de bytes la necesita para decidir quién puede verla."""
    t = plan_attested_images
    with engine().connect() as cx:
        r = cx.execute(select(t).where(t.c.plan_id == plan_id, t.c.sha256 == sha256)).first()
    return _attested_row_out(dict(r._mapping)) if r else None


def attested_image_attach(plan_id: str, sha256: str, attached_to: str, requirement_id=None, by=None) -> bool:
    """Sella la imagen al ledger aprobado (la compuerta humana): sólo si NO está retirada. False si no aplicó."""
    t = plan_attested_images
    with engine().begin() as cx:
        res = cx.execute(t.update().where(t.c.plan_id == plan_id, t.c.sha256 == sha256, t.c.withdrawn_at.is_(None))
                         .values(attached_to=attached_to, requirement_id=requirement_id, attached_by=by,
                                 attached_at=_now(), ledger_state="attached"))
    return bool(res.rowcount)


def attested_image_withdraw(plan_id: str, sha256: str, by: str, reason: str, cascade_n=None) -> bool:
    """LÁPIDA: marca la fila como retirada (identidad, procedencia y decisión se conservan). Los BYTES los borra quien
    llama, del almacén. Idempotente: una fila ya retirada devuelve False y no se re-escribe."""
    t = plan_attested_images
    with engine().begin() as cx:
        res = cx.execute(t.update().where(t.c.plan_id == plan_id, t.c.sha256 == sha256, t.c.withdrawn_at.is_(None))
                         .values(withdrawn_at=_now(), withdrawn_by=by, withdraw_reason=reason,
                                 withdraw_cascade_n=cascade_n, storage_state="withdrawn (tombstone)"))
    return bool(res.rowcount)


def attested_images_inherited_from(plan_id: str, sha256: str):
    """Las copias que otro plan heredó de esta imagen — la cascada del retiro las alcanza."""
    t = plan_attested_images
    with engine().connect() as cx:
        rows = cx.execute(select(t).where(t.c.inherited_from_plan_id == plan_id, t.c.sha256 == sha256,
                                          t.c.withdrawn_at.is_(None))).fetchall()
    return [_attested_row_out(dict(r._mapping)) for r in rows]


def attested_images_uploaded_today(uploaded_by: str, since) -> int:
    """Cuántas subió esta persona desde `since` (tope por persona y día, declarado en la tabla de env)."""
    t = plan_attested_images
    if isinstance(since, str) and since:
        try:
            since = datetime.datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            return 0
    with engine().connect() as cx:
        return int(cx.execute(select(func.count()).select_from(t)
                              .where(t.c.uploaded_by == uploaded_by, t.c.uploaded_at >= since)).scalar() or 0)


def attested_images_usage(plan_ids=None):
    """Agregado para /usage.attested_images: conteos MEDIDOS (nunca proyecciones) sobre las filas vivas."""
    t = plan_attested_images
    q = select(func.count(), func.coalesce(func.sum(t.c.bytes), 0),
               func.sum(case((t.c.withdrawn_at.isnot(None), 1), else_=0)),
               func.sum(case((t.c.attached_to.isnot(None), 1), else_=0)),
               func.sum(case((t.c.patient_material.is_(True), 1), else_=0))).select_from(t)
    if plan_ids:
        q = q.where(t.c.plan_id.in_(list(plan_ids)))
    with engine().connect() as cx:
        n, nbytes, nwd, natt, npat = cx.execute(q).first()
    return {"n_images": int(n or 0), "bytes_total": int(nbytes or 0), "n_withdrawn": int(nwd or 0),
            "n_attached": int(natt or 0), "n_patient_material": int(npat or 0),
            "class": "medición (conteos y bytes de las filas; ningún byte de imagen viaja aquí)"}


# La COMPARACIÓN (qué campo cambió respecto a la última fila) NO vive aquí: es del escritor
# (config_ledger.diff_rows, S5 — ADR-0081 (I): "compara con la ÚLTIMA fila por campo y appendea"). db sólo
# codifica, cuida el cinturón, escribe y lee: una sola verdad para el diff.
