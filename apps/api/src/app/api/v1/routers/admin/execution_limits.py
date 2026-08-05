"""Administrative API for runtime and actor execution limits."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.execution_limit import ActorExecutionLimitScope
from app.schemas.runtime_limits import (
    ActorLimitsResponse,
    ActorLimitsUpdate,
    OrchestratorLimitsUpdate,
    RuntimeLimitsResponse,
    RuntimeLimitsUpdate,
)
from app.services.runtime_limits_service import ActorLimits, RuntimeLimits, RuntimeLimitsService

router = APIRouter(tags=["execution-limits"])


def _actor_response(resolution) -> ActorLimitsResponse:
    return ActorLimitsResponse(
        own=ActorLimitsUpdate(**asdict(resolution.own)),
        effective=ActorLimitsUpdate(**asdict(resolution.effective)),
        sources=dict(resolution.sources),
    )


@router.get("/runtime", response_model=RuntimeLimitsResponse)
async def get_runtime_limits(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    limits = await RuntimeLimitsService(db).resolve_runtime()
    return RuntimeLimitsResponse(**asdict(limits), sources={key: "runtime" for key in asdict(limits)})


@router.patch("/runtime", response_model=RuntimeLimitsResponse)
async def update_runtime_limits(data: RuntimeLimitsUpdate, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    service = RuntimeLimitsService(db)
    await service.update_runtime(RuntimeLimits(**data.model_dump()), set(data.model_fields_set))
    await db.commit()
    limits = await service.resolve_runtime()
    return RuntimeLimitsResponse(**asdict(limits), sources={key: "runtime" for key in asdict(limits)})


@router.get("/defaults/agents", response_model=ActorLimitsResponse)
async def get_agent_defaults(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return _actor_response(await RuntimeLimitsService(db).resolve_agent_defaults())


@router.patch("/defaults/agents", response_model=ActorLimitsResponse)
async def update_agent_defaults(data: ActorLimitsUpdate, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    service = RuntimeLimitsService(db)
    await service.update_actor(ActorExecutionLimitScope.AGENT_DEFAULT, "global", ActorLimits(**data.model_dump()), set(data.model_fields_set))
    await db.commit()
    return _actor_response(await service.resolve_agent_defaults())


@router.get("/defaults/orchestrators", response_model=ActorLimitsResponse)
async def get_orchestrator_defaults(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return _actor_response(await RuntimeLimitsService(db).resolve_orchestrator_defaults())


@router.patch("/defaults/orchestrators", response_model=ActorLimitsResponse)
async def update_orchestrator_defaults(data: OrchestratorLimitsUpdate, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    service = RuntimeLimitsService(db)
    await service.update_actor(ActorExecutionLimitScope.ORCHESTRATOR_DEFAULT, "global", ActorLimits(**data.model_dump()), set(data.model_fields_set))
    await db.commit()
    return _actor_response(await service.resolve_orchestrator_defaults())


@router.get("/agents/{agent_slug}", response_model=ActorLimitsResponse)
async def get_agent_limits(agent_slug: str, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return _actor_response(await RuntimeLimitsService(db).resolve_agent(agent_slug))


@router.patch("/agents/{agent_slug}", response_model=ActorLimitsResponse)
async def update_agent_limits(agent_slug: str, data: ActorLimitsUpdate, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    service = RuntimeLimitsService(db)
    await service.update_actor(ActorExecutionLimitScope.AGENT, agent_slug, ActorLimits(**data.model_dump()), set(data.model_fields_set))
    await db.commit()
    return _actor_response(await service.resolve_agent(agent_slug))


@router.get("/orchestrators/{role}", response_model=ActorLimitsResponse)
async def get_orchestrator_limits(role: str, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return _actor_response(await RuntimeLimitsService(db).resolve_orchestrator(role))


@router.patch("/orchestrators/{role}", response_model=ActorLimitsResponse)
async def update_orchestrator_limits(role: str, data: OrchestratorLimitsUpdate, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    service = RuntimeLimitsService(db)
    try:
        await service.update_actor(ActorExecutionLimitScope.ORCHESTRATOR_ROLE, role, ActorLimits(**data.model_dump()), set(data.model_fields_set))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return _actor_response(await service.resolve_orchestrator(role))
