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
    Column("note", Text, nullable=False, default=""),
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
    for stmt in ("ALTER TABLE runs ADD COLUMN cancelled_by VARCHAR(64)",
                 "ALTER TABLE runs ADD COLUMN cancel_reason TEXT",
                 "ALTER TABLE runs ADD COLUMN usage_json TEXT",
                 "ALTER TABLE runs ADD COLUMN epistemic_summary_json TEXT",
                 "ALTER TABLE runs ADD COLUMN plan_json TEXT"):
        try:
            with engine().begin() as cx:
                cx.execute(text(stmt))
        except Exception:
            pass  # column already there
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
    with engine().begin() as cx:
        cx.execute(runs.insert().values(run_id=run_id, user_id=user_id, question=question,
                                        entities_csv=",".join(entities or []), state="queued",
                                        created_at=_now(), cancel_requested=False,
                                        plan_json=plan_json))


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


def claim_next_queued():
    """Atomically claim the oldest queued run (optimistic UPDATE ... WHERE state='queued'). Returns the
    run row (dict) or None. FIFO by created_at."""
    with engine().begin() as cx:
        row = cx.execute(select(runs).where(runs.c.state == "queued")
                         .order_by(runs.c.created_at).limit(1)).first()
        if row is None:
            return None
        n = cx.execute(runs.update()
                       .where(runs.c.run_id == row._mapping["run_id"], runs.c.state == "queued")
                       .values(state="running", started_at=_now())).rowcount
        if n != 1:  # another worker won the race
            return None
        return dict(row._mapping)


def get_run(run_id: str):
    with engine().begin() as cx:
        row = cx.execute(select(runs).where(runs.c.run_id == run_id)).first()
    if row is None:
        return None
    d = dict(row._mapping)
    for k in ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at"):
        d[k] = _dt_utc(d.get(k))
    return d


def list_runs(user_id=None, limit=50):
    """List rows carry the SAME field set the detail view derives from (LOTE-01·A1): heartbeat inputs,
    cancellation authorship and usage — a stuck run must be distinguishable from the LIST, and the
    datetime normalization must match the detail (SQLite drops tzinfo)."""
    with engine().begin() as cx:
        q = select(runs.c.run_id, runs.c.user_id, runs.c.question, runs.c.state,
                   runs.c.created_at, runs.c.started_at, runs.c.finished_at, runs.c.frozen_at,
                   runs.c.last_event_at, runs.c.cancelled_by, runs.c.cancel_reason,
                   runs.c.usage_json, runs.c.epistemic_summary_json, runs.c.error)
        if user_id:
            q = q.where(runs.c.user_id == user_id)
        rows = cx.execute(q.order_by(runs.c.created_at.desc()).limit(limit)).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("created_at", "started_at", "finished_at", "frozen_at", "last_event_at"):
            d[k] = _dt_utc(d.get(k))
        out.append(d)
    return out


def update_run(run_id: str, **values):
    with engine().begin() as cx:
        cx.execute(runs.update().where(runs.c.run_id == run_id).values(**values))


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
               rating_output, rating_output_state, note: str = "") -> dict:
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
        "note": note or "",
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
