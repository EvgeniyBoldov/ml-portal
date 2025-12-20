
from __future__ import annotations
from typing import Optional, List
import uuid
from app.repositories.users_repo import AsyncUsersRepository
from app.core.security import verify_password, hash_password

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

        # Verify password with argon2
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def get_user_by_id(self, user_id: str):
        """Get user by ID"""
        return await self.users_repo.get_by_id(user_id)

    async def create_user(self, login: str, email: str, password: str, role: str = "reader", tenant_ids: List[str] = None):
        """Create a new user"""
        if tenant_ids is None:
            tenant_ids = []
        
        # Check if user already exists by login or email
        existing_user = await self.users_repo.get_by_login(login)
        if existing_user:
            raise ValueError("User with this login already exists")
            
        existing_user = await self.users_repo.get_by_email(email)
        if existing_user:
            raise ValueError("User with this email already exists")
        
        # Hash password using argon2 (same as verify_password)
        password_hash = hash_password(password)
        
        # Create user
        user = await self.users_repo.create(
            id=uuid.uuid4(),
            login=login,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True
        )
        
        # Add to tenants if specified
        for index, tenant_id in enumerate(tenant_ids):
            await self.users_repo.add_to_tenant(
                user.id,
                uuid.UUID(tenant_id),
                is_default=index == 0,
            )
        
        # Flush changes (commit handled by UoW)
        await self.users_repo.session.flush()
        
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
            user.password_hash = hash_password(user_data["password"])
        
        if "is_active" in user_data:
            user.is_active = bool(user_data["is_active"])
        
        if "full_name" in user_data:
            user.full_name = user_data["full_name"]
        
        # Flush changes to trigger onupdate
        await self.users_repo.session.flush()
        await self.users_repo.session.refresh(user)
        # Commit handled by UoW
        return user

    async def delete_user(self, user_id: str):
        """Delete user"""
        user = await self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        await self.users_repo.session.delete(user)
        await self.users_repo.session.flush()  # Flush deletion
