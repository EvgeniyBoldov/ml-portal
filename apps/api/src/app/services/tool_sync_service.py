"""
ToolSyncService - синхронизация ToolHandler из кода в БД

При старте приложения:
- Если tool в коде есть, а в БД нет → создать
- Если tool в БД есть, а в коде нет → пометить is_active=false
- Если есть в обоих → обновить name, description, input_schema, output_schema из кода
- ToolGroups создаются автоматически по tool_group из handlers
"""
from typing import List, Set, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.tool import Tool
from app.models.tool_group import ToolGroup
from app.models.permission_set import PermissionSet
from app.agents.registry import ToolRegistry
from app.agents.handlers.base import ToolHandler

logger = get_logger(__name__)


class ToolSyncService:
    """
    Сервис для синхронизации tools из кода (ToolRegistry) в БД.
    
    Вызывается при старте приложения для обеспечения консистентности
    между кодом и базой данных.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def sync_tools(self) -> dict:
        """
        Синхронизировать tools из ToolRegistry в БД.
        
        Returns:
            Dict with sync statistics: created, updated, deactivated, groups_created
        """
        stats = {"created": 0, "updated": 0, "deactivated": 0, "groups_created": 0}
        
        handlers = ToolRegistry.list_all()
        handler_slugs: Set[str] = {h.slug for h in handlers}
        
        logger.info(f"Syncing {len(handlers)} tools from registry to DB")
        
        # First, sync tool groups
        group_slugs: Set[str] = {h.tool_group for h in handlers if hasattr(h, 'tool_group') and h.tool_group}
        group_id_map = await self._sync_tool_groups(group_slugs)
        stats["groups_created"] = len([g for g in group_slugs if g not in await self._get_existing_group_slugs()])
        
        for handler in handlers:
            tool = await self._get_tool_by_slug(handler.slug)
            tool_group_id = group_id_map.get(handler.tool_group) if hasattr(handler, 'tool_group') else None
            
            if tool is None:
                await self._create_tool(handler, tool_group_id)
                stats["created"] += 1
                logger.info(f"Created tool: {handler.slug}")
            else:
                updated = await self._update_tool(tool, handler, tool_group_id)
                if updated:
                    stats["updated"] += 1
                    logger.info(f"Updated tool: {handler.slug}")
        
        db_tools = await self._get_all_tools()
        for tool in db_tools:
            if tool.slug not in handler_slugs and tool.is_active:
                tool.is_active = False
                self.session.add(tool)
                stats["deactivated"] += 1
                logger.warning(f"Deactivated tool (not in registry): {tool.slug}")
        
        await self.session.commit()
        
        logger.info(
            f"Tool sync complete: {stats['created']} created, "
            f"{stats['updated']} updated, {stats['deactivated']} deactivated"
        )
        
        return stats
    
    async def _get_tool_by_slug(self, slug: str) -> Tool | None:
        """Get tool by slug"""
        stmt = select(Tool).where(Tool.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_all_tools(self) -> List[Tool]:
        """Get all tools from DB"""
        stmt = select(Tool)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_existing_group_slugs(self) -> Set[str]:
        """Get all existing group slugs"""
        stmt = select(ToolGroup.slug)
        result = await self.session.execute(stmt)
        return set(result.scalars().all())
    
    async def _sync_tool_groups(self, group_slugs: Set[str]) -> Dict[str, str]:
        """
        Sync tool groups - create if not exists.
        Returns mapping of slug -> id
        """
        group_id_map: Dict[str, str] = {}
        
        for slug in group_slugs:
            stmt = select(ToolGroup).where(ToolGroup.slug == slug)
            result = await self.session.execute(stmt)
            group = result.scalar_one_or_none()
            
            if group is None:
                # Create new group with slug as name (can be edited later)
                group = ToolGroup(
                    slug=slug,
                    name=slug.capitalize(),
                    description=f"Tools for {slug} integration",
                )
                self.session.add(group)
                await self.session.flush()
                logger.info(f"Created tool group: {slug}")
            
            group_id_map[slug] = str(group.id)
        
        return group_id_map
    
    async def _create_tool(self, handler: ToolHandler, tool_group_id: str | None = None) -> Tool:
        """Create new tool from handler"""
        from uuid import UUID
        tool = Tool(
            slug=handler.slug,
            name=handler.name,
            description=handler.description,
            type="builtin",
            tool_group_id=UUID(tool_group_id) if tool_group_id else None,
            input_schema=handler.input_schema,
            output_schema=handler.output_schema,
            is_active=True,
        )
        self.session.add(tool)
        await self.session.flush()
        
        # Auto-add to default permission set
        await self._add_tool_to_default_permissions(handler.slug)
        
        return tool
    
    async def _add_tool_to_default_permissions(self, tool_slug: str):
        """Add new tool to default permission set with 'denied' status"""
        # Get default permission set
        stmt = select(PermissionSet).where(
            PermissionSet.scope == "default",
            PermissionSet.tenant_id.is_(None),
            PermissionSet.user_id.is_(None)
        )
        result = await self.session.execute(stmt)
        default_perms = result.scalar_one_or_none()
        
        if not default_perms:
            logger.warning("Default permission set not found, skipping auto-add")
            return
        
        # Check if tool already in permissions
        tools_permissions = default_perms.tools_permissions or {}
        if tool_slug in tools_permissions:
            return
        
        # Add with 'denied' status by default
        tools_permissions[tool_slug] = "denied"
        default_perms.tools_permissions = tools_permissions
        
        self.session.add(default_perms)
        await self.session.flush()
        
        logger.info(f"Added tool '{tool_slug}' to default permissions (status: denied)")
    
    async def _update_tool(self, tool: Tool, handler: ToolHandler, tool_group_id: str | None = None) -> bool:
        """
        Update tool from handler if changed.
        Returns True if tool was updated.
        """
        from uuid import UUID
        updated = False
        
        if tool.name != handler.name:
            tool.name = handler.name
            updated = True
        
        if tool.description != handler.description:
            tool.description = handler.description
            updated = True
        
        if tool.input_schema != handler.input_schema:
            tool.input_schema = handler.input_schema
            updated = True
        
        if tool.output_schema != handler.output_schema:
            tool.output_schema = handler.output_schema
            updated = True
        
        # Update tool_group_id if changed
        new_group_id = UUID(tool_group_id) if tool_group_id else None
        if tool.tool_group_id != new_group_id:
            tool.tool_group_id = new_group_id
            updated = True
        
        if not tool.is_active:
            tool.is_active = True
            updated = True
        
        if updated:
            self.session.add(tool)
            await self.session.flush()
        
        return updated


async def sync_tools_from_registry(session: AsyncSession) -> dict:
    """
    Convenience function to sync tools.
    
    Usage in startup:
        async with get_session() as session:
            await sync_tools_from_registry(session)
    """
    service = ToolSyncService(session)
    return await service.sync_tools()
