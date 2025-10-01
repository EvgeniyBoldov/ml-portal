import asyncio
from typing import Optional

from app.core.db import get_session
from app.repositories.users_repo import UsersRepository
from app.core.security import hash_password
from app.core.config import get_settings  # FIX: add missing import

async def create_superuser() -> None:
    s = get_settings()
    async for session in get_session():
        repo = UsersRepository(session)
        existing = await repo.get_user_by_login(s.SUPERUSER_LOGIN)
        if existing:
            return
        await repo.create_user(
            login=s.SUPERUSER_LOGIN,
            password_hash=hash_password(s.SUPERUSER_PASSWORD),
            name="Admin",
            is_superuser=True,
            role="admin",
        )
        return

if __name__ == "__main__":
    asyncio.run(create_superuser())
