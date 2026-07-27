from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_limit import ExecutionLimitScope
from app.services.execution_limits_service import ExecutionLimitsService, apply_limits_override
from .schema import EntityLimits, RunLimits


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


class BudgetResolver:
    """New resolver for per-entity limits model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._limits_service = ExecutionLimitsService(session)

    async def resolve_run(self, platform_config: Dict[str, Any], sandbox_overrides: Optional[Dict[str, Any]] = None) -> RunLimits:
        limits = await self._limits_service.get_effective(
            scope_type=ExecutionLimitScope.PLATFORM,
            scope_ref="global",
        )
        limits = apply_limits_override(limits, (sandbox_overrides or {}).get("platform_limits"))
        return RunLimits(
            plan_revisions=_as_optional_int(limits.plan_revisions_max),
            task_attempts=_as_optional_int(limits.task_attempts_total_max),
            agent_runs=_as_optional_int(limits.agent_runs_total_max),
            llm_calls=_as_optional_int(limits.llm_calls_total_max),
            tool_calls=_as_optional_int(limits.tool_calls_total_max),
            tokens_total=_as_optional_int(limits.tokens_total_max),
            retries=_as_optional_int(limits.planner_retries_max),
            wall_time_ms=_as_optional_int(limits.execution_wall_time_ms_max),
            max_parallel_tasks=_as_optional_int(limits.max_parallel_tasks) or 1,
        )

    async def resolve_orchestrator(self, role: str, sandbox_overrides: Optional[Dict[str, Any]] = None) -> EntityLimits:
        role_key = (role or "").strip().lower()
        limits = await self._limits_service.get_effective(
            scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
            scope_ref=role_key,
        )
        limits = apply_limits_override(
            limits,
            ((sandbox_overrides or {}).get("orchestrator_limits") or {}).get(role_key),
        )
        return EntityLimits(
            plan_revisions=_as_optional_int(limits.plan_revisions_max),
            task_attempts=_as_optional_int(limits.task_attempts_total_max),
            agent_runs=_as_optional_int(limits.agent_runs_total_max),
            llm_calls=_as_optional_int(limits.planner_llm_calls_max if role_key == "planner" else limits.agent_llm_calls_max),
            tool_calls=_as_optional_int(limits.agent_tool_calls_max if role_key != "planner" else None),
            tokens_total=_as_optional_int(limits.planner_tokens_total_max if role_key == "planner" else limits.agent_tokens_total_max),
            retries=_as_optional_int(limits.planner_retries_max),
            wall_time_ms=_as_optional_int(limits.planner_execution_wall_time_ms_max if role_key == "planner" else limits.agent_execution_wall_time_ms_max),
        )
