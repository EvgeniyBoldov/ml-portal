"""Tool visibility and descriptor enrichment shared by MCP adapters."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
INTERNAL_ARGUMENTS = frozenset({
    "credential_access", "credentials", "instance_context", "collection_slug", "collection_id",
})


@dataclass(frozen=True)
class ToolPolicy:
    # None explicitly means all tools; an empty set exposes no tools.
    enabled_tools: frozenset[str] | None = frozenset()
    descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.enabled_tools is not None:
            for name in self.enabled_tools:
                self.risk_level(name)

    def allows(self, name: str) -> bool:
        return self.enabled_tools is None or name in self.enabled_tools

    def risk_level(self, name: str) -> str:
        descriptor = self.descriptors.get(name)
        runtime = descriptor.get("x-runtime") if isinstance(descriptor, dict) else None
        if not isinstance(runtime, dict) or set(runtime) != {"risk_level"}:
            raise ValueError(f"Tool '{name}' requires an explicit x-runtime.risk_level descriptor")
        value = str(runtime.get("risk_level") or "").strip().lower()
        if value not in {"safe", "risky"}:
            raise ValueError(f"Tool '{name}' has invalid risk level; expected safe or risky")
        return value

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
        # Provider metadata is untrusted. Publish only the local operation
        # filter's explicit binary risk classification; never relay provider
        # credential scope or confirmation/side-effect claims.
        schema["x-runtime"] = {"risk_level": self.risk_level(str(tool.get("name") or ""))}
        result["inputSchema"] = schema
        return result

    def filter_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            result["tools"] = [self.decorate(t) for t in result["tools"] if self.allows(str(t.get("name") or ""))]
        return payload
