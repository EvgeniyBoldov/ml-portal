"""
ToolInstance Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

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
        stmt = select(ToolInstance).where(ToolInstance.id == instance_id)
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
        tool_group_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        stmt = select(ToolInstance)
        
        if tool_group_id:
            stmt = stmt.where(ToolInstance.tool_group_id == tool_group_id)
        if is_active is not None:
            stmt = stmt.where(ToolInstance.is_active == is_active)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(ToolInstance.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_by_tool_group(
        self,
        tool_group_id: UUID,
        is_active: bool = True,
    ) -> List[ToolInstance]:
        """Get all instances for a tool group"""
        stmt = select(ToolInstance).where(
            ToolInstance.tool_group_id == tool_group_id,
            ToolInstance.is_active == is_active,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
