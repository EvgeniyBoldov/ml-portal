"""
ToolService v2 - strictly UUID-based.
"""
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tool import Tool
from app.core.exceptions import ToolNotFoundError, AlreadyExistsError
from app.repositories.tool_repository import ToolRepository
from app.schemas.tools import ToolCreate, ToolUpdate


class ToolService:
    def __init__(self, session: AsyncSession):
        self.repo = ToolRepository(session)

    async def list_tools(
        self,
        skip: int = 0,
        limit: int = 100,
        domain: Optional[str] = None,
    ) -> Tuple[List[Tool], int]:
        return await self.repo.list_tools(skip, limit, domain=domain)

    async def get_tool(self, tool_id: UUID) -> Tool:
        """Get tool by UUID (strict)."""
        tool = await self.repo.get_by_id(tool_id)
        if not tool:
            raise ToolNotFoundError(f"Tool '{tool_id}' not found")
        return tool

    async def get_tool_by_slug(self, slug: str) -> Tool:
        """Get tool by slug (for runtime/internal use only)."""
        tool = await self.repo.get_by_slug(slug)
        if not tool:
            raise ToolNotFoundError(f"Tool '{slug}' not found")
        return tool

    async def create_tool(self, data: ToolCreate) -> Tool:
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise AlreadyExistsError(f"Tool with slug '{data.slug}' already exists")

        tool = Tool(**data.model_dump())
        return await self.repo.create(tool)

    async def update_tool(self, tool_id: UUID, data: ToolUpdate) -> Tool:
        tool = await self.get_tool(tool_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tool, key, value)

        return await self.repo.update(tool)

    async def delete_tool(self, tool_id: UUID) -> None:
        tool = await self.get_tool(tool_id)
        await self.repo.delete(tool)
