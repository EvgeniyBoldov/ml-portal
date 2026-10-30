
from __future__ import annotations
from typing import Optional, List
import uuid
import inspect
from app.repositories.users_repo import AsyncUsersRepository
from app.core.security import verify_password, hash_password
from app.services.memory_scope_preferences_service import MemoryScopePreferencesService
from sqlalchemy import func, select
from app.models.tenant import Tenants
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

    async def create_user(
        self,
        login: str,
        email: Optional[str],
        password: str,
        role: str = "reader",
        tenant_id: Optional[uuid.UUID] = None,
        is_active: bool = True,
        memory_scope_keys: Optional[List[str]] = None,
        is_admin: bool = False,
        full_name: Optional[str] = None,
    ):
        """Create a new user"""
        # Check if user already exists by login or email
        existing_user = await self.users_repo.get_by_login(login)
        if existing_user:
            raise ValueError("User with this login already exists")
            
        existing_user = await self.users_repo.get_by_email(email) if email else None
        if existing_user:
            raise ValueError("User with this email already exists")

        if tenant_id:
            await self._validate_tenant(tenant_id)
        
        # Hash password using argon2 (same as verify_password)
        password_hash = hash_password(password)
        selected_scopes = await MemoryScopePreferencesService(self.users_repo.session).validate_keys(memory_scope_keys or [])
        
        # Create user
        user = await self.users_repo.create(
            id=uuid.uuid4(),
            login=login,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role="admin" if is_admin else ("reader" if role == "admin" else role),
            is_admin=is_admin,
            memory_scope_keys=selected_scopes,
            is_active=is_active
        )
        if tenant_id:
            await self.users_repo.add_to_tenant(
                user.id,
                tenant_id,
                is_default=True,
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

        disabling_admin = (getattr(user, "is_admin", False) is True or user.role == "admin") and self._is_user_enabled(user) and (
            user_data.get("is_admin") is False or (user_data.get("role") is not None and user_data["role"] != "admin")
            or user_data.get("is_active") is False
        )
        if disabling_admin and await self._is_last_active_admin(user):
            raise ValueError("last_admin")

        identity_fields = {"login", "full_name", "email"}
        if getattr(user, "auth_provider", "local") != "local" and identity_fields.intersection(user_data):
            raise ValueError("identity_fields_managed_by_auth_provider")

        if "login" in user_data and user_data["login"] != user.login:
            existing_user = await self.users_repo.get_by_login(user_data["login"])
            if existing_user and existing_user.id != user.id:
                raise ValueError("User with this login already exists")

        if user_data.get("memory_scope_keys") is not None:
            user.memory_scope_keys = await MemoryScopePreferencesService(self.users_repo.session).validate_keys(user_data["memory_scope_keys"])
        
        # Update fields
        if "email" in user_data:
            # Check if email is already taken by another user
            existing_user = await self.users_repo.get_by_email(user_data["email"]) if user_data["email"] else None
            if existing_user and existing_user.id != user.id:
                raise ValueError("Email already taken")
            user.email = user_data["email"]

        if "login" in user_data:
            user.login = user_data["login"]
        
        if user_data.get("role") is not None:
            # Legacy clients may still send a role; admin status is kept in its own flag.
            user.role = "admin" if user_data["role"] == "admin" else user_data["role"]
            if user_data["role"] == "admin":
                user.is_admin = True
        if user_data.get("is_admin") is not None:
            user.is_admin = bool(user_data["is_admin"])
            user.role = "admin" if user.is_admin else ("reader" if user.role == "admin" else user.role)
        
        if "password" in user_data:
            user.password_hash = hash_password(user_data["password"])
        
        if user_data.get("is_active") is not None:
            user.is_active = bool(user_data["is_active"])
        
        if "full_name" in user_data:
            user.full_name = user_data["full_name"]

        if "tenant_id" in user_data:
            selected_tenant_id = user_data["tenant_id"]
            selected_tenant_id = uuid.UUID(str(selected_tenant_id)) if selected_tenant_id else None
            if selected_tenant_id:
                await self._validate_tenant(selected_tenant_id)
            user_uuid = uuid.UUID(str(user.id))

            from sqlalchemy import select
            from app.models.tenant import UserTenants

            result = await self.users_repo.session.execute(
                select(UserTenants.tenant_id).where(UserTenants.user_id == user_uuid)
            )
            existing_tenant_ids = [row[0] for row in result.fetchall()]
            for current_tenant_id in set(existing_tenant_ids):
                if current_tenant_id != selected_tenant_id:
                    await self.users_repo.remove_from_tenant(user_uuid, current_tenant_id)

            if selected_tenant_id:
                if selected_tenant_id not in existing_tenant_ids:
                    await self.users_repo.add_to_tenant(user_uuid, selected_tenant_id, is_default=True)
                else:
                    await self.users_repo.set_default_tenant(user_uuid, selected_tenant_id)

        # Flush changes to trigger onupdate
        await self.users_repo.session.flush()
        await self.users_repo.session.refresh(user)
        # Commit handled by UoW
        return user

    @staticmethod
    def _is_user_enabled(user: object) -> bool:
        explicit = getattr(user, "is_enabled", None)
        if isinstance(explicit, bool):
            return explicit
        lifecycle = getattr(user, "lifecycle_status", "active")
        if lifecycle == "deprecated":
            return False
        return bool(getattr(user, "is_active", True))

    async def _is_last_active_admin(self, user: Users) -> bool:
        result = await self.users_repo.session.execute(
                    select(func.count())
                    .select_from(Users)
                    .where(Users.is_admin.is_(True))
                    .where(Users.is_active.is_(True))
                    .where(Users.lifecycle_status == "active")
                )
        value = result.scalar()
        if inspect.isawaitable(value):
            value = await value
        count = int(value or 0)
        return count <= 1

    async def _validate_tenant(self, tenant_id: uuid.UUID) -> None:
        tenant = await self.users_repo.session.get(Tenants, tenant_id)
        if (
            tenant is None
            or not bool(getattr(tenant, "is_active", False))
            or getattr(tenant, "lifecycle_status", "active") != "active"
        ):
            raise ValueError("tenant_not_available")
