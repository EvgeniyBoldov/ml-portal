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
from app.core.schema_hash import compute_schema_hash
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
    
    def __init__(self, session: AsyncSession, worker_build_id: Optional[str] = None):
        self.session = session
        self.worker_build_id = worker_build_id
    
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
            "schema_changes_detected": 0,
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
                result = await self._sync_backend_release(tool, version_info)
                if result == "created":
                    stats["backend_releases_created"] += 1
                elif result == "schema_changed":
                    stats["schema_changes_detected"] += 1
                    stats["backend_releases_updated"] += 1
                else:
                    stats["backend_releases_updated"] += 1
            
            stats["tools_synced"] += 1
        
        await self.session.commit()
        
        logger.info(
            f"Tool version sync complete: {stats['tools_synced']} tools, "
            f"{stats['backend_releases_created']} releases created, "
            f"{stats['backend_releases_updated']} releases updated, "
            f"{stats['schema_changes_detected']} schema changes detected"
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
    ) -> str:
        """
        Sync a single backend release.
        Returns: "created", "schema_changed", or "updated"
        """
        now = datetime.now(timezone.utc)
        new_hash = compute_schema_hash(
            version_info.input_schema,
            version_info.output_schema,
        )
        
        stmt = select(ToolBackendRelease).where(
            ToolBackendRelease.tool_id == tool.id,
            ToolBackendRelease.version == version_info.version
        )
        result = await self.session.execute(stmt)
        release = result.scalar_one_or_none()
        
        if release is None:
            release = ToolBackendRelease(
                tool_id=tool.id,
                version=version_info.version,
                input_schema=version_info.input_schema,
                output_schema=version_info.output_schema,
                description=version_info.description,
                method_name=version_info.method_name,
                deprecated=version_info.deprecated,
                deprecation_message=version_info.deprecation_message,
                schema_hash=new_hash,
                worker_build_id=self.worker_build_id,
                last_seen_at=now,
                synced_at=now,
            )
            self.session.add(release)
            await self.session.flush()
            logger.info(f"Created backend release: {tool.slug}@{version_info.version} (hash={new_hash[:8]})")
            return "created"
        
        # Detect schema change
        schema_changed = release.schema_hash is not None and release.schema_hash != new_hash
        if schema_changed:
            logger.warning(
                f"Schema change detected for {tool.slug}@{version_info.version}: "
                f"{release.schema_hash[:8]} -> {new_hash[:8]}",
                extra={
                    "tool_slug": tool.slug,
                    "version": version_info.version,
                    "old_hash": release.schema_hash,
                    "new_hash": new_hash,
                    "worker_build_id": self.worker_build_id,
                },
            )
        
        # Update fields
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
        
        # Always update tracking fields
        release.schema_hash = new_hash
        release.worker_build_id = self.worker_build_id
        release.last_seen_at = now
        
        if updated or schema_changed:
            release.synced_at = now
        
        self.session.add(release)
        await self.session.flush()
        
        if updated:
            logger.info(f"Updated backend release: {tool.slug}@{version_info.version}")
        
        return "schema_changed" if schema_changed else "updated"


async def sync_tool_versions(
    session: AsyncSession,
    worker_build_id: Optional[str] = None,
) -> dict:
    """
    Convenience function to sync tool versions.
    
    Usage in worker startup:
        async with get_session() as session:
            await sync_tool_versions(session, worker_build_id=os.getenv("WORKER_BUILD_ID"))
    """
    service = ToolVersionSyncService(session, worker_build_id=worker_build_id)
    return await service.sync_all()
