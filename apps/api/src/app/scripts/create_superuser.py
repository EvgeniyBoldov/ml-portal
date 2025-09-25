from __future__ import annotations
import os, sys

try:
    from app.services.auth_service import AuthService  # type: ignore
except Exception:
    print("[create_superuser] cannot import AuthService. Adjust import path.")
    sys.exit(1)

def main() -> int:
    email = os.getenv("ADMIN_EMAIL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    password = os.getenv("ADMIN_PASSWORD") or (sys.argv[2] if len(sys.argv) > 2 else None)
    if not email or not password:
        print("Usage: ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m app.scripts.create_superuser")
        return 2
    auth = AuthService()
    user = auth.create_superuser(email=email, password=password)
    print(f"Created superuser: {user}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
