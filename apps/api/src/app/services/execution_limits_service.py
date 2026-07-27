from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import inspect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_limit import ExecutionLimit, ExecutionLimitScope


PLATFORM_SCOPE_REF = "global"


@dataclass(frozen=True)
class ExecutionLimitsPayload:
    llm_input_tokens_max: Optional[int] = None
    llm_output_tokens_max: Optional[int] = None
    llm_context_window_max: Optional[int] = None
    plan_revisions_max: Optional[int] = None
    task_attempts_total_max: Optional[int] = None
    agent_runs_total_max: Optional[int] = None
    llm_calls_total_max: Optional[int] = None
    tool_calls_total_max: Optional[int] = None
    tokens_total_max: Optional[int] = None
    execution_wall_time_ms_max: Optional[int] = None
    run_ttl_ms: Optional[int] = None
    planner_llm_calls_max: Optional[int] = None
    planner_retries_max: Optional[int] = None
    planner_tokens_total_max: Optional[int] = None
    planner_execution_wall_time_ms_max: Optional[int] = None
    agent_attempts_max: Optional[int] = None
    agent_llm_calls_max: Optional[int] = None
    agent_tool_calls_max: Optional[int] = None
    agent_tokens_total_max: Optional[int] = None
    agent_execution_wall_time_ms_max: Optional[int] = None
    max_parallel_tasks: Optional[int] = None


class ExecutionLimitsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_effective(
        self,
        *,
        scope_type: str,
        scope_ref: Optional[str],
    ) -> ExecutionLimitsPayload:
        own = await self._get_scope(scope_type=scope_type, scope_ref=scope_ref)
        platform = await self._get_scope(
            scope_type=ExecutionLimitScope.PLATFORM,
            scope_ref=PLATFORM_SCOPE_REF,
        )
        return ExecutionLimitsPayload(
            llm_input_tokens_max=self._pick(own, platform, "llm_input_tokens_max"),
            llm_output_tokens_max=self._pick(own, platform, "llm_output_tokens_max"),
            llm_context_window_max=self._pick(own, platform, "llm_context_window_max"),
            **{field: self._pick(own, platform, field) for field in ExecutionLimitsPayload.__dataclass_fields__ if field not in {"llm_input_tokens_max", "llm_output_tokens_max", "llm_context_window_max"}},
        )

    async def get_scope(self, *, scope_type: str, scope_ref: Optional[str]) -> Optional[ExecutionLimit]:
        return await self._get_scope(scope_type=scope_type, scope_ref=scope_ref)

    async def upsert_scope(
        self,
        *,
        scope_type: str,
        scope_ref: Optional[str],
        payload: ExecutionLimitsPayload,
    ) -> ExecutionLimit:
        normalized_ref = self._normalize_scope_ref(scope_type, scope_ref)
        row = await self._get_scope(scope_type=scope_type, scope_ref=normalized_ref)
        if row is None:
            row = ExecutionLimit(scope_type=scope_type, scope_ref=normalized_ref)
            self.session.add(row)
        for field in payload.__dataclass_fields__.keys():
            setattr(row, field, getattr(payload, field))
        await self.session.flush()
        return row

    async def _get_scope(self, *, scope_type: str, scope_ref: Optional[str]) -> Optional[ExecutionLimit]:
        normalized_ref = self._normalize_scope_ref(scope_type, scope_ref)
        stmt = (
            select(ExecutionLimit)
            .where(ExecutionLimit.scope_type == scope_type)
            .where(ExecutionLimit.scope_ref == normalized_ref)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        scalars_obj = result.scalars()
        if inspect.isawaitable(scalars_obj):
            scalars_obj = await scalars_obj
        first_obj = scalars_obj.first()
        if inspect.isawaitable(first_obj):
            first_obj = await first_obj
        return first_obj

    @staticmethod
    def _normalize_scope_ref(scope_type: str, scope_ref: Optional[str]) -> str:
        if scope_type == ExecutionLimitScope.PLATFORM:
            return PLATFORM_SCOPE_REF
        return str(scope_ref or "").strip()

    @staticmethod
    def _pick(own: Optional[ExecutionLimit], platform: Optional[ExecutionLimit], field: str) -> Optional[int]:
        own_val = getattr(own, field, None) if own is not None else None
        if own_val is not None:
            return own_val
        return getattr(platform, field, None) if platform is not None else None


def apply_limits_override(
    base: ExecutionLimitsPayload,
    override: Optional[dict],
) -> ExecutionLimitsPayload:
    if not isinstance(override, dict) or not override:
        return base

    def _coerce(value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            n = int(value)
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    return ExecutionLimitsPayload(
        llm_input_tokens_max=_coerce(override.get("llm_input_tokens_max")) if "llm_input_tokens_max" in override else base.llm_input_tokens_max,
        llm_output_tokens_max=_coerce(override.get("llm_output_tokens_max")) if "llm_output_tokens_max" in override else base.llm_output_tokens_max,
        llm_context_window_max=_coerce(override.get("llm_context_window_max")) if "llm_context_window_max" in override else base.llm_context_window_max,
        **{field: _coerce(override[field]) if field in override else getattr(base, field) for field in ExecutionLimitsPayload.__dataclass_fields__ if field not in {"llm_input_tokens_max", "llm_output_tokens_max", "llm_context_window_max"}},
    )
