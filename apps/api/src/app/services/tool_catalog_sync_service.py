"""
ToolCatalogSyncService — синхронизация канонических tool containers из кода в БД.

Отвечает только за registry tools:
- ToolHandler -> Tool
- domains/name/slug

Schemas и backend releases синхронизируются отдельным сервисом.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.handlers.base import ToolHandler
from app.agents.registry import ToolRegistry
from app.core.logging import get_logger
from app.models.tool import Tool

logger = get_logger(__name__)


class ToolCatalogSyncService:
    """Sync canonical tool registry containers from runtime code into DB."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def sync_tools(self) -> dict:
        """Sync all runtime registry tools into the `tools` table."""
        stats = {"created": 0, "updated": 0}

        handlers = ToolRegistry.list_all()
        logger.info("Syncing %s tools from registry to DB", len(handlers))

        for handler in handlers:
            tool = await self._get_tool_by_slug(handler.slug)
            domains = self._resolve_domains(handler)

            if tool is None:
                await self._create_tool(handler, domains)
                stats["created"] += 1
                logger.info("Created tool: %s", handler.slug)
            else:
                updated = await self._update_tool(tool, handler, domains)
                if updated:
                    stats["updated"] += 1
                    logger.info("Updated tool: %s", handler.slug)

        await self.session.commit()

        logger.info(
            "Tool catalog sync complete: %s created, %s updated",
            stats["created"],
            stats["updated"],
        )
        return stats

    async def _get_tool_by_slug(self, slug: str) -> Tool | None:
        stmt = select(Tool).where(Tool.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_tool(self, handler: ToolHandler, domains: list[str]) -> Tool:
        tool = Tool(
            slug=handler.slug,
            name=handler.name,
            domains=domains,
            kind="read",
        )
        self.session.add(tool)
        await self.session.flush()
        return tool

    async def _update_tool(self, tool: Tool, handler: ToolHandler, domains: list[str]) -> bool:
        updated = False

        if tool.name != handler.name:
            tool.name = handler.name
            updated = True

        if tool.domains != domains:
            tool.domains = domains
            updated = True

        if updated:
            self.session.add(tool)
            await self.session.flush()

        return updated

    def _resolve_domains(self, handler: ToolHandler) -> List[str]:
        raw_domains = getattr(handler, "domains", None) or []
        domains: List[str] = []
        for domain in raw_domains:
            value = str(domain).strip()
            if value and value not in domains:
                domains.append(value)

        if domains:
            return domains

        slug = str(getattr(handler, "slug", "") or "").strip()
        if slug:
            prefix = slug.split(".", 1)[0].strip()
            if prefix:
                return [prefix]
        return []


async def sync_tools_from_registry(session: AsyncSession) -> dict:
    service = ToolCatalogSyncService(session)
    return await service.sync_tools()
