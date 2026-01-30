"""
ToolGroupService - управление группами инструментов
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool_group import ToolGroup
from app.repositories.tool_group_repository import ToolGroupRepository

logger = get_logger(__name__)


class ToolGroupError(Exception):
    """Base exception for tool group operations"""
    pass


class ToolGroupNotFoundError(ToolGroupError):
    """Tool group not found"""
    pass


class ToolGroupService:
    """Service for managing ToolGroups"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ToolGroupRepository(session)
    
    async def create_group(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> ToolGroup:
        """Create a new tool group"""
        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise ToolGroupError(f"Group with slug '{slug}' already exists")
        
        group = ToolGroup(
            slug=slug,
            name=name,
            description=description,
        )
        
        return await self.repo.create(group)
    
    async def get_group(self, group_id: UUID) -> ToolGroup:
        """Get group by ID"""
        group = await self.repo.get_by_id(group_id)
        if not group:
            raise ToolGroupNotFoundError(f"Group '{group_id}' not found")
        return group
    
    async def get_group_by_slug(self, slug: str) -> ToolGroup:
        """Get group by slug"""
        group = await self.repo.get_by_slug(slug)
        if not group:
            raise ToolGroupNotFoundError(f"Group '{slug}' not found")
        return group
    
    async def update_group(
        self,
        group_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> ToolGroup:
        """Update tool group"""
        group = await self.get_group(group_id)
        
        if name is not None:
            group.name = name
        if description is not None:
            group.description = description
        
        return await self.repo.update(group)
    
    async def delete_group(self, group_id: UUID) -> None:
        """Delete tool group"""
        group = await self.get_group(group_id)
        await self.repo.delete(group)
    
    async def list_groups(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ToolGroup], int]:
        """List tool groups"""
        return await self.repo.list_groups(skip=skip, limit=limit)
