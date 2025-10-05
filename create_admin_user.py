#!/usr/bin/env python3
"""
Simple script to create admin user for development
"""
import asyncio
import bcrypt
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Import models
from models.user import Users
from models.base import Base

async def create_admin_user():
    """Create admin user with login=admin, password=admin123"""
    
    # Database connection
    DATABASE_URL = "postgresql+asyncpg://ml_portal:ml_portal_password@localhost:5432/ml_portal"
    
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if admin user already exists
        result = await session.execute(select(Users).where(Users.login == "admin"))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print("Admin user already exists!")
            return
        
        # Hash password
        password_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        
        # Create admin user
        admin_user = Users(
            id=uuid.uuid4(),
            login="admin",
            email="admin@localhost",
            password_hash=password_hash,
            is_active=True,
            role="admin",
            can_edit_local_docs=True,
            can_edit_global_docs=True,
            can_trigger_reindex=True,
            can_manage_users=True
        )
        
        session.add(admin_user)
        await session.commit()
        
        print("Admin user created successfully!")
        print(f"Login: admin")
        print(f"Password: admin123")
        print(f"Email: admin@localhost")
        print(f"Role: admin")

if __name__ == "__main__":
    asyncio.run(create_admin_user())
