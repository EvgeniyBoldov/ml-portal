"""
Repository for Baseline operations.
Baseline is a separate entity from Prompt for managing restrictions and rules.
"""
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.baseline import Baseline, BaselineVersion, BaselineStatus, BaselineScope


class BaselineRepository:
    """Repository for Baseline (container) operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, baseline: Baseline) -> Baseline:
        """Create new baseline container"""
        self.session.add(baseline)
        await self.session.flush()
        return baseline

    async def get_by_id(self, baseline_id: UUID) -> Optional[Baseline]:
        """Get baseline container by ID"""
        stmt = select(Baseline).where(Baseline.id == baseline_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Baseline]:
        """Get baseline container by slug"""
        stmt = select(Baseline).where(Baseline.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_baselines(
        self, 
        skip: int = 0, 
        limit: int = 100,
        scope_filter: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Baseline], int]:
        """List baseline containers with pagination and filters"""
        base_query = select(Baseline)
        
        if scope_filter:
            base_query = base_query.where(Baseline.scope == scope_filter)
        
        if tenant_id:
            base_query = base_query.where(Baseline.tenant_id == tenant_id)
        
        if user_id:
            base_query = base_query.where(Baseline.user_id == user_id)
        
        if is_active is not None:
            base_query = base_query.where(Baseline.is_active == is_active)
        
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        # Get paginated results
        stmt = base_query.order_by(Baseline.slug).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    async def get_by_scope(
        self,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> List[Baseline]:
        """Get baselines by scope with optional tenant/user filter"""
        stmt = select(Baseline).where(
            Baseline.scope == scope,
            Baseline.is_active == True
        )
        
        if scope == BaselineScope.TENANT.value and tenant_id:
            stmt = stmt.where(Baseline.tenant_id == tenant_id)
        elif scope == BaselineScope.USER.value and user_id:
            stmt = stmt.where(Baseline.user_id == user_id)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_effective_baselines(
        self,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> List[Baseline]:
        """
        Get effective baselines for a user/tenant.
        Resolution priority: User > Tenant > Default
        Returns all applicable baselines merged.
        """
        baselines = []
        
        # 1. Default baselines (always apply)
        default_baselines = await self.get_by_scope(BaselineScope.DEFAULT.value)
        baselines.extend(default_baselines)
        
        # 2. Tenant baselines (if tenant_id provided)
        if tenant_id:
            tenant_baselines = await self.get_by_scope(
                BaselineScope.TENANT.value, 
                tenant_id=tenant_id
            )
            baselines.extend(tenant_baselines)
        
        # 3. User baselines (if user_id provided)
        if user_id:
            user_baselines = await self.get_by_scope(
                BaselineScope.USER.value, 
                user_id=user_id
            )
            baselines.extend(user_baselines)
        
        return baselines

    async def update(self, baseline: Baseline, data: Dict[str, Any]) -> Baseline:
        """Update baseline container fields"""
        for key, value in data.items():
            if hasattr(baseline, key) and value is not None:
                setattr(baseline, key, value)
        await self.session.flush()
        return baseline

    async def delete(self, baseline_id: UUID) -> bool:
        """Delete baseline container (cascade deletes versions)"""
        baseline = await self.get_by_id(baseline_id)
        if not baseline:
            return False
        await self.session.delete(baseline)
        await self.session.flush()
        return True


class BaselineVersionRepository:
    """Repository for BaselineVersion operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, version: BaselineVersion) -> BaselineVersion:
        """Create new baseline version"""
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: UUID) -> Optional[BaselineVersion]:
        """Get version by ID"""
        stmt = select(BaselineVersion).where(BaselineVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_baseline_and_version(
        self, 
        baseline_id: UUID, 
        version: int
    ) -> Optional[BaselineVersion]:
        """Get specific version of a baseline"""
        stmt = select(BaselineVersion).where(
            BaselineVersion.baseline_id == baseline_id,
            BaselineVersion.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_baseline(self, baseline_id: UUID) -> Optional[BaselineVersion]:
        """Get active version of a baseline"""
        stmt = select(BaselineVersion).where(
            BaselineVersion.baseline_id == baseline_id,
            BaselineVersion.status == BaselineStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_baseline(self, baseline_id: UUID) -> Optional[BaselineVersion]:
        """Get latest version of a baseline (any status)"""
        stmt = (
            select(BaselineVersion)
            .where(BaselineVersion.baseline_id == baseline_id)
            .order_by(desc(BaselineVersion.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_baseline(self, baseline_id: UUID) -> List[BaselineVersion]:
        """Get all versions of a baseline ordered by version desc"""
        stmt = (
            select(BaselineVersion)
            .where(BaselineVersion.baseline_id == baseline_id)
            .order_by(desc(BaselineVersion.version))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, baseline_id: UUID) -> int:
        """Get next version number for a baseline"""
        stmt = select(func.max(BaselineVersion.version)).where(
            BaselineVersion.baseline_id == baseline_id
        )
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def update_status(self, version_id: UUID, status: str) -> None:
        """Update version status"""
        stmt = (
            update(BaselineVersion)
            .where(BaselineVersion.id == version_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def archive_active_version(self, baseline_id: UUID) -> None:
        """Archive currently active version of a baseline"""
        stmt = (
            update(BaselineVersion)
            .where(
                BaselineVersion.baseline_id == baseline_id,
                BaselineVersion.status == BaselineStatus.ACTIVE.value
            )
            .values(status=BaselineStatus.ARCHIVED.value)
        )
        await self.session.execute(stmt)

    async def update(self, version: BaselineVersion, data: Dict[str, Any]) -> BaselineVersion:
        """Update version fields"""
        for key, value in data.items():
            if hasattr(version, key) and value is not None:
                setattr(version, key, value)
        await self.session.flush()
        return version

    async def has_draft(self, baseline_id: UUID) -> bool:
        """Check if baseline has a draft version"""
        stmt = select(func.count()).where(
            BaselineVersion.baseline_id == baseline_id,
            BaselineVersion.status == BaselineStatus.DRAFT.value
        )
        count = await self.session.scalar(stmt)
        return count > 0
