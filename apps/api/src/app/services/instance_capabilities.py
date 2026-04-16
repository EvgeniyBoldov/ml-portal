from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.tool_instance import ToolInstance


def resolve_provider_kind(config: Optional[Dict[str, Any]]) -> str:
    return str((config or {}).get("provider_kind") or "").strip().lower()


def is_mcp_service_instance(instance: ToolInstance) -> bool:
    connector_type = str(getattr(instance, "connector_type", "") or "").strip().lower()
    if connector_type:
        if connector_type != "mcp":
            return False
    elif getattr(instance, "instance_kind", "") != "service":
        return False

    provider_kind = resolve_provider_kind(instance.config)
    return provider_kind == "mcp"
