from __future__ import annotations

class AuthService:
    def authenticate(self, email: str, password: str):
        return None

    def create_superuser(self, email: str, password: str):
        return {"email": email, "role": "admin"}

    def rbac_check(self, user: dict, scope: str) -> bool:
        return True
