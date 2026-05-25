from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_limit import ExecutionLimitScope
from app.services.execution_limits_service import ExecutionLimitsService, apply_limits_override
from .schema import BudgetLimits, EntityLimits, RunLimits


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


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
        self._limits_service = ExecutionLimitsService(session)

    async def resolve_run(self, platform_config: Dict[str, Any], sandbox_overrides: Optional[Dict[str, Any]] = None) -> RunLimits:
        limits = await self._limits_service.get_effective(
            scope_type=ExecutionLimitScope.PLATFORM,
            scope_ref="global",
        )
        limits = apply_limits_override(limits, (sandbox_overrides or {}).get("platform_limits"))
        planner_steps = _as_optional_int(limits.runtime_steps_max)
        wall_time_ms = _as_optional_int(limits.runtime_wall_time_ms_max)

        return RunLimits(
            planner_steps=planner_steps,
            # Unified step budget: planner/agent use the same limit.
            agent_steps=planner_steps,
            tool_calls=_as_optional_int(limits.runtime_tool_calls_max),
            tokens_total=_as_optional_int(limits.runtime_tokens_total_max),
            retries=_as_optional_int(limits.runtime_retries_max),
            wall_time_ms=wall_time_ms,
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
        runtime_steps = _as_optional_int(limits.runtime_steps_max)
        retries = _as_optional_int(limits.runtime_retries_max)
        wall_time_ms = _as_optional_int(limits.runtime_wall_time_ms_max)
        tokens_total = _as_optional_int(limits.runtime_tokens_total_max)

        return EntityLimits(
            planner_steps=runtime_steps,
            agent_steps=runtime_steps,
            tokens_total=tokens_total,
            retries=retries,
            wall_time_ms=wall_time_ms,
        )
