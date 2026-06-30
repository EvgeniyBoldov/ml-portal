"""
Collection-aware runtime tool resolver.

Centralizes discovered-tool loading logic for runtime/admin summaries.
The resolver uses Collection.data_instance_id as single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.registry import ToolRegistry
from app.agents.operation_publication import (
    is_operation_allowed_for_collection_type,
    resolve_publication,
)
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.models.collection import Collection
from app.services.collection_linking import (
    resolve_bound_collection_by_instance_id,
    runtime_domain_for_collection,
)
from app.services.instance_capabilities import is_mcp_service_instance

@dataclass(frozen=True)
class CollectionToolResolutionContext:
    instance: ToolInstance
    provider: ToolInstance
    bound_collection: Optional[Collection]
    runtime_domain: str
    provider_kind: str  # "mcp" | "local"
    is_service_instance: bool


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

    async def load_discovered_tools(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[DiscoveredTool | VirtualDiscoveredTool]:
        context = await self._build_context(instance=instance, provider=provider)
        tools = await self._load_tools_for_context(
            context=context,
        )
        tools.extend(self._load_builtin_collection_tools(context=context))
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
        return is_mcp_service_instance(provider)

    @staticmethod
    def _is_current_system_handler(tool: DiscoveredTool) -> bool:
        handler = ToolRegistry.get(str(getattr(tool, "slug", "") or "").strip())
        if handler is None:
            return "system" in (list(getattr(tool, "domains", None) or []))
        return "system" in (list(getattr(handler, "domains", None) or []))

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
        return await resolve_bound_collection_by_instance_id(
            self.session,
            data_instance_id=instance.id,
        )

    @staticmethod
    def _load_builtin_collection_tools(
        *,
        context: CollectionToolResolutionContext,
    ) -> List[VirtualDiscoveredTool]:
        collection = context.bound_collection
        if collection is None:
            return []

        collection_type = str(getattr(collection, "collection_type", "") or "").strip().lower()
        context_domains = [context.runtime_domain] if context.runtime_domain else None
        tools: List[VirtualDiscoveredTool] = []
        for handler in ToolRegistry.list_all():
            domains = list(getattr(handler, "domains", None) or [])
            if context.runtime_domain and context.runtime_domain not in domains:
                continue
            publication = resolve_publication(
                raw_slug=str(getattr(handler, "slug", "") or "").strip(),
                discovered_domains=domains,
                context_domains=context_domains,
            )
            if publication is None or publication.scope_kind != "collection":
                continue
            if not is_operation_allowed_for_collection_type(
                publication,
                collection_type=collection_type,
            ):
                continue
            if publication.spec.requires_vector_search and not bool(
                getattr(collection, "has_vector_search", False)
            ):
                continue
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
        if tool.source != "local":
            return True
        publication = resolve_publication(
            raw_slug=str(tool.slug or "").strip(),
            discovered_domains=getattr(tool, "domains", None) or [],
            context_domains=[context.runtime_domain] if context.runtime_domain else None,
        )
        if publication is None:
            return False
        if publication.scope_kind == "system":
            return True
        if not is_operation_allowed_for_collection_type(
            publication,
            collection_type=getattr(context.bound_collection, "collection_type", None),
        ):
            return False
        if publication.spec.requires_vector_search and not bool(
            getattr(context.bound_collection, "has_vector_search", False)
        ):
            return False
        return True
