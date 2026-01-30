"""
ToolGroup Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_group import ToolGroup


class ToolGroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, group: ToolGroup) -> ToolGroup:
        self.session.add(group)
        await self.session.flush()
        await self.session.refresh(group)
        return group

    async def get_by_id(self, group_id: UUID) -> Optional[ToolGroup]:
        stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[ToolGroup]:
        stmt = select(ToolGroup).where(ToolGroup.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, group: ToolGroup) -> ToolGroup:
        self.session.add(group)
        await self.session.flush()
        await self.session.refresh(group)
        return group

    async def delete(self, group: ToolGroup) -> None:
        await self.session.delete(group)
        await self.session.flush()

    async def list_groups(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ToolGroup], int]:
        """List tool groups"""
        stmt = select(ToolGroup)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(ToolGroup.name).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total
