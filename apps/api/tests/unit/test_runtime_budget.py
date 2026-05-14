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


def test_agent_limit_should_apply_within_remaining_global_budget():
    """
    Desired runtime semantics:
    global max_tool_calls_total=10, consumed=4, agent local limit=2
    => agent can still do exactly 2 calls (from remaining 6).
    """
    tracker = RuntimeBudgetTracker(
        budget=RuntimeBudget(
            max_planner_iterations=10,
            max_agent_steps=20,
            max_tool_calls_total=10,
            max_wall_time_ms=120_000,
            per_tool_timeout_ms=30_000,
            max_steps_without_success=2,
        )
    )

    # Simulate previous agents already consumed 4 global calls
    for _ in range(4):
        assert tracker.can_consume_tool_call() is True
        tracker.record_tool_call()

    remaining_global = tracker.budget.max_tool_calls_total - tracker.snapshot()["consumed_tool_calls"]
    assert remaining_global == 6

    # Local runtime policy for this agent
    agent_local_limit = 2
    allowed_for_agent = min(agent_local_limit, remaining_global)
    assert allowed_for_agent == 2

    consumed_local = 0
    while consumed_local < allowed_for_agent:
        assert tracker.can_consume_tool_call() is True
        tracker.record_tool_call()
        consumed_local += 1

    assert consumed_local == 2
    assert tracker.snapshot()["consumed_tool_calls"] == 6
