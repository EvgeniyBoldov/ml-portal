"""
ToolInstance Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tool_instance import ToolInstance


class ToolInstanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, instance: ToolInstance) -> ToolInstance:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, instance_id: UUID) -> Optional[ToolInstance]:
        stmt = (
            select(ToolInstance)
            .options(selectinload(ToolInstance.access_via))
            .where(ToolInstance.id == instance_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, instance: ToolInstance) -> ToolInstance:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ToolInstance) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        instance_kind: Optional[str] = None,
        connector_type: Optional[str] = None,
        connector_subtype: Optional[str] = None,
        placement: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        stmt = select(ToolInstance)
        if is_active is not None:
            stmt = stmt.where(ToolInstance.is_active == is_active)
        if instance_kind is not None:
            stmt = stmt.where(ToolInstance.instance_kind == instance_kind)
        if connector_type is not None:
            stmt = stmt.where(ToolInstance.connector_type == connector_type)
        if connector_subtype is not None:
            stmt = stmt.where(ToolInstance.connector_subtype == connector_subtype)
        if placement is not None:
            stmt = stmt.where(ToolInstance.placement == placement)
        if domain is not None:
            stmt = stmt.where(ToolInstance.domain == domain)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(ToolInstance.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_by_slug(self, slug: str) -> Optional[ToolInstance]:
        """Get instance by slug (globally unique in practice)"""
        stmt = select(ToolInstance).where(ToolInstance.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_health_status(
        self,
        instance_id: UUID,
        status: str,
    ) -> Optional[ToolInstance]:
        """Update health check status"""
        instance = await self.get_by_id(instance_id)
        if not instance:
            return None

        instance.health_status = status
        return await self.update(instance)
