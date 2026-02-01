"""
Policy Repository - data access for Policy and PolicyVersion
"""
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.policy import Policy, PolicyVersion, PolicyStatus


class PolicyRepository:
    """Repository for Policy (container) operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, policy: Policy) -> Policy:
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def get_by_id(self, policy_id: UUID) -> Optional[Policy]:
        stmt = select(Policy).where(Policy.id == policy_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_versions(self, policy_id: UUID) -> Optional[Policy]:
        """Get policy with all versions loaded"""
        stmt = (
            select(Policy)
            .where(Policy.id == policy_id)
            .options(selectinload(Policy.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Policy]:
        stmt = select(Policy).where(Policy.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug_with_versions(self, slug: str) -> Optional[Policy]:
        """Get policy by slug with all versions loaded"""
        stmt = (
            select(Policy)
            .where(Policy.slug == slug)
            .options(selectinload(Policy.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, policy: Policy, data: Dict[str, Any]) -> Policy:
        """Update policy container fields"""
        for key, value in data.items():
            if hasattr(policy, key) and value is not None:
                setattr(policy, key, value)
        await self.session.flush()
        return policy

    async def delete(self, policy: Policy) -> None:
        await self.session.delete(policy)
        await self.session.flush()

    async def list_policies(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Policy], int]:
        """List policies with filters"""
        stmt = select(Policy)
        
        if is_active is not None:
            stmt = stmt.where(Policy.is_active == is_active)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(Policy.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_default(self) -> Optional[Policy]:
        """Get the default policy"""
        return await self.get_by_slug("default")


class PolicyVersionRepository:
    """Repository for PolicyVersion operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, version: PolicyVersion) -> PolicyVersion:
        """Create new policy version"""
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: UUID) -> Optional[PolicyVersion]:
        """Get version by ID"""
        stmt = select(PolicyVersion).where(PolicyVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_policy_and_version(
        self, 
        policy_id: UUID, 
        version: int
    ) -> Optional[PolicyVersion]:
        """Get specific version of a policy"""
        stmt = select(PolicyVersion).where(
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_policy(self, policy_id: UUID) -> Optional[PolicyVersion]:
        """Get active version of a policy"""
        stmt = select(PolicyVersion).where(
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.status == PolicyStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_policy(self, policy_id: UUID) -> Optional[PolicyVersion]:
        """Get latest version of a policy (any status)"""
        stmt = (
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(desc(PolicyVersion.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_policy(
        self, 
        policy_id: UUID,
        status_filter: Optional[str] = None
    ) -> List[PolicyVersion]:
        """Get all versions of a policy ordered by version desc"""
        stmt = (
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
        )
        
        if status_filter:
            stmt = stmt.where(PolicyVersion.status == status_filter)
        
        stmt = stmt.order_by(desc(PolicyVersion.version))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, policy_id: UUID) -> int:
        """Get next version number for a policy"""
        stmt = select(func.max(PolicyVersion.version)).where(
            PolicyVersion.policy_id == policy_id
        )
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def update_status(self, version_id: UUID, status: str) -> None:
        """Update version status"""
        stmt = (
            update(PolicyVersion)
            .where(PolicyVersion.id == version_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def deactivate_active_version(self, policy_id: UUID) -> None:
        """Deactivate currently active version of a policy (set to inactive)"""
        stmt = (
            update(PolicyVersion)
            .where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.status == PolicyStatus.ACTIVE.value
            )
            .values(status=PolicyStatus.INACTIVE.value)
        )
        await self.session.execute(stmt)

    async def update(self, version: PolicyVersion, data: Dict[str, Any]) -> PolicyVersion:
        """Update version fields"""
        for key, value in data.items():
            if hasattr(version, key) and value is not None:
                setattr(version, key, value)
        await self.session.flush()
        return version

    async def delete(self, version: PolicyVersion) -> None:
        """Delete a version"""
        await self.session.delete(version)
        await self.session.flush()

    async def has_draft(self, policy_id: UUID) -> bool:
        """Check if policy has a draft version"""
        stmt = select(func.count()).where(
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.status == PolicyStatus.DRAFT.value
        )
        count = await self.session.scalar(stmt)
        return count > 0
