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
    Column("error", Text),
    Column("bundle_json", Text),                              # the full evidence bundle (ADR-0043/0044)
    Column("frozen_record_json", Text),                       # the frozen record the UI renders (read-only)
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

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, future=True)
    return _engine


def init_db():
    metadata.create_all(engine())


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


def create_run(run_id: str, user_id: str, question: str, entities=None):
    with engine().begin() as cx:
        cx.execute(runs.insert().values(run_id=run_id, user_id=user_id, question=question,
                                        entities_csv=",".join(entities or []), state="queued",
                                        created_at=_now(), cancel_requested=False))


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
    with engine().begin() as cx:
        q = select(runs.c.run_id, runs.c.user_id, runs.c.question, runs.c.state,
                   runs.c.created_at, runs.c.finished_at, runs.c.last_event_at)
        if user_id:
            q = q.where(runs.c.user_id == user_id)
        rows = cx.execute(q.order_by(runs.c.created_at.desc()).limit(limit)).all()
    return [dict(r._mapping) for r in rows]


def update_run(run_id: str, **values):
    with engine().begin() as cx:
        cx.execute(runs.update().where(runs.c.run_id == run_id).values(**values))


def request_cancel(run_id: str) -> bool:
    """Flag a queued/running run for cancellation (checked between stages). A queued run cancels
    immediately; a running one cancels at its next stage boundary."""
    with engine().begin() as cx:
        row = cx.execute(select(runs.c.state).where(runs.c.run_id == run_id)).first()
        if row is None or row._mapping["state"] not in ("queued", "running"):
            return False
        cx.execute(runs.update().where(runs.c.run_id == run_id).values(cancel_requested=True))
        if row._mapping["state"] == "queued":
            cx.execute(runs.update().where(runs.c.run_id == run_id, runs.c.state == "queued")
                       .values(state="cancelled", finished_at=_now()))
    return True


def cancel_requested(run_id: str) -> bool:
    with engine().begin() as cx:
        row = cx.execute(select(runs.c.cancel_requested).where(runs.c.run_id == run_id)).first()
    return bool(row and row._mapping["cancel_requested"])


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
