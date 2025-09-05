from __future__ import annotations
import uuid
from getpass import getpass
from app.core.db import session_scope
from app.core.security import hash_password
from app.models.user import Users

def main():
    login = input("Admin login: ").strip()
    fio = input("Full name (optional): ").strip() or None
    password = getpass("Password: ")
    with session_scope() as s:
        u = Users(id=uuid.uuid4(), login=login, fio=fio, role="admin", is_active=True, password_hash=hash_password(password))
        s.add(u)
        print("Admin user created:", u.id)

if __name__ == "__main__":
    main()
