"""Base primitives for collection-derived semantic profiles."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.collection import Collection
from app.models.tool_instance import ToolInstance


@dataclass(slots=True)
class ResolvedCollection:
    id: str
    summary: Optional[str] = None
    entity_types: List[str] = field(default_factory=list)
    use_cases: Optional[str] = None
    limitations: Optional[str] = None
    policy_hints: Optional[Dict[str, Any]] = None
    schema_hints: Optional[Dict[str, Any]] = None
    examples: Optional[Any] = None
    semantic_source: Optional[str] = None

    def to_prompt_context(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "entity_types": list(self.entity_types),
            "use_cases": self.use_cases,
            "limitations": self.limitations,
            "policy_hints": self.policy_hints or {},
            "schema_hints": self.schema_hints or {},
            "examples": self.examples,
            "semantic_source": self.semantic_source,
        }


class BaseCollectionTypeResolver:
    """Per-collection-type semantic resolver."""

    collection_type: str = ""

    def supports(self, collection: Collection) -> bool:
        return str(collection.collection_type or "").strip().lower() == self.collection_type

    def build(self, instance: ToolInstance, collection: Collection) -> ResolvedCollection:
        raise NotImplementedError

    @staticmethod
    def semantic_bundle(collection: Collection) -> tuple[dict[str, Any], dict[str, Any], Any]:
        current_version = collection.current_version
        semantic_profile = (
            (getattr(current_version, "semantic_profile", None) or {})
            if current_version
            else {}
        )
        policy_hints = (
            (getattr(current_version, "policy_hints", None) or {})
            if current_version
            else {}
        )
        semantic_version = getattr(current_version, "version", None) if current_version else None
        return semantic_profile, policy_hints, semantic_version

    @staticmethod
    def profile_id(collection: Collection) -> str:
        current_version = collection.current_version
        if current_version:
            return f"collection:{collection.id}:v{current_version.version}"
        return f"derived:{collection.id}"

    @staticmethod
    def semantic_source(collection: Collection) -> str:
        return "active_profile" if collection.current_version else "derived_collection"

    @staticmethod
    def transport_profile(instance: ToolInstance) -> Dict[str, Any]:
        config = instance.config or {}
        provider_kind = str(config.get("provider_kind") or "").strip().lower() or None
        placement = str(getattr(instance, "placement", "") or "").strip().lower() or "remote"
        access_via_instance_id = getattr(instance, "access_via_instance_id", None)
        if placement == "local":
            transport_kind = "mcp.local"
        else:
            transport_kind = "mcp.remote"
        return {
            "transport_kind": transport_kind,
            "provider_kind": provider_kind,
            "placement": placement,
            "access_via_instance_id": str(access_via_instance_id) if access_via_instance_id else None,
            "runtime_contract": "mcp.tools.call",
        }


def normalize_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def field_hint(field: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": field.get("name"),
        "category": field.get("category"),
        "data_type": field.get("data_type"),
        "required": bool(field.get("required", False)),
        "description": field.get("description"),
    }
