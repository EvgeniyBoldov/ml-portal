from __future__ import annotations

from app.runtime.budgets import BudgetLimitsResolver


def test_resolver_uses_platform_defaults_when_config_missing() -> None:
    resolved = BudgetLimitsResolver.resolve_from_platform(
        planner_max_steps=8,
        planner_max_wall_time_ms=90_000,
        platform_config={},
    )

    assert resolved.run.max_planner_iterations == 8
    assert resolved.run.max_wall_time_ms == 90_000
    assert resolved.run.max_agent_steps == 20
    assert resolved.run.max_tool_calls_total == 50


def test_resolver_applies_runtime_budget_overrides() -> None:
    resolved = BudgetLimitsResolver.resolve_from_platform(
        planner_max_steps=8,
        planner_max_wall_time_ms=90_000,
        platform_config={
            "runtime_budget": {
                "max_planner_iterations": 5,
                "max_agent_steps": 12,
                "max_tool_calls_total": 40,
                "max_wall_time_ms": 120_000,
                "per_tool_timeout_ms": 15_000,
                "max_steps_without_success": 4,
                "loop_threshold": 6,
                "max_retries": 2,
                "max_tokens_total": 10_000,
            }
        },
    )

    run = resolved.run
    assert run.max_planner_iterations == 5
    assert run.max_agent_steps == 12
    assert run.max_tool_calls_total == 40
    assert run.max_wall_time_ms == 120_000
    assert run.per_tool_timeout_ms == 15_000
    assert run.max_steps_without_success == 4
    assert run.loop_threshold == 6
    assert run.max_retries == 2
    assert run.max_tokens_total == 10_000
