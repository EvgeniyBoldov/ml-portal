from __future__ import annotations

from app.runtime.budget import RuntimeBudget, RuntimeBudgetTracker


def test_runtime_budget_from_platform_config_uses_defaults_and_overrides():
    budget = RuntimeBudget.from_platform_config(
        planner_max_steps=12,
        planner_max_wall_time_ms=120_000,
        platform_config={
            "runtime_budget": {
                "max_agent_steps": 7,
                "max_tool_calls_total": 9,
                "per_tool_timeout_ms": 8_000,
            }
        },
    )

    assert budget.max_planner_iterations == 12
    assert budget.max_wall_time_ms == 120_000
    assert budget.max_agent_steps == 7
    assert budget.max_tool_calls_total == 9
    assert budget.per_tool_timeout_ms == 8_000


def test_runtime_budget_tracker_counts_and_limits():
    tracker = RuntimeBudgetTracker(
        budget=RuntimeBudget(
            max_planner_iterations=2,
            max_agent_steps=2,
            max_tool_calls_total=1,
            max_wall_time_ms=120_000,
            per_tool_timeout_ms=30_000,
            max_steps_without_success=2,
        )
    )

    assert tracker.can_run_planner_iteration() is True
    tracker.record_planner_iteration()
    assert tracker.can_run_planner_iteration() is True
    tracker.record_planner_iteration()
    assert tracker.can_run_planner_iteration() is False

    assert tracker.can_run_agent_step() is True
    tracker.record_agent_step()
    assert tracker.can_run_agent_step() is True
    tracker.record_agent_step()
    assert tracker.can_run_agent_step() is False

    assert tracker.can_consume_tool_call() is True
    tracker.record_tool_call()
    assert tracker.can_consume_tool_call() is False

    snap = tracker.snapshot()
    assert snap["consumed_planner_iterations"] == 2
    assert snap["consumed_agent_steps"] == 2
    assert snap["consumed_tool_calls"] == 1
