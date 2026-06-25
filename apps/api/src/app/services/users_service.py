
from __future__ import annotations
from typing import Optional, List
import uuid
import inspect
from app.repositories.users_repo import AsyncUsersRepository
from app.core.security import verify_password, hash_password
from app.services.chats_service import ChatsService
from app.services.rbac_cleanup_service import RbacCleanupService
from sqlalchemy import func, select
from app.models.user import Users

class AsyncUsersService:
    def __init__(self, users_repo: AsyncUsersRepository):
        self.users_repo = users_repo

    async def authenticate_user(self, login_or_email: str, password: str):
        # Try login first, then email
        user = await self.users_repo.get_by_login(login_or_email)
        if user is None:
            user = await self.users_repo.get_by_email(login_or_email)

        if user is None or not self._is_user_enabled(user):
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
        if getattr(user, "lifecycle_status", "active") != "active":
            raise ValueError("deprecated")
        
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

        if "tenant_ids" in user_data:
            new_tenant_ids = [uuid.UUID(str(t)) for t in (user_data["tenant_ids"] or [])]
            user_uuid = uuid.UUID(str(user.id))

            from sqlalchemy import select, delete
            from app.models.tenant import UserTenants

            result = await self.users_repo.session.execute(
                select(UserTenants.tenant_id).where(UserTenants.user_id == user_uuid)
            )
            current_tenant_ids = [row[0] for row in result.fetchall()]
            current_set = set(current_tenant_ids)
            new_set = set(new_tenant_ids)

            for tenant_id in current_set - new_set:
                await self.users_repo.remove_from_tenant(user_uuid, tenant_id)

            for tenant_id in new_tenant_ids:
                if tenant_id in current_set:
                    continue
                await self.users_repo.add_to_tenant(user_uuid, tenant_id, is_default=False)

            # Keep default tenant deterministic and aligned with UI selection order.
            if new_tenant_ids:
                await self.users_repo.set_default_tenant(user_uuid, new_tenant_ids[0])

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
        if await self._is_last_active_admin(user):
            raise ValueError("last_admin")

        chats_service = ChatsService(self.users_repo.session)
        rbac_cleanup = RbacCleanupService(self.users_repo.session)

        from sqlalchemy import select
        from app.models.chat import Chats

        result = await self.users_repo.session.execute(
            select(Chats.id).where(Chats.owner_id == user.id)
        )
        scalar_result = result.scalars()
        if inspect.isawaitable(scalar_result):
            scalar_result = await scalar_result
        chat_ids = scalar_result.all()
        if inspect.isawaitable(chat_ids):
            chat_ids = await chat_ids
        for chat_id in chat_ids:
            await chats_service.delete_chat(chat_id=chat_id, owner_id=user.id)

        await rbac_cleanup.remove_rules_for_owner(owner_user_id=user.id)

        await self.users_repo.session.delete(user)
        await self.users_repo.session.flush()  # Flush deletion

    async def _is_last_active_admin(self, user: Users) -> bool:
        if user.role != "admin":
            return False
        if not self._is_user_enabled(user):
            return False

        count = int(
            (
                await self.users_repo.session.execute(
                    select(func.count())
                    .select_from(Users)
                    .where(Users.role == "admin")
                    .where(Users.is_active.is_(True))
                    .where(Users.lifecycle_status == "active")
                )
            ).scalar()
            or 0
        )
        return count <= 1

    @staticmethod
    def _is_user_enabled(user: object) -> bool:
        explicit = getattr(user, "is_enabled", None)
        if isinstance(explicit, bool):
            return explicit
        lifecycle = getattr(user, "lifecycle_status", "active")
        if lifecycle == "deprecated":
            return False
        return bool(getattr(user, "is_active", True))
