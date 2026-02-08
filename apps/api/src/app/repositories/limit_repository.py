"""
Limit Repository - data access for Limit and LimitVersion
"""
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.limit import Limit, LimitVersion, LimitStatus


class LimitRepository:
    """Repository for Limit (container) operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, limit: Limit) -> Limit:
        self.session.add(limit)
        await self.session.flush()
        return limit

    async def get_by_id(self, limit_id: UUID) -> Optional[Limit]:
        stmt = select(Limit).where(Limit.id == limit_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Limit]:
        stmt = select(Limit).where(Limit.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug_with_versions(self, slug: str) -> Optional[Limit]:
        stmt = (
            select(Limit)
            .where(Limit.slug == slug)
            .options(selectinload(Limit.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, limit: Limit, data: Dict[str, Any]) -> Limit:
        for key, value in data.items():
            if hasattr(limit, key) and value is not None:
                setattr(limit, key, value)
        await self.session.flush()
        return limit

    async def delete(self, limit: Limit) -> None:
        await self.session.delete(limit)
        await self.session.flush()

    async def list_limits(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Limit], int]:
        stmt = select(Limit)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0

        stmt = stmt.order_by(Limit.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)

        return list(result.scalars().all()), total

    async def get_default(self) -> Optional[Limit]:
        return await self.get_by_slug("default")


class LimitVersionRepository:
    """Repository for LimitVersion operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, version: LimitVersion) -> LimitVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: UUID) -> Optional[LimitVersion]:
        stmt = select(LimitVersion).where(LimitVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_limit_and_version(
        self,
        limit_id: UUID,
        version: int
    ) -> Optional[LimitVersion]:
        stmt = select(LimitVersion).where(
            LimitVersion.limit_id == limit_id,
            LimitVersion.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_limit(self, limit_id: UUID) -> Optional[LimitVersion]:
        stmt = select(LimitVersion).where(
            LimitVersion.limit_id == limit_id,
            LimitVersion.status == LimitStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_limit(self, limit_id: UUID) -> Optional[LimitVersion]:
        stmt = (
            select(LimitVersion)
            .where(LimitVersion.limit_id == limit_id)
            .order_by(desc(LimitVersion.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_limit(
        self,
        limit_id: UUID,
        status_filter: Optional[str] = None
    ) -> List[LimitVersion]:
        stmt = (
            select(LimitVersion)
            .where(LimitVersion.limit_id == limit_id)
        )

        if status_filter:
            stmt = stmt.where(LimitVersion.status == status_filter)

        stmt = stmt.order_by(desc(LimitVersion.version))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, limit_id: UUID) -> int:
        stmt = select(func.max(LimitVersion.version)).where(
            LimitVersion.limit_id == limit_id
        )
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def update_status(self, version_id: UUID, status: str) -> None:
        stmt = (
            update(LimitVersion)
            .where(LimitVersion.id == version_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def deactivate_active_version(self, limit_id: UUID) -> None:
        stmt = (
            update(LimitVersion)
            .where(
                LimitVersion.limit_id == limit_id,
                LimitVersion.status == LimitStatus.ACTIVE.value
            )
            .values(status=LimitStatus.DEPRECATED.value)
        )
        await self.session.execute(stmt)

    async def update(self, version: LimitVersion, data: Dict[str, Any]) -> LimitVersion:
        for key, value in data.items():
            if hasattr(version, key) and value is not None:
                setattr(version, key, value)
        await self.session.flush()
        return version

    async def delete(self, version: LimitVersion) -> None:
        await self.session.delete(version)
        await self.session.flush()

    async def has_draft(self, limit_id: UUID) -> bool:
        stmt = select(func.count()).where(
            LimitVersion.limit_id == limit_id,
            LimitVersion.status == LimitStatus.DRAFT.value
        )
        count = await self.session.scalar(stmt)
        return count > 0
