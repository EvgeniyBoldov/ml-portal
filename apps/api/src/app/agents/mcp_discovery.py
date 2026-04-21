from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional


RuntimeRiskLevel = Literal["safe", "write", "destructive"]
RuntimeCredentialScope = Literal["platform", "user", "auto"]

DEFAULT_RISK_LEVEL: RuntimeRiskLevel = "safe"
DEFAULT_SIDE_EFFECTS = False
DEFAULT_REQUIRES_CONFIRMATION = False
DEFAULT_CREDENTIAL_SCOPE: RuntimeCredentialScope = "auto"


class MCPDiscoveryValidationError(ValueError):
    """Raised when MCP-discovered operation metadata is invalid."""


@dataclass(slots=True, frozen=True)
class DiscoveredOperation:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    risk_level: RuntimeRiskLevel
    side_effects: bool
    requires_confirmation: bool
    credential_scope: RuntimeCredentialScope


def parse_discovered_operation(
    *,
    tool_name: str,
    description: Optional[str],
    input_schema: Optional[Dict[str, Any]],
    output_schema: Optional[Dict[str, Any]],
) -> DiscoveredOperation:
    normalized_input_schema = dict(input_schema or {})
    runtime_flags = _parse_runtime_flags(
        tool_name=tool_name,
        runtime_payload=normalized_input_schema.get("x-runtime"),
    )
    normalized_input_schema["x-runtime"] = {
        "risk_level": runtime_flags.risk_level,
        "side_effects": runtime_flags.side_effects,
        "requires_confirmation": runtime_flags.requires_confirmation,
        "credential_scope": runtime_flags.credential_scope,
    }
    return DiscoveredOperation(
        name=tool_name,
        description=str(description or ""),
        input_schema=normalized_input_schema,
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        risk_level=runtime_flags.risk_level,
        side_effects=runtime_flags.side_effects,
        requires_confirmation=runtime_flags.requires_confirmation,
        credential_scope=runtime_flags.credential_scope,
    )


@dataclass(slots=True, frozen=True)
class RuntimeFlags:
    risk_level: RuntimeRiskLevel = DEFAULT_RISK_LEVEL
    side_effects: bool = DEFAULT_SIDE_EFFECTS
    requires_confirmation: bool = DEFAULT_REQUIRES_CONFIRMATION
    credential_scope: RuntimeCredentialScope = DEFAULT_CREDENTIAL_SCOPE


def _parse_runtime_flags(*, tool_name: str, runtime_payload: Any) -> RuntimeFlags:
    if runtime_payload is None:
        return RuntimeFlags()
    if not isinstance(runtime_payload, dict):
        raise MCPDiscoveryValidationError(
            f"MCP discovery error for tool '{tool_name}' operation '{tool_name}': "
            "x-runtime must be an object"
        )

    risk_level_raw = runtime_payload.get("risk_level", DEFAULT_RISK_LEVEL)
    risk_level = str(risk_level_raw or "").strip().lower()
    if risk_level not in {"safe", "write", "destructive"}:
        raise MCPDiscoveryValidationError(
            f"MCP discovery error for tool '{tool_name}' operation '{tool_name}': "
            f"invalid x-runtime.risk_level='{risk_level_raw}'"
        )

    side_effects_raw = runtime_payload.get("side_effects", DEFAULT_SIDE_EFFECTS)
    if not isinstance(side_effects_raw, bool):
        raise MCPDiscoveryValidationError(
            f"MCP discovery error for tool '{tool_name}' operation '{tool_name}': "
            "x-runtime.side_effects must be boolean"
        )

    requires_confirmation_raw = runtime_payload.get(
        "requires_confirmation",
        DEFAULT_REQUIRES_CONFIRMATION,
    )
    if not isinstance(requires_confirmation_raw, bool):
        raise MCPDiscoveryValidationError(
            f"MCP discovery error for tool '{tool_name}' operation '{tool_name}': "
            "x-runtime.requires_confirmation must be boolean"
        )

    credential_scope_raw = runtime_payload.get(
        "credential_scope",
        DEFAULT_CREDENTIAL_SCOPE,
    )
    credential_scope = str(credential_scope_raw or "").strip().lower()
    if credential_scope not in {"platform", "user", "auto"}:
        raise MCPDiscoveryValidationError(
            f"MCP discovery error for tool '{tool_name}' operation '{tool_name}': "
            f"invalid x-runtime.credential_scope='{credential_scope_raw}'"
        )

    return RuntimeFlags(
        risk_level=risk_level,  # type: ignore[arg-type]
        side_effects=side_effects_raw,
        requires_confirmation=requires_confirmation_raw,
        credential_scope=credential_scope,  # type: ignore[arg-type]
    )

