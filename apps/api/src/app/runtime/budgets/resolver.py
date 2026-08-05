from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.runtime_limits_service import RuntimeLimitsService
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
        self._limits_service = RuntimeLimitsService(session)

    async def resolve_run(self, platform_config: Dict[str, Any], sandbox_overrides: Optional[Dict[str, Any]] = None) -> RunLimits:
        limits = await self._limits_service.resolve_runtime((sandbox_overrides or {}).get("runtime_limits"))
        return RunLimits(
            # The existing graph store consumes plan revisions including the
            # initial plan, hence max_replans becomes +1 at this boundary.
            plan_revisions=_as_optional_int((limits.max_replans or 0) + 1),
            task_attempts=_as_optional_int(limits.max_task_executions),
            wall_time_ms=_as_optional_int(limits.wall_time_ms_max),
            max_parallel_tasks=_as_optional_int(limits.max_parallel_tasks) or 1,
        )

    async def resolve_orchestrator(self, role: str, sandbox_overrides: Optional[Dict[str, Any]] = None) -> EntityLimits:
        role_key = (role or "").strip().lower()
        resolution = await self._limits_service.resolve_orchestrator(
            role_key,
            ((sandbox_overrides or {}).get("orchestrator_limits") or {}).get(role_key),
        )
        limits = resolution.effective
        return EntityLimits(
            llm_calls=_as_optional_int(limits.llm_calls_max),
            wall_time_ms=_as_optional_int(limits.wall_time_ms_max),
        )
