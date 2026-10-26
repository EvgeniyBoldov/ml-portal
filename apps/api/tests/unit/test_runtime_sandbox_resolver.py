from __future__ import annotations

from types import SimpleNamespace

from app.services.sandbox_override_resolver import SandboxOverrideResolver, SandboxToolOverrides

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


def test_discovered_tool_runtime_contract_excludes_non_executable_release_selection():
    resolver = SandboxOverrideResolver({"overrides": {
        "release": {
            "entity_type": "discovered_tool", "entity_id": "tool-1",
            "field_path": "tool_release_id", "value_json": "archived-or-missing-release",
        },
        "published": {
            "entity_type": "discovered_tool", "entity_id": "tool-1",
            "field_path": "published", "value_json": False,
        },
    }})

    runtime = resolver.to_runtime_overrides()
    typed = SandboxToolOverrides.from_runtime_overrides(runtime)

    assert "discovered_tool_release_ids" not in runtime
    assert typed.publication == {"tool-1": False}
    assert SandboxOverrideResolver.is_override_allowed(
        entity_type="discovered_tool", field_path="tool_release_id"
    )[0] is False


def test_sandbox_runtime_overrides_include_limits_and_agent_limits():
    agent_version = SimpleNamespace(id="agent-version-1")
    resolver = SandboxOverrideResolver(
        {
            "overrides": {
                "ov-platform": {
                    "entity_type": "orchestration",
                    "entity_id": None,
                    "field_path": "platform_limits.iterations_max",
                    "value_json": 12,
                },
                "ov-agent": {
                    "entity_type": "agent_version",
                    "entity_id": "agent-version-1",
                    "field_path": "agent_limits.tool_calls_max",
                    "value_json": 7,
                },
                "ov-agent-model": {
                    "entity_type": "agent_version",
                    "entity_id": "agent-version-1",
                    "field_path": "model",
                    "value_json": "llm.local.qwen",
                },
                "ov-orch": {
                    "entity_type": "orchestration",
                    "entity_id": "planner",
                    "field_path": "orchestrator_limits.llm_calls_max",
                    "value_json": 3,
                },
                "ov-runtime": {
                    "entity_type": "orchestration",
                    "entity_id": None,
                    "field_path": "runtime_limits.max_iterations",
                    "value_json": 4,
                },
            },
        },
    )

    runtime_overrides = resolver.to_runtime_overrides(agent_version=agent_version)

    assert runtime_overrides["platform_limits"]["iterations_max"] == 12
    assert runtime_overrides["agent_limits"]["tool_calls_max"] == 7
    assert runtime_overrides["agent_exec"]["model"] == "llm.local.qwen"
    assert runtime_overrides["orchestrator_limits"]["planner"]["llm_calls_max"] == 3
    assert runtime_overrides["runtime_limits"]["max_iterations"] == 4


def test_sandbox_agent_safety_overrides_are_compiled_into_the_effective_prompt():
    version = SimpleNamespace(
        id="agent-version-1", identity="Identity", mission=None, scope=None,
        rules=None, tool_use_rules=None, output_format=None, examples=None,
        never_do=None, allowed_ops=None, prompt=None,
    )
    resolver = SandboxOverrideResolver({"overrides": {
        "never-do": {"entity_type": "agent_version", "entity_id": version.id, "field_path": "never_do", "value_json": "Не удаляй данные"},
        "allowed-ops": {"entity_type": "agent_version", "entity_id": version.id, "field_path": "allowed_ops", "value_json": "Только чтение"},
    }})

    prompt = resolver.compile_patched_prompt(version)

    assert "Не удаляй данные" in prompt
    assert "Только чтение" in prompt
