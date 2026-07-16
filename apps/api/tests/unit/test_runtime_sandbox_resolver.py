from __future__ import annotations

from types import SimpleNamespace

from app.services.sandbox_override_resolver import SandboxOverrideResolver

def test_sandbox_agent_slug_uses_only_explicit_override():
    cfg_without_override = SandboxOverrideResolver({"overrides": {}})
    assert cfg_without_override.agent_slug_override is None

    cfg_with_override = SandboxOverrideResolver(
        {
            "overrides": {
                "ov-1": {
                    "entity_type": "orchestration",
                    "field_path": "agent.slug",
                    "value_json": "viewer",
                }
            },
        },
    )
    assert cfg_with_override.agent_slug_override == "viewer"


def test_sandbox_runtime_overrides_include_limits_and_agent_limits():
    agent_version = SimpleNamespace(id="agent-version-1")
    resolver = SandboxOverrideResolver(
        {
            "overrides": {
                "ov-platform": {
                    "entity_type": "orchestration",
                    "entity_id": None,
                    "field_path": "platform_limits.runtime_steps_max",
                    "value_json": 12,
                },
                "ov-agent": {
                    "entity_type": "agent_version",
                    "entity_id": "agent-version-1",
                    "field_path": "limits.runtime_tool_calls_max",
                    "value_json": 7,
                },
                "ov-orch": {
                    "entity_type": "orchestration",
                    "entity_id": "planner",
                    "field_path": "limits.runtime_retries_max",
                    "value_json": 3,
                },
            },
        },
    )

    runtime_overrides = resolver.to_runtime_overrides(agent_version=agent_version)

    assert runtime_overrides["platform_limits"]["runtime_steps_max"] == 12
    assert runtime_overrides["agent_limits"]["runtime_tool_calls_max"] == 7
    assert runtime_overrides["orchestrator_limits"]["planner"]["runtime_retries_max"] == 3
