from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional
import inspect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_limit import ExecutionLimit, ExecutionLimitScope


PLATFORM_SCOPE_REF = "global"


# Last-resort values for an incomplete database.  The platform/global row is
# the operator-owned default; these values only make a new or partially
# migrated installation safe until that row is configured.
CODE_DEFAULT_EXECUTION_LIMITS = {
    "llm_input_tokens_max": 16_000,
    "llm_output_tokens_max": 4_096,
    "llm_context_window_max": 16_384,
    "llm_timeout_s": 30,
    "plan_revisions_max": 25,
    "task_attempts_total_max": 3,
    "agent_runs_total_max": 25,
    "llm_calls_total_max": 100,
    "tool_calls_total_max": 50,
    "tokens_total_max": 32_000,
    "execution_wall_time_ms_max": 300_000,
    "run_ttl_ms": 600_000,
    "planner_llm_calls_max": 12,
    "planner_retries_max": 3,
    "planner_tokens_total_max": 12_000,
    "planner_execution_wall_time_ms_max": 300_000,
    "agent_attempts_max": 3,
    "agent_llm_calls_max": 10,
    "agent_tool_calls_max": 50,
    "agent_tokens_total_max": 16_000,
    "agent_execution_wall_time_ms_max": 300_000,
    "max_parallel_tasks": 1,
}


@dataclass(frozen=True)
class ExecutionLimitsPayload:
    llm_input_tokens_max: Optional[int] = None
    llm_output_tokens_max: Optional[int] = None
    llm_context_window_max: Optional[int] = None
    llm_timeout_s: Optional[int] = None
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


@dataclass(frozen=True)
class ResolvedExecutionLimits:
    """Effective limits plus the origin of every value for operator traces."""

    values: ExecutionLimitsPayload
    sources: Mapping[str, str]


class ExecutionLimitsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_effective(
        self,
        *,
        scope_type: str,
        scope_ref: Optional[str],
    ) -> ExecutionLimitsPayload:
        return (await self.resolve(scope_type=scope_type, scope_ref=scope_ref)).values

    async def resolve(
        self,
        *,
        scope_type: str,
        scope_ref: Optional[str],
        override: Optional[dict] = None,
    ) -> ResolvedExecutionLimits:
        own = await self._get_scope(scope_type=scope_type, scope_ref=scope_ref)
        platform = await self._get_scope(
            scope_type=ExecutionLimitScope.PLATFORM,
            scope_ref=PLATFORM_SCOPE_REF,
        )
        values: dict[str, int] = {}
        sources: dict[str, str] = {}
        for field in ExecutionLimitsPayload.__dataclass_fields__:
            own_value = self._positive_value(getattr(own, field, None) if own is not None else None)
            platform_value = self._positive_value(
                getattr(platform, field, None) if platform is not None else None
            )
            if own_value is not None:
                values[field] = own_value
                sources[field] = "entity"
            elif platform_value is not None:
                values[field] = platform_value
                sources[field] = "platform"
            else:
                values[field] = CODE_DEFAULT_EXECUTION_LIMITS[field]
                sources[field] = "code"

        for field, raw_value in (override or {}).items():
            if field not in values:
                continue
            value = self._positive_value(raw_value)
            if value is not None:
                values[field] = value
                sources[field] = "sandbox"
        return ResolvedExecutionLimits(
            values=ExecutionLimitsPayload(**values),
            sources=sources,
        )

    async def get_scope(self, *, scope_type: str, scope_ref: Optional[str]) -> Optional[ExecutionLimit]:
        return await self._get_scope(scope_type=scope_type, scope_ref=scope_ref)

    async def upsert_scope(
        self,
        *,
        scope_type: str,
        scope_ref: Optional[str],
        payload: ExecutionLimitsPayload,
        fields: Optional[set[str]] = None,
    ) -> ExecutionLimit:
        normalized_ref = self._normalize_scope_ref(scope_type, scope_ref)
        row = await self._get_scope(scope_type=scope_type, scope_ref=normalized_ref)
        if row is None:
            row = ExecutionLimit(scope_type=scope_type, scope_ref=normalized_ref)
            self.session.add(row)
        for field in fields or set(payload.__dataclass_fields__.keys()):
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
    def _positive_value(value: object) -> Optional[int]:
        try:
            normalized = int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return normalized if normalized is not None and normalized > 0 else None


def apply_limits_override(
    base: ExecutionLimitsPayload,
    override: Optional[dict],
) -> ExecutionLimitsPayload:
    if not isinstance(override, dict) or not override:
        return base

    values = dict(base.__dict__)
    for field, raw_value in override.items():
        if field not in values:
            continue
        value = ExecutionLimitsService._positive_value(raw_value)
        if value is not None:
            values[field] = value
    return ExecutionLimitsPayload(**values)
