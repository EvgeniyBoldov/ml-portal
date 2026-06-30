from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional

from app.agents.operation_publication import (
    CollectionCapabilityBinding,
    get_collection_capability_bindings,
    get_operation_spec,
    is_operation_allowed_for_collection_type,
)
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.collection_tool_resolver import CollectionToolResolver, VirtualDiscoveredTool


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    canonical_op_slug: str
    raw_tool_slug: str
    scope_kind: Literal["collection", "system"]
    discovered_tool: DiscoveredTool | VirtualDiscoveredTool


class CollectionCapabilityResolver:
    """Resolve collection-bound capabilities from canonical registry + available bindings."""

    def __init__(self, tool_loader: CollectionToolResolver) -> None:
        self.tool_loader = tool_loader

    async def resolve_for_instance(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[CapabilityCandidate]:
        context = await self.tool_loader._build_context(instance=instance, provider=provider)
        discovered_tools = await self.tool_loader.load_discovered_tools(
            instance=instance,
            provider=provider,
        )

        collection_type = str(getattr(context.bound_collection, "collection_type", "") or "").strip().lower()
        if not collection_type:
            return []

        discovered_index = self._index_by_slug(discovered_tools)
        resolved: List[CapabilityCandidate] = []
        seen_canonical: set[str] = set()
        for binding in get_collection_capability_bindings(collection_type):
            if binding.canonical_op_slug in seen_canonical:
                continue
            spec = get_operation_spec(binding.canonical_op_slug)
            if spec is None:
                continue
            publication = spec.to_publication_decision()
            if not is_operation_allowed_for_collection_type(
                publication,
                collection_type=collection_type,
            ):
                continue
            if spec.requires_vector_search and not bool(getattr(context.bound_collection, "has_vector_search", False)):
                continue
            candidate = self._match_binding(binding, discovered_index)
            if candidate is None:
                continue
            seen_canonical.add(binding.canonical_op_slug)
            resolved.append(candidate)
        return resolved

    @staticmethod
    def _index_by_slug(
        discovered_tools: Iterable[DiscoveredTool | VirtualDiscoveredTool],
    ) -> dict[str, List[DiscoveredTool | VirtualDiscoveredTool]]:
        index: dict[str, List[DiscoveredTool | VirtualDiscoveredTool]] = {}
        for tool in discovered_tools:
            slug = str(getattr(tool, "slug", "") or "").strip()
            if not slug:
                continue
            index.setdefault(slug, []).append(tool)
        return index

    @staticmethod
    def _match_binding(
        binding: CollectionCapabilityBinding,
        discovered_index: dict[str, List[DiscoveredTool | VirtualDiscoveredTool]],
    ) -> Optional[CapabilityCandidate]:
        for raw_slug in binding.raw_tool_slugs:
            matches = discovered_index.get(raw_slug) or []
            for tool in matches:
                source = str(getattr(tool, "source", "") or "").strip()
                if binding.source != "any" and source != binding.source:
                    continue
                return CapabilityCandidate(
                    canonical_op_slug=binding.canonical_op_slug,
                    raw_tool_slug=raw_slug,
                    scope_kind="collection",
                    discovered_tool=tool,
                )
        return None


class SystemCapabilityResolver:
    """Resolve global system capabilities independently from collection surfaces."""

    def __init__(self, tool_loader: CollectionToolResolver) -> None:
        self.tool_loader = tool_loader

    async def resolve(self) -> List[CapabilityCandidate]:
        discovered_tools = await self.tool_loader._load_system_tools()
        resolved: List[CapabilityCandidate] = []
        for tool in discovered_tools:
            resolved.append(
                CapabilityCandidate(
                    canonical_op_slug=str(getattr(tool, "slug", "") or "").strip(),
                    raw_tool_slug=str(getattr(tool, "slug", "") or "").strip(),
                    scope_kind="system",
                    discovered_tool=tool,
                )
            )
        return resolved
