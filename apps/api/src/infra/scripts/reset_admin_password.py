import asyncio
import sys
import os

# Add /app to path
sys.path.append("/app")

from app.core.db import async_session_maker
from app.models.user import Users
from app.core.security import get_password_hash
from sqlalchemy import select

async def main():
    print("Resetting admin password...")
    async with async_session_maker() as session:
        stmt = select(Users).where(Users.login == "admin")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            new_hash = get_password_hash("admin123")
            user.hashed_password = new_hash
            session.add(user)
            await session.commit()
            print("✅ Password updated for user 'admin' to 'admin123'")
        else:
            print("❌ User 'admin' not found")

if __name__ == "__main__":
    asyncio.run(main())
