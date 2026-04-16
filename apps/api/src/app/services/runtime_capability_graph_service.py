from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set
from uuid import UUID

from app.agents.operation_router import OperationResolveResult


@dataclass
class CollectionGraphInfo:
    id: str
    slug: str
    name: str
    collection_type: str


class RuntimeCapabilityGraphService:
    """Builds a runtime capability graph from resolved operations."""

    def build(
        self,
        *,
        resolved: OperationResolveResult,
        agents: Iterable[Any],
        collections: Dict[str, CollectionGraphInfo],
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_ids: Set[str] = set()
        edge_ids: Set[str] = set()

        data_by_slug = {item.slug: item for item in resolved.resolved_data_instances}
        data_by_id = {item.instance_id: item for item in resolved.resolved_data_instances}
        operations_by_slug = {item.operation_slug: item for item in resolved.resolved_operations}

        def add_node(node_id: str, node_type: str, label: str, meta: Dict[str, Any]) -> None:
            if node_id in node_ids:
                return
            node_ids.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": label,
                    "meta": meta,
                }
            )

        def add_edge(src: str, dst: str, edge_type: str, meta: Optional[Dict[str, Any]] = None) -> None:
            edge_id = f"{src}->{dst}:{edge_type}"
            if edge_id in edge_ids:
                return
            edge_ids.add(edge_id)
            edges.append(
                {
                    "id": edge_id,
                    "from": src,
                    "to": dst,
                    "type": edge_type,
                    "meta": meta or {},
                }
            )

        for data in resolved.resolved_data_instances:
            data_node_id = f"data:{data.slug}"
            add_node(
                data_node_id,
                "data_instance",
                data.name,
                {
                    "slug": data.slug,
                    "instance_id": data.instance_id,
                    "domain": data.domain,
                    "placement": data.placement,
                    "provider_instance_slug": data.provider_instance_slug,
                    "collection_id": data.collection_id,
                    "collection_slug": data.collection_slug,
                },
            )

            collection_info = self._resolve_collection_info(data, collections)
            if collection_info is not None:
                collection_node_id = f"collection:{collection_info.slug}"
                add_node(
                    collection_node_id,
                    "collection",
                    collection_info.name,
                    {
                        "id": collection_info.id,
                        "slug": collection_info.slug,
                        "collection_type": collection_info.collection_type,
                    },
                )
                add_edge(data_node_id, collection_node_id, "bound_to_collection")

            if data.provider_instance_slug:
                provider_node_id = f"provider:{data.provider_instance_slug}"
                add_node(
                    provider_node_id,
                    "provider_instance",
                    data.provider_instance_slug,
                    {
                        "provider_instance_id": data.provider_instance_id,
                        "provider_instance_slug": data.provider_instance_slug,
                    },
                )
                add_edge(data_node_id, provider_node_id, "accessed_via_provider")

        for op in resolved.resolved_operations:
            op_node_id = f"operation:{op.operation_slug}"
            add_node(
                op_node_id,
                "operation",
                op.name,
                {
                    "operation_slug": op.operation_slug,
                    "operation": op.operation,
                    "source": op.source,
                    "risk_level": op.risk_level,
                    "side_effects": op.side_effects,
                    "requires_confirmation": op.requires_confirmation,
                    "data_instance_slug": op.data_instance_slug,
                    "provider_instance_slug": op.provider_instance_slug,
                },
            )
            add_edge(op_node_id, f"data:{op.data_instance_slug}", "targets_data_instance")
            if op.provider_instance_slug:
                add_edge(op_node_id, f"provider:{op.provider_instance_slug}", "executes_via_provider")

        for agent in agents:
            if not getattr(agent, "current_version_id", None):
                continue
            agent_slug = str(getattr(agent, "slug", "") or "").strip()
            if not agent_slug:
                continue
            agent_node_id = f"agent:{agent_slug}"
            add_node(
                agent_node_id,
                "agent",
                str(getattr(agent, "name", "") or agent_slug),
                {
                    "slug": agent_slug,
                    "allowed_collection_ids": [
                        str(value) for value in (getattr(agent, "allowed_collection_ids", None) or [])
                    ],
                },
            )
            allowed_collection_ids = self._normalize_uuid_set(getattr(agent, "allowed_collection_ids", None))
            for operation_slug, operation in operations_by_slug.items():
                data = data_by_slug.get(operation.data_instance_slug)
                if data is None:
                    data = data_by_id.get(operation.data_instance_id)
                if data is None:
                    continue
                if not self._agent_allows_data_instance(data, allowed_collection_ids):
                    continue
                add_edge(agent_node_id, f"operation:{operation_slug}", "can_call")

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "agents": len([node for node in nodes if node["type"] == "agent"]),
                "operations": len([node for node in nodes if node["type"] == "operation"]),
                "data_instances": len([node for node in nodes if node["type"] == "data_instance"]),
                "providers": len([node for node in nodes if node["type"] == "provider_instance"]),
                "collections": len([node for node in nodes if node["type"] == "collection"]),
            },
            "missing": {
                "tools": list(resolved.missing.tools),
                "collections": list(resolved.missing.collections),
                "credentials": list(resolved.missing.credentials),
            },
        }

    @staticmethod
    def _normalize_uuid_set(values: Optional[Iterable[Any]]) -> Set[str]:
        normalized: Set[str] = set()
        for value in values or []:
            if isinstance(value, UUID):
                normalized.add(str(value))
            else:
                text = str(value or "").strip()
                if text:
                    normalized.add(text)
        return normalized

    @staticmethod
    def _agent_allows_data_instance(data: Any, allowed_collection_ids: Set[str]) -> bool:
        if not allowed_collection_ids:
            return True
        collection_id = str(getattr(data, "collection_id", "") or "").strip()
        return bool(collection_id and collection_id in allowed_collection_ids)

    @staticmethod
    def _resolve_collection_info(
        data: Any,
        collections: Dict[str, CollectionGraphInfo],
    ) -> Optional[CollectionGraphInfo]:
        collection_id = str(getattr(data, "collection_id", "") or "").strip()
        collection_slug = str(getattr(data, "collection_slug", "") or "").strip()
        if collection_id and collection_id in collections:
            return collections[collection_id]
        if collection_slug and collection_slug in collections:
            return collections[collection_slug]
        return None
