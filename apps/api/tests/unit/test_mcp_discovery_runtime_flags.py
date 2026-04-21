from __future__ import annotations

import pytest

from app.agents.mcp_discovery import MCPDiscoveryValidationError, parse_discovered_operation


def test_discovery_defaults_when_x_runtime_missing() -> None:
    discovered = parse_discovered_operation(
        tool_name="netbox.get_device",
        description="Get device",
        input_schema={"type": "object"},
        output_schema=None,
    )
    assert discovered.risk_level == "safe"
    assert discovered.side_effects is False
    assert discovered.requires_confirmation is False
    assert discovered.credential_scope == "auto"
    assert discovered.input_schema["x-runtime"] == {
        "risk_level": "safe",
        "side_effects": False,
        "requires_confirmation": False,
        "credential_scope": "auto",
    }


def test_discovery_merges_partial_x_runtime_with_defaults() -> None:
    discovered = parse_discovered_operation(
        tool_name="jira.search",
        description="Search issues",
        input_schema={
            "type": "object",
            "x-runtime": {
                "risk_level": "write",
            },
        },
        output_schema=None,
    )
    assert discovered.risk_level == "write"
    assert discovered.side_effects is False
    assert discovered.requires_confirmation is False
    assert discovered.credential_scope == "auto"


def test_discovery_rejects_invalid_risk_level() -> None:
    with pytest.raises(MCPDiscoveryValidationError, match="invalid x-runtime.risk_level"):
        parse_discovered_operation(
            tool_name="jira.delete",
            description="Delete issue",
            input_schema={
                "type": "object",
                "x-runtime": {"risk_level": "banana"},
            },
            output_schema=None,
        )


def test_discovery_rejects_invalid_credential_scope() -> None:
    with pytest.raises(MCPDiscoveryValidationError, match="invalid x-runtime.credential_scope"):
        parse_discovered_operation(
            tool_name="jira.search",
            description="Search issue",
            input_schema={
                "type": "object",
                "x-runtime": {"credential_scope": "invalid"},
            },
            output_schema=None,
        )
