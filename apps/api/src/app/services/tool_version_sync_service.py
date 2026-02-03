"""
ToolVersionSyncService - синхронизация версий VersionedTool из кода в БД

При старте воркера:
- Сканирует все классы VersionedTool
- Извлекает версии из методов с @tool_version
- Создаёт/обновляет записи в tool_backend_releases
"""
from typing import List, Set, Dict, Optional
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.tool import Tool
from app.models.tool_group import ToolGroup
from app.models.tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from app.agents.handlers.versioned_tool import VersionedTool, ToolVersionInfo, tool_registry

logger = get_logger(__name__)


class ToolVersionSyncService:
    """
    Сервис для синхронизации версий инструментов из кода в БД.
    
    Вызывается при старте воркера для обеспечения консистентности
    между кодом (VersionedTool) и базой данных (ToolBackendRelease).
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def sync_all(self) -> dict:
        """
        Синхронизировать все версии из ToolRegistry в БД.
        
        Returns:
            Dict with sync statistics
        """
        stats = {
            "tools_synced": 0,
            "backend_releases_created": 0,
            "backend_releases_updated": 0,
            "groups_created": 0,
        }
        
        tools = tool_registry.get_all()
        logger.info(f"Syncing {len(tools)} versioned tools from registry")
        
        if not tools:
            logger.info("No versioned tools found in registry")
            return stats
        
        # First, sync tool groups
        group_slugs: Set[str] = {t.tool_group for t in tools}
        group_id_map = await self._sync_tool_groups(group_slugs)
        stats["groups_created"] = len(group_id_map) - len(await self._get_existing_group_slugs())
        
        # Sync each tool and its versions
        for versioned_tool in tools:
            tool = await self._ensure_tool_exists(versioned_tool, group_id_map)
            
            versions = versioned_tool.get_versions()
            for version_info in versions:
                created = await self._sync_backend_release(tool, version_info)
                if created:
                    stats["backend_releases_created"] += 1
                else:
                    stats["backend_releases_updated"] += 1
            
            stats["tools_synced"] += 1
        
        await self.session.commit()
        
        logger.info(
            f"Tool version sync complete: {stats['tools_synced']} tools, "
            f"{stats['backend_releases_created']} releases created, "
            f"{stats['backend_releases_updated']} releases updated"
        )
        
        return stats
    
    async def _get_existing_group_slugs(self) -> Set[str]:
        """Get all existing group slugs"""
        stmt = select(ToolGroup.slug)
        result = await self.session.execute(stmt)
        return set(result.scalars().all())
    
    async def _sync_tool_groups(self, group_slugs: Set[str]) -> Dict[str, UUID]:
        """
        Sync tool groups - create if not exists.
        Returns mapping of slug -> id
        """
        group_id_map: Dict[str, UUID] = {}
        
        for slug in group_slugs:
            stmt = select(ToolGroup).where(ToolGroup.slug == slug)
            result = await self.session.execute(stmt)
            group = result.scalar_one_or_none()
            
            if group is None:
                group = ToolGroup(
                    slug=slug,
                    name=slug.capitalize(),
                    description=f"Tools for {slug} integration",
                )
                self.session.add(group)
                await self.session.flush()
                logger.info(f"Created tool group: {slug}")
            
            group_id_map[slug] = group.id
        
        return group_id_map
    
    async def _ensure_tool_exists(
        self, 
        versioned_tool: VersionedTool, 
        group_id_map: Dict[str, UUID]
    ) -> Tool:
        """
        Ensure tool exists in DB, create if not.
        """
        stmt = select(Tool).where(Tool.slug == versioned_tool.tool_slug)
        result = await self.session.execute(stmt)
        tool = result.scalar_one_or_none()
        
        group_id = group_id_map.get(versioned_tool.tool_group)
        
        if tool is None:
            # Get latest version for initial schema
            latest = versioned_tool.get_latest_version()
            
            tool = Tool(
                slug=versioned_tool.tool_slug,
                name=versioned_tool.name,
                description=versioned_tool.description,
                type="builtin",
                tool_group_id=group_id,
                input_schema=latest.input_schema if latest else {},
                output_schema=latest.output_schema if latest else None,
                is_active=True,
            )
            self.session.add(tool)
            await self.session.flush()
            logger.info(f"Created tool: {versioned_tool.tool_slug}")
        else:
            # Update tool metadata if changed
            updated = False
            if tool.name != versioned_tool.name:
                tool.name = versioned_tool.name
                updated = True
            if tool.description != versioned_tool.description:
                tool.description = versioned_tool.description
                updated = True
            if tool.tool_group_id != group_id:
                tool.tool_group_id = group_id
                updated = True
            if not tool.is_active:
                tool.is_active = True
                updated = True
            
            if updated:
                self.session.add(tool)
                await self.session.flush()
                logger.info(f"Updated tool: {versioned_tool.tool_slug}")
        
        return tool
    
    async def _sync_backend_release(
        self, 
        tool: Tool, 
        version_info: ToolVersionInfo
    ) -> bool:
        """
        Sync a single backend release.
        Returns True if created, False if updated.
        """
        stmt = select(ToolBackendRelease).where(
            ToolBackendRelease.tool_id == tool.id,
            ToolBackendRelease.version == version_info.version
        )
        result = await self.session.execute(stmt)
        release = result.scalar_one_or_none()
        
        if release is None:
            # Create new backend release
            release = ToolBackendRelease(
                tool_id=tool.id,
                version=version_info.version,
                input_schema=version_info.input_schema,
                output_schema=version_info.output_schema,
                description=version_info.description,
                method_name=version_info.method_name,
                deprecated=version_info.deprecated,
                deprecation_message=version_info.deprecation_message,
                synced_at=datetime.now(timezone.utc),
            )
            self.session.add(release)
            await self.session.flush()
            logger.info(f"Created backend release: {tool.slug}@{version_info.version}")
            return True
        else:
            # Update existing release if changed
            updated = False
            
            if release.input_schema != version_info.input_schema:
                release.input_schema = version_info.input_schema
                updated = True
            if release.output_schema != version_info.output_schema:
                release.output_schema = version_info.output_schema
                updated = True
            if release.description != version_info.description:
                release.description = version_info.description
                updated = True
            if release.method_name != version_info.method_name:
                release.method_name = version_info.method_name
                updated = True
            if release.deprecated != version_info.deprecated:
                release.deprecated = version_info.deprecated
                updated = True
            if release.deprecation_message != version_info.deprecation_message:
                release.deprecation_message = version_info.deprecation_message
                updated = True
            
            if updated:
                release.synced_at = datetime.now(timezone.utc)
                self.session.add(release)
                await self.session.flush()
                logger.info(f"Updated backend release: {tool.slug}@{version_info.version}")
            
            return False


async def sync_tool_versions(session: AsyncSession) -> dict:
    """
    Convenience function to sync tool versions.
    
    Usage in worker startup:
        async with get_session() as session:
            await sync_tool_versions(session)
    """
    service = ToolVersionSyncService(session)
    return await service.sync_all()
