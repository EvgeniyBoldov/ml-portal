
from __future__ import annotations
from typing import Optional
import bcrypt
from app.repositories.users_repo import AsyncUsersRepository

class AsyncUsersService:
    def __init__(self, users_repo: AsyncUsersRepository):
        self.users_repo = users_repo

    async def authenticate_user(self, login_or_email: str, password: str):
        # Try login first, then email
        user = await self.users_repo.get_by_login(login_or_email)
        if user is None:
            user = await self.users_repo.get_by_email(login_or_email)

        if user is None or getattr(user, "is_active", True) is False:
            return None

        # Expect password_hash stored as bcrypt hash
        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8"))
        except Exception:
            ok = False
        return user if ok else None

    async def get_user_by_id(self, user_id: str):
        """Get user by ID"""
        return await self.users_repo.get_by_id(user_id)
