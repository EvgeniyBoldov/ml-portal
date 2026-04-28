"""Unified runtime budget DTO and tracker."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class RuntimeBudget:
    max_planner_iterations: int
    max_agent_steps: int
    max_tool_calls_total: int
    max_wall_time_ms: int
    per_tool_timeout_ms: int
    max_steps_without_success: int
    loop_threshold: int = 3  # Detect loop after N identical signatures

    @classmethod
    def from_platform_config(
        cls,
        *,
        planner_max_steps: int,
        planner_max_wall_time_ms: int,
        platform_config: Dict[str, Any],
    ) -> "RuntimeBudget":
        cfg = platform_config if isinstance(platform_config, dict) else {}
        budget_cfg = cfg.get("runtime_budget") if isinstance(cfg.get("runtime_budget"), dict) else {}
        return cls(
            max_planner_iterations=_as_positive_int(
                budget_cfg.get("max_planner_iterations"),
                planner_max_steps,
            ),
            max_agent_steps=_as_positive_int(budget_cfg.get("max_agent_steps"), 20),
            max_tool_calls_total=_as_positive_int(budget_cfg.get("max_tool_calls_total"), 50),
            max_wall_time_ms=_as_positive_int(
                budget_cfg.get("max_wall_time_ms"),
                planner_max_wall_time_ms,
            ),
            per_tool_timeout_ms=_as_positive_int(budget_cfg.get("per_tool_timeout_ms"), 30_000),
            max_steps_without_success=_as_positive_int(
                budget_cfg.get("max_steps_without_success"),
                2,
            ),
            loop_threshold=_as_positive_int(budget_cfg.get("loop_threshold"), 3),
        )


class RuntimeBudgetTracker:
    """Mutable per-turn budget tracker shared by pipeline stages.

    NOTE(5.4): This tracker is NOT thread-safe. Pipeline is strictly sequential
    (no fan-out to multiple agents), so this is fine. If parallel agent execution
    is added in the future, this class will need refactoring with proper locking.
    """

    def __init__(self, *, budget: RuntimeBudget) -> None:
        self.budget = budget
        self._started_at = time.monotonic()
        self._planner_iterations = 0
        self._agent_steps = 0
        self._tool_calls = 0

    def save_budget(self) -> RuntimeBudget:
        """Return a copy of the current budget for later restoration."""
        return self.budget

    def restore_budget(self, saved: RuntimeBudget) -> None:
        """Restore a previously saved budget (e.g. after sub-agent execution)."""
        self.budget = saved

    def apply_agent_limits_inplace(
        self,
        *,
        max_steps: int,
        max_tool_calls_total: int,
        tool_timeout_ms: int,
        max_steps_without_success: int,
    ) -> None:
        """Narrow the shared budget to the sub-agent's policy limits (takes the min)."""
        self.budget = RuntimeBudget(
            max_planner_iterations=self.budget.max_planner_iterations,
            max_agent_steps=min(self.budget.max_agent_steps, _as_positive_int(max_steps, max_steps)),
            max_tool_calls_total=min(
                self.budget.max_tool_calls_total,
                _as_positive_int(max_tool_calls_total, max_tool_calls_total),
            ),
            max_wall_time_ms=self.budget.max_wall_time_ms,
            per_tool_timeout_ms=min(
                self.budget.per_tool_timeout_ms,
                _as_positive_int(tool_timeout_ms, tool_timeout_ms),
            ),
            max_steps_without_success=min(
                self.budget.max_steps_without_success,
                _as_positive_int(max_steps_without_success, max_steps_without_success),
            ),
            loop_threshold=self.budget.loop_threshold,
        )

    def remaining_wall_time_ms(self) -> int:
        elapsed = int((time.monotonic() - self._started_at) * 1000)
        return max(0, self.budget.max_wall_time_ms - elapsed)

    def can_run_planner_iteration(self) -> bool:
        return (
            self._planner_iterations < self.budget.max_planner_iterations
            and self.remaining_wall_time_ms() > 0
        )

    def record_planner_iteration(self) -> None:
        self._planner_iterations += 1

    def can_run_agent_step(self) -> bool:
        return (
            self._agent_steps < self.budget.max_agent_steps
            and self.remaining_wall_time_ms() > 0
        )

    def record_agent_step(self) -> None:
        self._agent_steps += 1

    def can_consume_tool_call(self) -> bool:
        return (
            self._tool_calls < self.budget.max_tool_calls_total
            and self.remaining_wall_time_ms() > 0
        )

    def record_tool_call(self) -> None:
        self._tool_calls += 1

    def snapshot(self) -> Dict[str, int]:
        return {
            "max_planner_iterations": self.budget.max_planner_iterations,
            "max_agent_steps": self.budget.max_agent_steps,
            "max_tool_calls_total": self.budget.max_tool_calls_total,
            "max_wall_time_ms": self.budget.max_wall_time_ms,
            "per_tool_timeout_ms": self.budget.per_tool_timeout_ms,
            "max_steps_without_success": self.budget.max_steps_without_success,
            "loop_threshold": self.budget.loop_threshold,
            "consumed_planner_iterations": self._planner_iterations,
            "consumed_agent_steps": self._agent_steps,
            "consumed_tool_calls": self._tool_calls,
            "remaining_wall_time_ms": self.remaining_wall_time_ms(),
        }


def _as_positive_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return int(default)
        return max(1, int(value))
    except (TypeError, ValueError):
        return int(default)
