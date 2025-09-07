import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, MetaData, select, insert, update
from sqlalchemy.exc import SQLAlchemyError

DB_URL = os.environ.get("DB_URL")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
USER_EMAIL = os.environ.get("USER_EMAIL", "user@example.com")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "user123")

if not DB_URL:
    print("seed_users.py: DB_URL is required", file=sys.stderr)
    sys.exit(2)

try:
    from passlib.hash import bcrypt
    def hash_pw(pw: str) -> str:
        return bcrypt.hash(pw)
except Exception:
    def hash_pw(pw: str) -> str:
        return pw  # plaintext fallback

engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
md = MetaData()

with engine.begin() as conn:
    md.reflect(conn)
    if "users" not in md.tables:
        print("seed_users.py: 'users' table not found; skipping.", file=sys.stderr)
        sys.exit(0)

    users = md.tables["users"]
    cols = users.c

    email_col = getattr(cols, "email", None) or getattr(cols, "username", None)
    pwd_col = getattr(cols, "hashed_password", None) or getattr(cols, "password_hash", None) or getattr(cols, "password", None)
    is_active_col = getattr(cols, "is_active", None)
    is_super_col = getattr(cols, "is_superuser", None) or getattr(cols, "is_admin", None) or getattr(cols, "is_staff", None)
    full_name_col = getattr(cols, "full_name", None) or getattr(cols, "name", None)

    if not email_col or not pwd_col:
        print("seed_users.py: Cannot identify email/password columns.", file=sys.stderr)
        sys.exit(1)

    def upsert(email: str, password: str, is_admin: bool):
        row = conn.execute(select(users).where(email_col == email)).fetchone()
        fields = {email_col.key: email, pwd_col.key: hash_pw(password)}
        if is_active_col is not None:
            fields[is_active_col.key] = True
        if is_super_col is not None:
            fields[is_super_col.key] = bool(is_admin)
        if full_name_col is not None and row is None:
            fields[full_name_col.key] = "Admin" if is_admin else "User"
        if row is None:
            conn.execute(insert(users).values(**fields))
            print(f"Created {'admin' if is_admin else 'user'}: {email}")
        else:
            conn.execute(update(users).where(email_col == email).values(**fields))
            print(f"Updated {'admin' if is_admin else 'user'}: {email}")

    upsert(ADMIN_EMAIL, ADMIN_PASSWORD, True)
    upsert(USER_EMAIL, USER_PASSWORD, False)

print("seed_users.py: done")
