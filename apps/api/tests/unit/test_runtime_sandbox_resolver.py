from __future__ import annotations

import importlib.util
import logging
import sys
import types
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace


@lru_cache(maxsize=1)
def _load_module():
    core_pkg = sys.modules.get("app.core")
    if core_pkg is None:
        core_pkg = types.ModuleType("app.core")
        core_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["app.core"] = core_pkg

    logging_mod = sys.modules.get("app.core.logging")
    if logging_mod is None:
        logging_mod = types.ModuleType("app.core.logging")
        logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
        sys.modules["app.core.logging"] = logging_mod
    setattr(core_pkg, "logging", logging_mod)

    module_path = Path(__file__).resolve().parents[2] / "src" / "app" / "services" / "sandbox_override_resolver.py"
    spec = importlib.util.spec_from_file_location("sandbox_override_resolver_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolver_cls():
    return _load_module().SandboxOverrideResolver


def test_sandbox_agent_slug_uses_only_explicit_override():
    Resolver = _resolver_cls()

    cfg_without_override = Resolver({"overrides": {}})
    assert cfg_without_override.agent_slug_override is None

    cfg_with_override = Resolver(
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
    Resolver = _resolver_cls()
    agent_version = SimpleNamespace(id="agent-version-1")
    resolver = Resolver(
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
