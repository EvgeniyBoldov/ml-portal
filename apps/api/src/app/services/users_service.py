
from __future__ import annotations
from typing import Optional, List
import bcrypt
import uuid
from repositories.users_repo import AsyncUsersRepository
from core.security import verify_password

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

        # Expect password_hash stored as argon2 hash
        try:
            ok = verify_password(password, user.password_hash)
        except Exception:
            ok = False
        return user if ok else None

    async def get_user_by_id(self, user_id: str):
        """Get user by ID"""
        return await self.users_repo.get_by_id(user_id)

    async def create_user(self, email: str, password: str, role: str = "reader", tenant_ids: List[str] = None):
        """Create a new user"""
        if tenant_ids is None:
            tenant_ids = []
        
        # Check if user already exists
        existing_user = await self.users_repo.get_by_email(email)
        if existing_user:
            raise ValueError("User with this email already exists")
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        
        # Create user
        user = await self.users_repo.create(
            id=uuid.uuid4(),
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True
        )
        
        # Add to tenants if specified
        for tenant_id in tenant_ids:
            await self.users_repo.add_to_tenant(user.id, uuid.UUID(tenant_id))
        
        return user

    async def update_user(self, user_id: str, user_data: dict):
        """Update user"""
        user = await self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        # Update fields
        if "email" in user_data:
            # Check if email is already taken by another user
            existing_user = await self.users_repo.get_by_email(user_data["email"])
            if existing_user and existing_user.id != user.id:
                raise ValueError("Email already taken")
            user.email = user_data["email"]
        
        if "role" in user_data:
            user.role = user_data["role"]
        
        if "password" in user_data:
            password_hash = bcrypt.hashpw(user_data["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            user.password_hash = password_hash
        
        await self.users_repo.session.commit()
        return user

    async def delete_user(self, user_id: str):
        """Delete user"""
        user = await self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        # Soft delete - mark as inactive
        user.is_active = False
        await self.users_repo.session.commit()
