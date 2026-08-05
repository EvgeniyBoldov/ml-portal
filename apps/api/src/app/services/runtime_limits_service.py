"""Resolution of runtime guards and sparse actor defaults/overrides."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_limit import (
    ActorExecutionLimit,
    ActorExecutionLimitScope,
    RuntimeExecutionLimits,
)


GLOBAL = "global"
RUNTIME_CODE_DEFAULTS = {
    "wall_time_ms_max": 300_000,
    "max_parallel_tasks": 1,
    "max_replans": 3,
    "max_task_executions": 100,
}
AGENT_CODE_DEFAULTS = {"llm_calls_max": 10, "tool_calls_max": 50, "wall_time_ms_max": 300_000}
ORCHESTRATOR_CODE_DEFAULTS = {"llm_calls_max": 12, "tool_calls_max": None, "wall_time_ms_max": 300_000}


@dataclass(frozen=True)
class RuntimeLimits:
    wall_time_ms_max: Optional[int] = None
    max_parallel_tasks: Optional[int] = None
    max_replans: Optional[int] = None
    max_task_executions: Optional[int] = None


@dataclass(frozen=True)
class ActorLimits:
    llm_calls_max: Optional[int] = None
    tool_calls_max: Optional[int] = None
    wall_time_ms_max: Optional[int] = None


@dataclass(frozen=True)
class ResolvedActorLimits:
    own: ActorLimits
    effective: ActorLimits
    sources: Mapping[str, str]


class RuntimeLimitsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_runtime(self, override: Optional[dict] = None) -> RuntimeLimits:
        row = await self._runtime_row()
        values = self._resolve_values(RUNTIME_CODE_DEFAULTS, row, override, allow_zero={"max_replans"})
        return RuntimeLimits(**values)

    async def update_runtime(self, values: RuntimeLimits, fields: set[str]) -> RuntimeExecutionLimits:
        row = await self._runtime_row()
        if row is None:
            row = RuntimeExecutionLimits(scope_ref=GLOBAL)
            self.session.add(row)
        for field in fields:
            setattr(row, field, getattr(values, field))
        await self.session.flush()
        return row

    async def resolve_agent(self, slug: str, override: Optional[dict] = None) -> ResolvedActorLimits:
        return await self._resolve_actor(ActorExecutionLimitScope.AGENT, slug, AGENT_CODE_DEFAULTS, override)

    async def resolve_orchestrator(self, role: str, override: Optional[dict] = None) -> ResolvedActorLimits:
        return await self._resolve_actor(ActorExecutionLimitScope.ORCHESTRATOR_ROLE, role, ORCHESTRATOR_CODE_DEFAULTS, override)

    async def resolve_agent_defaults(self) -> ResolvedActorLimits:
        return await self._resolve_default(ActorExecutionLimitScope.AGENT_DEFAULT, AGENT_CODE_DEFAULTS)

    async def resolve_orchestrator_defaults(self) -> ResolvedActorLimits:
        return await self._resolve_default(ActorExecutionLimitScope.ORCHESTRATOR_DEFAULT, ORCHESTRATOR_CODE_DEFAULTS)

    async def update_actor(self, scope_type: str, scope_ref: str, values: ActorLimits, fields: set[str]) -> ActorExecutionLimit:
        self._validate_scope(scope_type, values, fields)
        row = await self._actor_row(scope_type, scope_ref)
        if row is None:
            row = ActorExecutionLimit(scope_type=scope_type, scope_ref=scope_ref)
            self.session.add(row)
        for field in fields:
            setattr(row, field, getattr(values, field))
        await self.session.flush()
        return row

    async def _resolve_default(self, scope_type: str, code_defaults: dict) -> ResolvedActorLimits:
        row = await self._actor_row(scope_type, GLOBAL)
        own = self._actor_from_row(row)
        effective_values = self._resolve_values(code_defaults, row, None)
        sources = {key: "default" if getattr(own, key) is not None else "code" for key in asdict(own)}
        return ResolvedActorLimits(own=own, effective=ActorLimits(**effective_values), sources=sources)

    async def _resolve_actor(self, scope_type: str, scope_ref: str, code_defaults: dict, override: Optional[dict]) -> ResolvedActorLimits:
        own_row = await self._actor_row(scope_type, scope_ref)
        default_scope = ActorExecutionLimitScope.AGENT_DEFAULT if scope_type == ActorExecutionLimitScope.AGENT else ActorExecutionLimitScope.ORCHESTRATOR_DEFAULT
        default_row = await self._actor_row(default_scope, GLOBAL)
        own = self._actor_from_row(own_row)
        effective: dict[str, Optional[int]] = {}
        sources: dict[str, str] = {}
        for field, fallback in code_defaults.items():
            own_value = getattr(own_row, field, None) if own_row else None
            default_value = getattr(default_row, field, None) if default_row else None
            if self._valid(own_value):
                effective[field], sources[field] = int(own_value), "entity"
            elif self._valid(default_value):
                effective[field], sources[field] = int(default_value), "default"
            else:
                effective[field], sources[field] = fallback, "code"
            if isinstance(override, dict) and self._valid(override.get(field)):
                effective[field], sources[field] = int(override[field]), "sandbox"
        return ResolvedActorLimits(own=own, effective=ActorLimits(**effective), sources=sources)

    async def _runtime_row(self) -> Optional[RuntimeExecutionLimits]:
        return (await self.session.execute(select(RuntimeExecutionLimits).where(RuntimeExecutionLimits.scope_ref == GLOBAL))).scalar_one_or_none()

    async def _actor_row(self, scope_type: str, scope_ref: str) -> Optional[ActorExecutionLimit]:
        return (await self.session.execute(
            select(ActorExecutionLimit).where(ActorExecutionLimit.scope_type == scope_type, ActorExecutionLimit.scope_ref == scope_ref.strip())
        )).scalar_one_or_none()

    @staticmethod
    def _actor_from_row(row: Optional[ActorExecutionLimit]) -> ActorLimits:
        return ActorLimits(**{field: getattr(row, field, None) if row else None for field in ActorLimits.__dataclass_fields__})

    @staticmethod
    def _resolve_values(
        defaults: dict,
        row: object,
        override: Optional[dict],
        *,
        allow_zero: set[str] | None = None,
    ) -> dict:
        values: dict[str, Optional[int]] = {}
        for field, fallback in defaults.items():
            candidate = getattr(row, field, None) if row else None
            valid = RuntimeLimitsService._valid(candidate, allow_zero=field in (allow_zero or set()))
            values[field] = int(candidate) if valid else fallback
            if isinstance(override, dict) and RuntimeLimitsService._valid(override.get(field), allow_zero=field in (allow_zero or set())):
                values[field] = int(override[field])
        return values

    @staticmethod
    def _valid(value: object, *, allow_zero: bool = False) -> bool:
        return isinstance(value, int) and value >= (0 if allow_zero else 1)

    @staticmethod
    def _validate_scope(scope_type: str, values: ActorLimits, fields: set[str]) -> None:
        valid = {ActorExecutionLimitScope.AGENT_DEFAULT, ActorExecutionLimitScope.ORCHESTRATOR_DEFAULT, ActorExecutionLimitScope.AGENT, ActorExecutionLimitScope.ORCHESTRATOR_ROLE}
        if scope_type not in valid:
            raise ValueError("Unknown actor limits scope")
        if scope_type in {ActorExecutionLimitScope.ORCHESTRATOR_DEFAULT, ActorExecutionLimitScope.ORCHESTRATOR_ROLE} and "tool_calls_max" in fields:
            raise ValueError("tool_calls_max is only valid for agents")
