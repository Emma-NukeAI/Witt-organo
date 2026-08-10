"""
seed_users.py — account administration for the webapp backend. LOCAL CLI ONLY (the one asymmetry).

Flat permissions (ADR-0047 / webapp decision 9-bis): the 5 accounts are equals over HTTP; creating
users, resetting passwords and disabling accounts happens ONLY here, run by Emmanuel on a machine
with DB access. This is deliberately NOT an HTTP endpoint.

Usage (WITT_BACKEND_DB_URL selects the DB; defaults to the local SQLite dev file):
    python seed_users.py init                      # create the 5 accounts, print passwords ONCE
    python seed_users.py set-password natalia      # reset one password (prints the new one ONCE)
    python seed_users.py disable sharon            # disable + revoke sessions
    python seed_users.py enable sharon
    python seed_users.py list

Passwords are random (secrets.token_urlsafe) and printed to stdout exactly once — distribute them
out-of-band; the DB stores only scrypt hashes (db.py). Never commit passwords anywhere.
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

# The 5 accounts (webapp decision 3): médicos rate as 'medico', devs as 'dev' (rater_profile).
TEAM = [
    ("marcelo", "Marcelo", "medico"),
    ("natalia", "Natalia", "medico"),
    ("martin", "Martín", "medico"),
    ("emmanuel", "Emmanuel", "dev"),
    ("sharon", "Sharon", "dev"),
]


def _new_password():
    return secrets.token_urlsafe(12)


def cmd_init(_args):
    db.init_db()
    print("cuenta       rol      password (se muestra UNA vez)")
    print("-" * 55)
    for user_id, display, role in TEAM:
        pw = _new_password()
        db.upsert_user(user_id, display, role, pw)
        print(f"{user_id:<12} {role:<8} {pw}")
    print("-" * 55)
    print("Distribuye cada password por canal directo (no al Drive compartido, no a git).")


def cmd_set_password(args):
    db.init_db()
    known = {u for u, _, _ in TEAM} | {u["user_id"] for u in db.list_users()}
    if args.user not in known:
        sys.exit(f"usuario desconocido: {args.user}")
    current = {u["user_id"]: u for u in db.list_users()}.get(args.user)
    display = current["display_name"] if current else dict((u, d) for u, d, _ in TEAM)[args.user]
    role = current["role"] if current else dict((u, r) for u, _, r in TEAM)[args.user]
    pw = _new_password()
    db.upsert_user(args.user, display, role, pw)
    print(f"{args.user}: {pw}   (se muestra UNA vez)")


def cmd_disable(args):
    db.init_db()
    db.set_disabled(args.user, True)
    print(f"{args.user}: disabled (sesiones revocadas)")


def cmd_enable(args):
    db.init_db()
    db.set_disabled(args.user, False)
    print(f"{args.user}: enabled")


def cmd_list(_args):
    db.init_db()
    for u in db.list_users():
        flag = " [DISABLED]" if u["disabled"] else ""
        print(f"{u['user_id']:<12} {u['role']:<8} {u['display_name']}{flag}")


def main():
    ap = argparse.ArgumentParser(description="Account admin (local-only asymmetry, ADR-0047).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    p = sub.add_parser("set-password"); p.add_argument("user"); p.set_defaults(fn=cmd_set_password)
    p = sub.add_parser("disable"); p.add_argument("user"); p.set_defaults(fn=cmd_disable)
    p = sub.add_parser("enable"); p.add_argument("user"); p.set_defaults(fn=cmd_enable)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
