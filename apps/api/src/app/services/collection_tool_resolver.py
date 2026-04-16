"""
Collection-aware runtime tool resolver.

Centralizes discovered-tool loading logic for runtime/admin summaries.
The resolver prefers explicit collection binding metadata over instance domain.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.models.collection import Collection
from app.services.collection_binding import resolve_bound_collection
from app.services.collection_binding import resolve_collection_runtime_domain
from app.services.instance_capabilities import is_mcp_service_instance


class CollectionToolResolver:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_discovered_tools(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
        include_unpublished: bool = False,
    ) -> List[DiscoveredTool]:
        _ = include_unpublished
        bound_collection = await self._resolve_bound_collection(instance)
        if self._is_mcp_provider(provider):
            mcp_tools = await self._load_provider_tools(provider)
            local_catalog_tools = await self._load_local_collection_catalog_tools()
            tools = self._dedupe_tools([*mcp_tools, *local_catalog_tools])
        else:
            if not provider.id:
                return []
            tools = await self._load_local_tools_for_provider(provider)

        if str(getattr(instance, "instance_kind", "") or "").strip().lower() == "service":
            return tools

        return [
            tool for tool in tools
            if self._is_tool_supported_for_instance(
                tool=tool,
                instance=instance,
                bound_collection=bound_collection,
            )
        ]

    async def _load_provider_tools(self, provider: ToolInstance) -> List[DiscoveredTool]:
        stmt = (
            select(DiscoveredTool)
            .options(selectinload(DiscoveredTool.tool))
            .where(
                DiscoveredTool.is_active.is_(True),
                DiscoveredTool.source == "mcp",
                DiscoveredTool.provider_instance_id == provider.id,
            )
            .order_by(DiscoveredTool.slug)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_local_tools_for_provider(self, provider: ToolInstance) -> List[DiscoveredTool]:
        stmt = (
            select(DiscoveredTool)
            .options(selectinload(DiscoveredTool.tool))
            .where(
                DiscoveredTool.is_active.is_(True),
                DiscoveredTool.source == "local",
                DiscoveredTool.provider_instance_id == provider.id,
            )
            .order_by(DiscoveredTool.slug)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_local_collection_catalog_tools(self) -> List[DiscoveredTool]:
        stmt = (
            select(DiscoveredTool)
            .options(selectinload(DiscoveredTool.tool))
            .where(
                DiscoveredTool.is_active.is_(True),
                DiscoveredTool.source == "local",
                DiscoveredTool.slug == "collection.catalog",
            )
            .order_by(DiscoveredTool.provider_instance_id, DiscoveredTool.slug)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _dedupe_tools(tools: List[DiscoveredTool]) -> List[DiscoveredTool]:
        seen: set[tuple[str, str]] = set()
        deduped: List[DiscoveredTool] = []
        for tool in tools:
            key = (str(tool.source or ""), str(tool.slug or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(tool)
        return deduped

    @staticmethod
    def _is_mcp_provider(provider: ToolInstance) -> bool:
        return is_mcp_service_instance(provider)

    @staticmethod
    def _resolve_local_domains(instance: ToolInstance) -> List[str]:
        """
        Build ordered local runtime domains for compatibility filtering.

        Priority:
        1. explicit collection-bound runtime domain from config
        2. persisted instance domain
        """
        domains: List[str] = []
        resolved = resolve_collection_runtime_domain(
            getattr(instance, "config", None),
            getattr(instance, "domain", ""),
        )
        fallback = str(getattr(instance, "domain", "") or "").strip()

        for candidate in (resolved, fallback):
            candidate = str(candidate or "").strip()
            if candidate and candidate not in domains:
                domains.append(candidate)
        return domains

    async def _resolve_bound_collection(self, instance: ToolInstance) -> Optional[Collection]:
        return await resolve_bound_collection(self.session, getattr(instance, "config", None))

    @staticmethod
    def _is_tool_supported_for_instance(
        *,
        tool: DiscoveredTool,
        instance: ToolInstance,
        bound_collection: Optional[Collection],
    ) -> bool:
        if tool.source != "local":
            return True

        raw_slug = str(tool.slug or "").strip()
        runtime_domain = resolve_collection_runtime_domain(
            getattr(instance, "config", None),
            getattr(instance, "domain", ""),
        )

        if raw_slug == "collection.doc_search":
            return runtime_domain == "collection.document" and bool(
                getattr(bound_collection, "has_vector_search", False)
            )

        if raw_slug == "collection.text_search":
            return runtime_domain == "collection.table" and bool(
                getattr(bound_collection, "has_vector_search", False)
            )

        if raw_slug in {"collection.search", "collection.aggregate", "collection.get"}:
            return runtime_domain == "collection.table"

        if raw_slug == "collection.catalog":
            return bool(bound_collection) and runtime_domain in {
                "collection.table",
                "collection.document",
                "collection.sql",
                "collection.api",
                "sql",
                "api",
            }

        return True
