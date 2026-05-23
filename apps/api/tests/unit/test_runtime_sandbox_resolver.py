from __future__ import annotations

from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver


def test_sandbox_agent_slug_uses_only_explicit_override():
    # Baseline tenant settings in effective config must not pin sandbox runs.
    cfg_without_override = {
        "tenant": {"name": "Example"},
        "sandbox": {"overrides": []},
    }
    assert RuntimeSandboxResolver.sandbox_agent_slug(cfg_without_override) is None

    cfg_with_override = {
        "tenant": {"name": "Example"},
        "overrides": {
            "ov-1": {
                    "entity_type": "orchestration",
                    "field_path": "agent.slug",
                    "value_json": "viewer",
                }
        },
    }
    assert RuntimeSandboxResolver.sandbox_agent_slug(cfg_with_override) == "viewer"
