"""Collection-first discovered-tool resolver.

The caller must supply the target collection.  A shared local provider never
selects a collection implicitly; remote source binding is resolved above this
layer and passed in explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.registry import ToolRegistry
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.models.collection import Collection
from app.services.collection_linking import runtime_domain_for_collection
from app.services.instance_capabilities import is_mcp_service_instance

@dataclass(frozen=True)
class CollectionToolResolutionContext:
    instance: ToolInstance
    provider: ToolInstance
    bound_collection: Optional[Collection]
    runtime_domain: str
    provider_kind: str  # "mcp" | "local"


@dataclass(frozen=True)
class VirtualDiscoveredTool:
    slug: str
    name: str
    description: str
    source: str
    domains: List[str]
    input_schema: dict
    output_schema: Optional[dict]
    is_active: bool = True
    provider_instance_id: Optional[str] = None


class CollectionToolResolver:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_discovered_tools_for_collection(
        self,
        *,
        collection: Collection,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[DiscoveredTool | VirtualDiscoveredTool]:
        """Resolve tools for an explicit collection target.

        A local provider can serve many collections.  Never infer the target
        collection from the provider instance: doing so makes the first bound
        collection silently win for every shared local service.
        """
        runtime_domain = runtime_domain_for_collection(
            collection=collection,
            fallback_domain=getattr(instance, "domain", ""),
        )
        context = CollectionToolResolutionContext(
            instance=instance,
            provider=provider,
            bound_collection=collection,
            runtime_domain=runtime_domain,
            provider_kind="mcp" if self._is_mcp_provider(provider) else "local",
        )
        tools = await self._load_tools_for_context(context=context)
        tools.extend(self._load_builtin_collection_tools(context=context))
        return [
            tool
            for tool in self._dedupe_tools(tools)
            if self._is_tool_supported_for_context(tool=tool, context=context)
        ]

    async def _load_tools_for_context(
        self,
        *,
        context: CollectionToolResolutionContext,
    ) -> List[DiscoveredTool | VirtualDiscoveredTool]:
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

    async def _load_system_tools(self) -> List[DiscoveredTool]:
        """Load global system tools (provider_instance_id=NULL, domain='system')."""
        stmt = (
            select(DiscoveredTool)
            .options(selectinload(DiscoveredTool.tool))
            .where(
                DiscoveredTool.is_active.is_(True),
                DiscoveredTool.source == "local",
                DiscoveredTool.provider_instance_id.is_(None),
                DiscoveredTool.domains.any("system"),
            )
            .order_by(DiscoveredTool.slug)
        )
        result = await self.session.execute(stmt)
        tools = list(result.scalars().all())
        return [
            tool
            for tool in tools
            if self._is_current_system_handler(tool)
        ]

    @staticmethod
    def _dedupe_tools(
        tools: List[DiscoveredTool | VirtualDiscoveredTool],
    ) -> List[DiscoveredTool | VirtualDiscoveredTool]:
        seen: set[tuple[str, str]] = set()
        deduped: List[DiscoveredTool | VirtualDiscoveredTool] = []
        for tool in tools:
            key = (str(tool.source or ""), str(tool.slug or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(tool)
        return deduped

    @staticmethod
    def _is_mcp_provider(provider: ToolInstance) -> bool:
        # Discovery accepts remote MCP services by connector_type. Resolution
        # must use the same execution-provider rule; provider_kind is admin
        # metadata and must not make an already discovered MCP look local.
        if str(getattr(provider, "placement", "") or "").strip().lower() == "local":
            return False
        connector_type = str(getattr(provider, "connector_type", "") or "").strip().lower()
        if connector_type == "mcp":
            return True
        return is_mcp_service_instance(provider)

    @staticmethod
    def _is_current_system_handler(tool: DiscoveredTool) -> bool:
        handler = ToolRegistry.get(str(getattr(tool, "slug", "") or "").strip())
        if handler is None:
            return "system" in (list(getattr(tool, "domains", None) or []))
        return "system" in (list(getattr(handler, "domains", None) or []))

    @staticmethod
    def _load_builtin_collection_tools(
        *,
        context: CollectionToolResolutionContext,
    ) -> List[VirtualDiscoveredTool]:
        collection = context.bound_collection
        if collection is None:
            return []

        tools: List[VirtualDiscoveredTool] = []
        for handler in ToolRegistry.list_all():
            # Platform defaults are explicit collection capabilities, not an
            # inferred allow-list for provider tools. collection.info is the
            # sole default today and is valid for every collection.
            if str(getattr(handler, "slug", "") or "").strip() != "collection.info":
                continue
            domains = list(getattr(handler, "domains", None) or [])
            descriptor = handler.to_mcp_descriptor()
            tools.append(
                VirtualDiscoveredTool(
                    slug=str(getattr(handler, "slug", "") or "").strip(),
                    name=str(getattr(handler, "name", "") or "").strip(),
                    description=str(
                        descriptor.get("description") or getattr(handler, "description", "") or ""
                    ).strip(),
                    source="local",
                    domains=domains,
                    input_schema=dict(descriptor.get("inputSchema") or {}),
                    output_schema=(
                        dict(descriptor.get("outputSchema") or {})
                        if isinstance(descriptor.get("outputSchema"), dict)
                        else None
                    ),
                    provider_instance_id=(
                        str(getattr(context.provider, "id", "") or "").strip() or None
                    ),
                )
            )
        return tools

    @staticmethod
    def _is_tool_supported_for_context(
        *,
        tool: DiscoveredTool | VirtualDiscoveredTool,
        context: CollectionToolResolutionContext,
    ) -> bool:
        # The collection/provider relationship already scopes provider tools.
        # Do not reclassify them by domains or provider-specific raw names.
        return bool(str(getattr(tool, "slug", "") or "").strip())
