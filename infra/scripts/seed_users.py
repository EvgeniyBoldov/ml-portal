# backend/scripts/seed_users.py
import os, sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, select, insert, update
from sqlalchemy.exc import SQLAlchemyError

DB_URL = os.environ.get("DB_URL") or os.environ.get("DB.URL")
if not DB_URL:
    print("seed_users.py: DB_URL is required", file=sys.stderr); sys.exit(2)

ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
USER_LOGIN = os.environ.get("USER_LOGIN", "user")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "user123")

try:
    from passlib.hash import bcrypt
    def hash_pw(pw: str) -> str: return bcrypt.hash(pw)
except Exception:
    def hash_pw(pw: str) -> str: return pw  # plaintext fallback

engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
md = MetaData()

with engine.begin() as conn:
    # No create_all here — we rely on Alembic migrations.
    md.reflect(conn)
    if "users" not in md.tables:
        print("seed_users.py: users table not found — run migrations first.", file=sys.stderr)
        sys.exit(3)
    users_tbl = md.tables["users"]

    def col(name, alt=None):
        c = users_tbl.c.get(name)
        if c is None and alt:
            c = users_tbl.c.get(alt)
        if c is None:
            raise RuntimeError(f"seed_users.py: column not found: {name}")
        return c

    login_col = col("login", "username")
    pwd_col = users_tbl.c.get("password_hash") or users_tbl.c.get("password") or users_tbl.c.get("hashed_password")
    if pwd_col is None:
        print("seed_users.py: cannot identify password column", file=sys.stderr); sys.exit(4)
    is_active_col = users_tbl.c.get("is_active")
    role_col = users_tbl.c.get("role")
    fio_col = users_tbl.c.get("fio") or users_tbl.c.get("full_name") or users_tbl.c.get("name")

    def upsert_user(login: str, password: str, is_admin: bool, fio: str | None):
        existing = conn.execute(select(users_tbl).where(login_col == login)).first()
        if existing:
            upd = {pwd_col.key: hash_pw(password)}
            if is_active_col is not None: upd[is_active_col.key] = True
            if role_col is not None and is_admin: upd[role_col.key] = "admin"
            conn.execute(update(users_tbl).where(login_col == login).values(**upd))
        else:
            ins = {login_col.key: login, pwd_col.key: hash_pw(password)}
            if is_active_col is not None: ins[is_active_col.key] = True
            if role_col is not None: ins[role_col.key] = ("admin" if is_admin else "reader")
            if fio_col is not None: ins[fio_col.key] = fio
            conn.execute(insert(users_tbl).values(**ins))

    try:
        upsert_user(ADMIN_LOGIN, ADMIN_PASSWORD, True, "Admin")
        upsert_user(USER_LOGIN, USER_PASSWORD, False, "User")
        print("seed_users.py: users ready")
    except SQLAlchemyError as e:
        print(f"seed_users.py: error: {e}", file=sys.stderr); sys.exit(5)
