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

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, MetaData, String, Table,
                        create_engine, delete, select)

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
