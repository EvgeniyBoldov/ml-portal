"""
LDAP user provisioning service (Just-in-Time).

Handles:
- Auto-creation of users on first LDAP login
- Profile updates on subsequent logins
- Conflict resolution (local vs LDAP user collision)
- Assignment to default tenant
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.ldap_client import LDAPAuthResult, LDAPUserProfile, LDAPClient
from app.core.logging import get_logger
from app.models.tenant import Tenants, UserTenants
from app.models.user import Users
from app.repositories.users_repo import AsyncUsersRepository
from sqlalchemy import select

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProvisioningResult:
    """Result of user provisioning attempt."""
    success: bool
    user: Users | None = None
    is_new: bool = False
    error: str | None = None


class LDAPUserService:
    """Service for LDAP user provisioning and management."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or Settings()
        self.users_repo = AsyncUsersRepository(session)
        self.ldap_client = LDAPClient(settings)

    async def _get_default_tenant_id(self) -> uuid.UUID | None:
        """Get or create default tenant for LDAP users."""
        result = await self.session.execute(
            select(Tenants).where(Tenants.name == self.settings.AUTH_LDAP_DEFAULT_TENANT_SLUG)
        )
        tenant = result.scalar_one_or_none()

        if tenant:
            return tenant.id

        # Create default tenant if not exists
        tenant = Tenants(
            id=uuid.uuid4(),
            name=self.settings.AUTH_LDAP_DEFAULT_TENANT_SLUG,
            description="Default tenant for LDAP-authenticated users. Administrators should manually assign users to specific tenants.",
            is_active=True,
        )
        self.session.add(tenant)
        await self.session.flush()
        logger.info(f"Created default tenant '{self.settings.AUTH_LDAP_DEFAULT_TENANT_SLUG}' for LDAP users")
        return tenant.id

    async def _check_conflict(self, login: str) -> Users | None:
        """
        Check for existing local user with same login.
        Returns user if conflict (local user exists), None if OK.
        """
        existing = await self.users_repo.get_by_login(login)
        if existing and existing.auth_provider == "local":
            return existing
        return None

    async def _provision_user(self, profile: LDAPUserProfile) -> ProvisioningResult:
        """Create or update user from LDAP profile."""
        # Check for conflict with local user
        conflict = await self._check_conflict(profile.login)
        if conflict:
            logger.warning(f"LDAP login conflict: local user '{profile.login}' exists, denying LDAP auth")
            return ProvisioningResult(
                success=False,
                error="Local user with this login already exists. LDAP authentication denied.",
            )

        # Try to find existing LDAP user by external_id
        existing = await self.users_repo.get_by_external_id("ldap", profile.external_id)

        if existing:
            # Update existing LDAP user
            if self.settings.AUTH_LDAP_UPDATE_PROFILE_ON_LOGIN:
                await self.users_repo.update_ldap_profile(
                    user_id=existing.id,
                    email=profile.email,
                    full_name=profile.full_name,
                    ldap_groups=profile.groups,
                )
                logger.debug(f"Updated LDAP profile for user '{profile.login}'")

            # Update last login
            await self.users_repo.update_last_login(existing.id)

            # Reactivate if previously deactivated and now active in AD
            if not existing.is_active and profile.is_active:
                await self.users_repo.deactivate(existing.id, "", is_active=True)
                logger.info(f"Reactivated LDAP user '{profile.login}' (now active in AD)")

            # Deactivate if disabled in AD
            if existing.is_active and not profile.is_active:
                await self.users_repo.deactivate(existing.id, "ldap_disabled")
                logger.warning(f"Deactivated LDAP user '{profile.login}' (disabled in AD)")

            return ProvisioningResult(success=True, user=existing, is_new=False)

        # Create new LDAP user
        if not self.settings.AUTH_LDAP_AUTO_CREATE_USERS:
            return ProvisioningResult(
                success=False,
                error="User not found and auto-creation is disabled",
            )

        # Get default tenant
        default_tenant_id = await self._get_default_tenant_id()
        if not default_tenant_id:
            return ProvisioningResult(
                success=False,
                error="Failed to resolve default tenant",
            )

        # Create user
        new_user = await self.users_repo.create(
            login=profile.login,
            email=profile.email,
            full_name=profile.full_name,
            password_hash=None,  # LDAP users have no local password
            auth_provider="ldap",
            external_id=profile.external_id,
            ldap_groups=profile.groups,
            role=self.settings.AUTH_LDAP_DEFAULT_ROLE,
            is_active=profile.is_active,
        )

        # Assign to default tenant
        await self.users_repo.add_to_tenant(
            user_id=new_user.id,
            tenant_id=default_tenant_id,
            is_default=True,
        )

        # Record first login
        await self.users_repo.update_last_login(new_user.id)

        logger.info(f"Created new LDAP user '{profile.login}' with tenant '{self.settings.AUTH_LDAP_DEFAULT_TENANT_SLUG}'")
        return ProvisioningResult(success=True, user=new_user, is_new=True)

    async def authenticate_and_provision(self, login: str, password: str) -> ProvisioningResult:
        """
        Authenticate against LDAP and provision user if needed.
        Main entry point for login flow.
        """
        if not self.settings.AUTH_LDAP_ENABLED:
            return ProvisioningResult(success=False, error="LDAP authentication not enabled")

        # Authenticate against LDAP
        auth_result = await self.ldap_client.authenticate(login, password)
        if not auth_result.success:
            return ProvisioningResult(success=False, error=auth_result.error)

        if not auth_result.user:
            return ProvisioningResult(success=False, error="LDAP auth succeeded but no user profile returned")

        # Provision (create or update)
        return await self._provision_user(auth_result.user)

    async def sync_user_status(self, user: Users) -> dict[str, Any]:
        """
        Sync single user status with LDAP (for daily sync task).
        Returns dict with action taken.
        """
        if user.auth_provider != "ldap":
            return {"action": "skipped", "reason": "not_ldap_user"}

        if not user.external_id:
            return {"action": "skipped", "reason": "no_external_id"}

        # Lookup current status in AD
        profile = await self.ldap_client.lookup_user(user.login)

        if profile is None:
            # User not found in AD - deactivate
            if user.is_active:
                await self.users_repo.deactivate(user.id, "ldap_not_found")
                return {"action": "deactivated", "reason": "ldap_not_found"}
            return {"action": "no_change", "reason": "already_inactive"}

        # Update profile fields
        await self.users_repo.update_ldap_profile(
            user_id=user.id,
            email=profile.email,
            full_name=profile.full_name,
            ldap_groups=profile.groups,
        )

        # Handle status changes
        if not profile.is_active and user.is_active:
            await self.users_repo.deactivate(user.id, "ldap_disabled")
            return {"action": "deactivated", "reason": "ldap_disabled"}

        if profile.is_active and not user.is_active:
            # Reactivate (was disabled, now active in AD)
            await self.users_repo.deactivate(user.id, "", is_active=True)
            return {"action": "reactivated"}

        return {"action": "updated", "profile_changed": True}
