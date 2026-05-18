from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration_settings import OrchestrationSettings
from app.models.system_llm_role import SystemLLMRole
from .schema import BudgetLimits, EntityLimits, RunLimits


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _min_or_none(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


@dataclass(frozen=True)
class ResolvedLimits:
    run: BudgetLimits


class BudgetLimitsResolver:
    """Legacy resolver kept for compatibility with existing callers."""

    @staticmethod
    def resolve_from_platform(
        *,
        planner_max_steps: int,
        planner_max_wall_time_ms: int,
        platform_config: Dict[str, Any],
    ) -> ResolvedLimits:
        cfg = platform_config if isinstance(platform_config, dict) else {}
        budget_cfg = cfg.get("runtime_budget") if isinstance(cfg.get("runtime_budget"), dict) else {}

        run = BudgetLimits(
            max_planner_iterations=max(1, int(budget_cfg.get("max_planner_iterations") or planner_max_steps)),
            max_agent_steps=max(1, int(budget_cfg.get("max_agent_steps") or 20)),
            max_tool_calls_total=max(1, int(budget_cfg.get("max_tool_calls_total") or 50)),
            max_wall_time_ms=max(1, int(budget_cfg.get("max_wall_time_ms") or planner_max_wall_time_ms)),
            per_tool_timeout_ms=max(1, int(budget_cfg.get("per_tool_timeout_ms") or 30_000)),
            max_steps_without_success=max(1, int(budget_cfg.get("max_steps_without_success") or 2)),
            loop_threshold=max(1, int(budget_cfg.get("loop_threshold") or 3)),
            max_retries=max(1, int(budget_cfg.get("max_retries") or 3)),
            max_tokens_total=(
                int(budget_cfg.get("max_tokens_total"))
                if budget_cfg.get("max_tokens_total") is not None
                else None
            ),
        )
        return ResolvedLimits(run=run)


class BudgetResolver:
    """New resolver for per-entity limits model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_run(self, platform_config: Dict[str, Any]) -> RunLimits:
        cfg = platform_config if isinstance(platform_config, dict) else {}
        budget_cfg = cfg.get("runtime_budget") if isinstance(cfg.get("runtime_budget"), dict) else {}
        policy_cfg = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}

        planner_steps = _as_optional_int(budget_cfg.get("max_planner_iterations"))
        if planner_steps is None:
            planner_steps = _as_optional_int(policy_cfg.get("max_steps"))

        wall_time_ms = _as_optional_int(budget_cfg.get("max_wall_time_ms"))
        if wall_time_ms is None:
            wall_time_ms = _as_optional_int(policy_cfg.get("max_wall_time_ms"))

        return RunLimits(
            planner_steps=planner_steps,
            agent_steps=_as_optional_int(budget_cfg.get("max_agent_steps")),
            tool_calls=_as_optional_int(budget_cfg.get("max_tool_calls_total")),
            tokens_total=_as_optional_int(budget_cfg.get("max_tokens_total")),
            retries=_as_optional_int(budget_cfg.get("max_retries")),
            wall_time_ms=wall_time_ms,
        )

    async def resolve_orchestrator(self, role: str) -> EntityLimits:
        role_key = (role or "").strip().lower()

        settings = (
            await self._session.execute(select(OrchestrationSettings).limit(1))
        ).scalars().first()

        planner_steps = None
        retries = None
        wall_time_ms = None
        if role_key == "planner" and settings is not None:
            planner_steps = _as_optional_int(settings.executor_max_steps)
            retries = _as_optional_int(settings.executor_max_retries)
            timeout_s = _as_optional_int(settings.executor_timeout_s)
            wall_time_ms = timeout_s * 1000 if timeout_s is not None else None

        llm_role = (
            await self._session.execute(
                select(SystemLLMRole).where(SystemLLMRole.role_type == role_key, SystemLLMRole.is_active.is_(True)).limit(1)
            )
        ).scalars().first()

        if llm_role is not None:
            retries = _min_or_none(retries, _as_optional_int(llm_role.max_retries))
            llm_timeout_s = _as_optional_int(llm_role.timeout_s)
            llm_wall = llm_timeout_s * 1000 if llm_timeout_s is not None else None
            wall_time_ms = _min_or_none(wall_time_ms, llm_wall)
            tokens_total = _as_optional_int(llm_role.max_tokens)
        else:
            tokens_total = None

        return EntityLimits(
            planner_steps=planner_steps,
            tokens_total=tokens_total,
            retries=retries,
            wall_time_ms=wall_time_ms,
        )
