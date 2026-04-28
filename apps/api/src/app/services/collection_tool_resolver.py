"""
Collection-aware runtime tool resolver.

Centralizes discovered-tool loading logic for runtime/admin summaries.
The resolver uses Collection.data_instance_id as single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.models.collection import Collection
from app.services.collection_linking import (
    resolve_bound_collection_by_instance_id,
    runtime_domain_for_collection,
)
from app.services.instance_capabilities import is_mcp_service_instance

_CATALOG_DOMAINS: frozenset[str] = frozenset({
    "collection.table",
    "collection.document",
    "collection.sql",
    "collection.api",
    "sql",
    "api",
})

_LocalToolRule = Tuple[str, Optional[Callable[["CollectionToolResolutionContext"], bool]]]

_LOCAL_TOOL_RULES: Dict[str, _LocalToolRule] = {
    "collection.doc_search": (
        "collection.document",
        lambda ctx: bool(getattr(ctx.bound_collection, "has_vector_search", False)),
    ),
    "collection.text_search": (
        "collection.table",
        lambda ctx: bool(getattr(ctx.bound_collection, "has_vector_search", False)),
    ),
    "collection.search": ("collection.table", None),
    "collection.aggregate": ("collection.table", None),
    "collection.get": ("collection.table", None),
    "collection.catalog": (
        "",
        lambda ctx: bool(ctx.bound_collection) and ctx.runtime_domain in _CATALOG_DOMAINS,
    ),
}


@dataclass(frozen=True)
class CollectionToolResolutionContext:
    instance: ToolInstance
    provider: ToolInstance
    bound_collection: Optional[Collection]
    runtime_domain: str
    provider_kind: str  # "mcp" | "local"
    is_service_instance: bool


class CollectionToolResolver:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_discovered_tools(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[DiscoveredTool]:
        context = await self._build_context(instance=instance, provider=provider)
        tools = await self._load_tools_for_context(
            context=context,
        )
        deduped = self._dedupe_tools(tools)
        if context.is_service_instance:
            return deduped
        return [
            tool
            for tool in deduped
            if self._is_tool_supported_for_context(
                tool=tool,
                context=context,
            )
        ]

    async def _build_context(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> CollectionToolResolutionContext:
        bound_collection = await self._resolve_bound_collection(instance)
        runtime_domain = runtime_domain_for_collection(
            collection=bound_collection,
            fallback_domain=getattr(instance, "domain", ""),
        )
        provider_kind = "mcp" if self._is_mcp_provider(provider) else "local"
        is_service_instance = bool(getattr(instance, "is_service", False))
        return CollectionToolResolutionContext(
            instance=instance,
            provider=provider,
            bound_collection=bound_collection,
            runtime_domain=runtime_domain,
            provider_kind=provider_kind,
            is_service_instance=is_service_instance,
        )

    async def _load_tools_for_context(
        self,
        *,
        context: CollectionToolResolutionContext,
    ) -> List[DiscoveredTool]:
        tools: List[DiscoveredTool] = []
        if context.provider_kind == "mcp":
            tools.extend(
                await self._load_provider_tools(provider=context.provider)
            )
        else:
            if not context.provider.id:
                return []
            tools.extend(
                await self._load_local_tools_for_provider(provider=context.provider)
            )

        # collection.catalog should be available for any bound collection,
        # regardless of the provider kind.
        if context.bound_collection is not None:
            tools.extend(await self._load_local_collection_catalog_tools())
        return tools

    async def _load_provider_tools(
        self,
        *,
        provider: ToolInstance,
    ) -> List[DiscoveredTool]:
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

    async def _load_local_tools_for_provider(
        self,
        *,
        provider: ToolInstance,
    ) -> List[DiscoveredTool]:
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
        1. persisted instance domain
        """
        domains: List[str] = []
        domain = str(getattr(instance, "domain", "") or "").strip()
        if domain:
            domains.append(domain)
        return domains

    async def _resolve_bound_collection(self, instance: ToolInstance) -> Optional[Collection]:
        if not getattr(instance, "is_data", False):
            return None
        return await resolve_bound_collection_by_instance_id(
            self.session,
            data_instance_id=instance.id,
        )

    @staticmethod
    def _is_tool_supported_for_context(
        *,
        tool: DiscoveredTool,
        context: CollectionToolResolutionContext,
    ) -> bool:
        if tool.source != "local":
            return True
        raw_slug = str(tool.slug or "").strip()
        rule = _LOCAL_TOOL_RULES.get(raw_slug)
        if rule is None:
            return True
        required_domain, capability_check = rule
        if required_domain and context.runtime_domain != required_domain:
            return False
        if capability_check and not capability_check(context):
            return False
        return True
