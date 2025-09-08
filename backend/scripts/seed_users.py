#!/usr/bin/env python3
import os, sys, uuid
from sqlalchemy import create_engine, MetaData, select, insert, update

# hash like the app (argon2)
try:
    from app.core.security import hash_password  # Argon2
except Exception:
    def hash_password(pw: str) -> str:
        return pw

DB_URL = os.environ.get("DB_URL")
ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
USER_LOGIN = os.environ.get("USER_LOGIN", "user")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "user123")

if not DB_URL:
    print("seed_users.py: DB_URL is required", file=sys.stderr)
    sys.exit(2)

engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
md = MetaData()

def _pick(cols, *names):
    for n in names:
        c = getattr(cols, n, None)
        if c is not None:
            return c
    return None

with engine.begin() as conn:
    md.reflect(conn)
    if "users" not in md.tables:
        print("seed_users.py: 'users' table not found; skipping.", file=sys.stderr)
        sys.exit(0)

    users = md.tables["users"]
    cols = users.c
    id_col = _pick(cols, "id")
    login_col = _pick(cols, "login", "email", "username")
    pwd_col = _pick(cols, "password_hash", "hashed_password", "password")
    is_active_col = _pick(cols, "is_active")
    role_col = _pick(cols, "role")

    if login_col is None or pwd_col is None:
        print("seed_users.py: Cannot identify login and password columns.", file=sys.stderr)
        sys.exit(1)

    def upsert(login_value: str, password_value: str, is_admin: bool):
        where = (login_col == login_value)
        row = conn.execute(select(users).where(where)).fetchone()

        fields = {login_col.key: login_value, pwd_col.key: hash_password(password_value)}
        if is_active_col is not None:
            fields[is_active_col.key] = True
        if role_col is not None and row is None:
            fields[role_col.key] = "admin" if is_admin else "reader"

        if row is None and id_col is not None:
            fields[id_col.key] = uuid.uuid4()

        if row is None:
            conn.execute(insert(users).values(**fields))
            print(f"Created {'admin' if is_admin else 'user'}: {login_value}")
        else:
            conn.execute(update(users).where(where).values(**fields))
            print(f"Updated {'admin' if is_admin else 'user'}: {login_value}")

    upsert(ADMIN_LOGIN, ADMIN_PASSWORD, True)
    upsert(USER_LOGIN, USER_PASSWORD, False)

print("seed_users.py: done")
