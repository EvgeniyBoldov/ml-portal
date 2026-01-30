from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.tool import Tool
from app.repositories.tool_repository import ToolRepository
from app.schemas.tools import ToolCreate, ToolUpdate


class ToolService:
    def __init__(self, session: AsyncSession):
        self.repo = ToolRepository(session)

    async def list_tools(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None,
        tool_group_id: Optional[UUID] = None,
    ) -> Tuple[List[Tool], int]:
        return await self.repo.list_tools(skip, limit, type_filter, tool_group_id)

    async def get_tool(self, identifier: str) -> Tool:
        """Get tool by ID or slug"""
        tool = None
        try:
            # Try as UUID
            uuid_obj = UUID(identifier)
            tool = await self.repo.get_by_id(uuid_obj)
        except ValueError:
            pass
            
        if not tool:
            # Try as slug
            tool = await self.repo.get_by_slug(identifier)
            
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{identifier}' not found")
            
        return tool

    async def create_tool(self, data: ToolCreate) -> Tool:
        # Check slug uniqueness
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise HTTPException(status_code=400, detail=f"Tool with slug '{data.slug}' already exists")
            
        tool = Tool(**data.model_dump())
        return await self.repo.create(tool)

    async def update_tool(self, identifier: str, data: ToolUpdate) -> Tool:
        tool = await self.get_tool(identifier)
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tool, key, value)
            
        return await self.repo.update(tool)

    async def delete_tool(self, identifier: str) -> None:
        tool = await self.get_tool(identifier)
        await self.repo.delete(tool)
