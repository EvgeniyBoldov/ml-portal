"""Tool visibility and descriptor enrichment shared by MCP adapters."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any

_DESTRUCTIVE = re.compile(r"(^|_)(delete|remove|destroy|purge|revoke|archive|deactivate|drop)(_|$)", re.I)
INTERNAL_ARGUMENTS = frozenset({
    "credential_access", "credentials", "instance_context", "collection_slug", "collection_id",
})


@dataclass(frozen=True)
class ToolPolicy:
    # None explicitly means all tools; an empty set exposes no tools.
    enabled_tools: frozenset[str] | None = frozenset()
    descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)

    def allows(self, name: str) -> bool:
        return self.enabled_tools is None or name in self.enabled_tools

    def decorate(self, tool: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(tool)
        overrides = self.descriptors.get(str(tool.get("name") or ""), {})
        for key in ("description", "title"):
            if key in overrides:
                if not isinstance(overrides[key], str):
                    raise ValueError("Tool descriptor text must be a string")
                result[key] = overrides[key]
        annotations = dict(result.get("annotations") or {})
        annotations.update(overrides.get("annotations") or {})
        result["annotations"] = annotations
        schema = dict(result.get("inputSchema") or {})
        metadata = dict(schema.get("x-runtime") or {})
        metadata.update(overrides.get("x-runtime") or {})
        if not metadata.get("risk_level"):
            if annotations.get("destructiveHint") is True or _DESTRUCTIVE.search(str(result.get("name") or "")):
                risk = "destructive"
            elif annotations.get("readOnlyHint") is True:
                risk = "safe"
            elif annotations.get("readOnlyHint") is False:
                risk = "write"
            else:
                risk = "destructive"
            metadata["risk_level"] = risk
        if metadata["risk_level"] not in {"safe", "write", "destructive"}:
            raise ValueError("Invalid runtime risk descriptor")
        risky = metadata["risk_level"] != "safe"
        metadata.setdefault("side_effects", risky)
        metadata.setdefault("requires_confirmation", risky)
        metadata.setdefault("idempotent", annotations.get("idempotentHint") is True)
        metadata.setdefault("credential_scope", "user")
        if metadata["credential_scope"] not in {"auto", "user", "platform"}:
            raise ValueError("Invalid credential scope descriptor")
        for key in ("side_effects", "requires_confirmation", "idempotent"):
            if not isinstance(metadata[key], bool):
                raise ValueError("Runtime flag descriptor must be boolean")
        schema["x-runtime"] = metadata
        result["inputSchema"] = schema
        return result

    def filter_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            result["tools"] = [self.decorate(t) for t in result["tools"] if self.allows(str(t.get("name") or ""))]
        return payload
