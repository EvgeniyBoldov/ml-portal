from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal
from app.models.discovered_tool import DiscoveredTool
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.services.collection_tool_resolver import CollectionToolResolver, VirtualDiscoveredTool


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    canonical_op_slug: str
    raw_tool_slug: str
    scope_kind: Literal["collection", "system"]
    discovered_tool: DiscoveredTool | VirtualDiscoveredTool


class CollectionCapabilityResolver:
    """Resolve the selected provider's active capabilities for a collection."""

    def __init__(self, tool_loader: CollectionToolResolver) -> None:
        self.tool_loader = tool_loader

    async def resolve_for_collection(
        self,
        *,
        collection: Collection,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[CapabilityCandidate]:
        discovered_tools = await self.tool_loader.load_discovered_tools_for_collection(
            collection=collection,
            instance=instance,
            provider=provider,
        )

        resolved: List[CapabilityCandidate] = []
        seen_raw_slugs: set[str] = set()
        for tool in discovered_tools:
            raw_slug = str(getattr(tool, "slug", "") or "").strip()
            if not raw_slug or raw_slug in seen_raw_slugs:
                continue
            seen_raw_slugs.add(raw_slug)
            resolved.append(
                CapabilityCandidate(
                    canonical_op_slug=raw_slug,
                    raw_tool_slug=raw_slug,
                    scope_kind="collection",
                    discovered_tool=tool,
                )
            )
        return resolved


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
