"""
Tool Repository v2
"""
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool


class ToolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tool: Tool) -> Tool:
        self.session.add(tool)
        await self.session.flush()
        await self.session.refresh(tool)
        return tool

    async def get_by_id(self, tool_id: UUID) -> Optional[Tool]:
        stmt = select(Tool).where(Tool.id == tool_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Tool]:
        stmt = select(Tool).where(Tool.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, tool: Tool) -> Tool:
        self.session.add(tool)
        await self.session.flush()
        await self.session.refresh(tool)
        return tool

    async def delete(self, tool: Tool) -> None:
        await self.session.delete(tool)
        await self.session.flush()

    async def list_tools(
        self,
        skip: int = 0,
        limit: int = 100,
        domain: Optional[str] = None,
    ) -> Tuple[List[Tool], int]:
        stmt = select(Tool)
        if domain:
            stmt = stmt.where(Tool.domains.any(domain))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0

        stmt = stmt.order_by(Tool.slug).offset(skip).limit(limit)
        result = await self.session.execute(stmt)

        return list(result.scalars().all()), total

    async def get_by_domain(self, domain: str) -> List[Tool]:
        """Get all tools for a runtime domain"""
        stmt = select(Tool).where(Tool.domains.any(domain))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
