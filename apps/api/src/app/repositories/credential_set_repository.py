"""
Credential Repository v2 - owner-based credentials.
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential_set import Credential


class CredentialRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, credential: Credential) -> Credential:
        self.session.add(credential)
        await self.session.flush()
        await self.session.refresh(credential)
        return credential

    async def get_by_id(self, cred_id: UUID) -> Optional[Credential]:
        stmt = select(Credential).where(Credential.id == cred_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, credential: Credential) -> Credential:
        self.session.add(credential)
        await self.session.flush()
        await self.session.refresh(credential)
        return credential

    async def delete(self, credential: Credential) -> None:
        await self.session.delete(credential)
        await self.session.flush()

    async def list_credentials(
        self,
        skip: int = 0,
        limit: int = 100,
        instance_id: Optional[UUID] = None,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Credential], int]:
        """List credentials with filters"""
        stmt = select(Credential)

        if instance_id:
            stmt = stmt.where(Credential.instance_id == instance_id)
        if owner_user_id:
            stmt = stmt.where(Credential.owner_user_id == owner_user_id)
        if owner_tenant_id:
            stmt = stmt.where(Credential.owner_tenant_id == owner_tenant_id)
        if owner_platform is not None:
            stmt = stmt.where(Credential.owner_platform == owner_platform)
        if is_active is not None:
            stmt = stmt.where(Credential.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0

        stmt = stmt.order_by(Credential.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)

        return list(result.scalars().all()), total

    async def resolve_for_instance(
        self,
        instance_id: UUID,
        strategy: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[Credential]:
        """
        Resolve credential for instance using strategy.

        Strategies:
        - USER_ONLY: only user creds
        - TENANT_ONLY: only tenant creds
        - PLATFORM_ONLY: only platform creds
        - USER_THEN_TENANT: user > tenant
        - TENANT_THEN_PLATFORM: tenant > platform
        - ANY: user > tenant > platform
        """
        base = [Credential.instance_id == instance_id, Credential.is_active == True]

        async def _find_user() -> Optional[Credential]:
            if not user_id:
                return None
            stmt = select(Credential).where(and_(*base, Credential.owner_user_id == user_id))
            return (await self.session.execute(stmt)).scalar_one_or_none()

        async def _find_tenant() -> Optional[Credential]:
            if not tenant_id:
                return None
            stmt = select(Credential).where(and_(*base, Credential.owner_tenant_id == tenant_id))
            return (await self.session.execute(stmt)).scalar_one_or_none()

        async def _find_platform() -> Optional[Credential]:
            stmt = select(Credential).where(and_(*base, Credential.owner_platform == True))
            return (await self.session.execute(stmt)).scalar_one_or_none()

        if strategy == "USER_ONLY":
            return await _find_user()
        elif strategy == "TENANT_ONLY":
            return await _find_tenant()
        elif strategy == "PLATFORM_ONLY":
            return await _find_platform()
        elif strategy == "USER_THEN_TENANT":
            return await _find_user() or await _find_tenant()
        elif strategy == "TENANT_THEN_PLATFORM":
            return await _find_tenant() or await _find_platform()
        else:  # ANY
            return await _find_user() or await _find_tenant() or await _find_platform()

    async def get_all_for_instance(
        self,
        instance_id: UUID,
    ) -> List[Credential]:
        """Get all credentials for a tool instance"""
        stmt = select(Credential).where(
            Credential.instance_id == instance_id
        ).order_by(Credential.created_at.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_credentials(
        self,
        instance_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Check if any active credentials exist (ANY strategy)"""
        cred = await self.resolve_for_instance(
            instance_id=instance_id,
            strategy="ANY",
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return cred is not None
