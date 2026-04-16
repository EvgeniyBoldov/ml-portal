"""
Repositories for Tool Releases
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tool import Tool
from app.models.tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus


class ToolBackendReleaseRepository:
    """Repository for ToolBackendRelease (read-only)"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, release_id: UUID) -> Optional[ToolBackendRelease]:
        """Get backend release by ID"""
        stmt = select(ToolBackendRelease).where(ToolBackendRelease.id == release_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_tool_and_version(
        self, 
        tool_id: UUID, 
        version: str
    ) -> Optional[ToolBackendRelease]:
        """Get backend release by tool ID and version"""
        stmt = select(ToolBackendRelease).where(
            ToolBackendRelease.tool_id == tool_id,
            ToolBackendRelease.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_by_tool(self, tool_id: UUID) -> List[ToolBackendRelease]:
        """List all backend releases for a tool"""
        stmt = (
            select(ToolBackendRelease)
            .where(ToolBackendRelease.tool_id == tool_id)
            .order_by(ToolBackendRelease.synced_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_latest(self, tool_id: UUID) -> Optional[ToolBackendRelease]:
        """Get latest backend release for a tool"""
        stmt = (
            select(ToolBackendRelease)
            .where(ToolBackendRelease.tool_id == tool_id)
            .order_by(ToolBackendRelease.synced_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ToolReleaseRepository:
    """Repository for ToolRelease"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, release_id: UUID) -> Optional[ToolRelease]:
        """Get release by ID with backend_release loaded"""
        stmt = (
            select(ToolRelease)
            .options(selectinload(ToolRelease.backend_release))
            .where(ToolRelease.id == release_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_tool_and_version(
        self, 
        tool_id: UUID, 
        version: int
    ) -> Optional[ToolRelease]:
        """Get release by tool ID and version"""
        stmt = (
            select(ToolRelease)
            .options(selectinload(ToolRelease.backend_release))
            .where(
                ToolRelease.tool_id == tool_id,
                ToolRelease.version == version
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_by_tool(self, tool_id: UUID) -> List[ToolRelease]:
        """List all releases for a tool"""
        stmt = (
            select(ToolRelease)
            .options(selectinload(ToolRelease.backend_release))
            .where(ToolRelease.tool_id == tool_id)
            .order_by(ToolRelease.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_active(self, tool_id: UUID) -> Optional[ToolRelease]:
        """Get active release for a tool"""
        stmt = (
            select(ToolRelease)
            .options(selectinload(ToolRelease.backend_release))
            .where(
                ToolRelease.tool_id == tool_id,
                ToolRelease.status == ToolReleaseStatus.ACTIVE.value
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_next_version(self, tool_id: UUID) -> int:
        """Get next version number for a tool"""
        stmt = (
            select(func.coalesce(func.max(ToolRelease.version), 0))
            .where(ToolRelease.tool_id == tool_id)
        )
        result = await self.session.execute(stmt)
        max_version = result.scalar()
        return max_version + 1
    
    async def create(self, release: ToolRelease) -> ToolRelease:
        """Create a new release"""
        self.session.add(release)
        await self.session.flush()
        return release
    
    async def update(self, release: ToolRelease) -> ToolRelease:
        """Update a release"""
        self.session.add(release)
        await self.session.flush()
        return release


class ToolWithReleasesRepository:
    """Repository for Tool with releases"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_slug(self, slug: str) -> Optional[Tool]:
        """Get tool by slug with all releases loaded"""
        stmt = (
            select(Tool)
            .options(
                selectinload(Tool.backend_releases),
                selectinload(Tool.releases).selectinload(ToolRelease.backend_release),
                selectinload(Tool.current_version).selectinload(ToolRelease.backend_release),
            )
            .where(Tool.slug == slug)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_id(self, tool_id: UUID) -> Optional[Tool]:
        """Get tool by ID with all releases loaded"""
        stmt = (
            select(Tool)
            .options(
                selectinload(Tool.backend_releases),
                selectinload(Tool.releases).selectinload(ToolRelease.backend_release),
                selectinload(Tool.current_version).selectinload(ToolRelease.backend_release),
            )
            .where(Tool.id == tool_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_by_domain(self, domain: str) -> List[Tool]:
        """List all tools in a runtime domain"""
        stmt = (
            select(Tool)
            .options(
                selectinload(Tool.backend_releases),
                selectinload(Tool.releases),
            )
            .where(Tool.domains.any(domain))
            .order_by(Tool.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def update(self, tool: Tool) -> Tool:
        """Update a tool"""
        self.session.add(tool)
        await self.session.flush()
        return tool
