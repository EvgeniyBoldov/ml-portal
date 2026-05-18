from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EntityLimits:
    """Limits for one concrete entity."""

    planner_steps: Optional[int] = None
    agent_steps: Optional[int] = None
    tool_calls: Optional[int] = None
    tokens_total: Optional[int] = None
    retries: Optional[int] = None
    wall_time_ms: Optional[int] = None


@dataclass(frozen=True)
class RunLimits:
    """Hard caps for the whole run."""

    planner_steps: Optional[int] = None
    agent_steps: Optional[int] = None
    tool_calls: Optional[int] = None
    tokens_total: Optional[int] = None
    retries: Optional[int] = None
    wall_time_ms: Optional[int] = None

    def as_entity_limits(self) -> EntityLimits:
        return EntityLimits(
            planner_steps=self.planner_steps,
            agent_steps=self.agent_steps,
            tool_calls=self.tool_calls,
            tokens_total=self.tokens_total,
            retries=self.retries,
            wall_time_ms=self.wall_time_ms,
        )


@dataclass(frozen=True)
class BudgetLimits:
    """Legacy flat runtime limits (kept for compatibility while migrating)."""

    max_planner_iterations: int
    max_agent_steps: int
    max_tool_calls_total: int
    max_wall_time_ms: int
    per_tool_timeout_ms: int
    max_steps_without_success: int
    loop_threshold: int = 3
    max_retries: int = 3
    max_tokens_total: Optional[int] = None


@dataclass(frozen=True)
class BudgetMetric:
    used: int
    limit: Optional[int]
    remaining: Optional[int]
