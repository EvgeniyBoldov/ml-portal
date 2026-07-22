from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EntityLimits:
    """Limits for one concrete execution entity."""

    plan_revisions: Optional[int] = None
    task_attempts: Optional[int] = None
    agent_runs: Optional[int] = None
    llm_calls: Optional[int] = None
    tool_calls: Optional[int] = None
    tokens_total: Optional[int] = None
    retries: Optional[int] = None
    wall_time_ms: Optional[int] = None
    max_parallel_tasks: Optional[int] = None


@dataclass(frozen=True)
class RunLimits:
    """Hard caps for the whole run."""

    plan_revisions: Optional[int] = None
    task_attempts: Optional[int] = None
    agent_runs: Optional[int] = None
    llm_calls: Optional[int] = None
    tool_calls: Optional[int] = None
    tokens_total: Optional[int] = None
    retries: Optional[int] = None
    wall_time_ms: Optional[int] = None
    max_parallel_tasks: Optional[int] = None

    def as_entity_limits(self) -> EntityLimits:
        return EntityLimits(
            plan_revisions=self.plan_revisions,
            task_attempts=self.task_attempts,
            agent_runs=self.agent_runs,
            llm_calls=self.llm_calls,
            tool_calls=self.tool_calls,
            tokens_total=self.tokens_total,
            retries=self.retries,
            wall_time_ms=self.wall_time_ms,
            max_parallel_tasks=self.max_parallel_tasks,
        )
