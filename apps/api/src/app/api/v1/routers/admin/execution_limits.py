from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.execution_limit import ExecutionLimitScope
from app.schemas.execution_limits import ExecutionLimitsResponse, ExecutionLimitsUpdate
from app.services.execution_limits_service import (
    ExecutionLimitsPayload,
    ExecutionLimitsService,
    PLATFORM_SCOPE_REF,
)

router = APIRouter(tags=["execution-limits"])


def _payload_from_update(data: ExecutionLimitsUpdate) -> ExecutionLimitsPayload:
    return ExecutionLimitsPayload(**data.model_dump(exclude_unset=True))


@router.get("/platform", response_model=ExecutionLimitsResponse)
async def get_platform_limits(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = ExecutionLimitsService(db)
    row = await service.get_scope(
        scope_type=ExecutionLimitScope.PLATFORM,
        scope_ref=PLATFORM_SCOPE_REF,
    )
    if row is not None:
        return ExecutionLimitsResponse.model_validate(row)
    effective = await service.get_effective(scope_type=ExecutionLimitScope.PLATFORM, scope_ref=PLATFORM_SCOPE_REF)
    return ExecutionLimitsResponse(scope_type=ExecutionLimitScope.PLATFORM, scope_ref=PLATFORM_SCOPE_REF, **effective.__dict__)


@router.patch("/platform", response_model=ExecutionLimitsResponse)
async def update_platform_limits(
    data: ExecutionLimitsUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = ExecutionLimitsService(db)
    row = await service.upsert_scope(
        scope_type=ExecutionLimitScope.PLATFORM,
        scope_ref=PLATFORM_SCOPE_REF,
        payload=_payload_from_update(data),
    )
    await db.commit()
    return ExecutionLimitsResponse.model_validate(row)


@router.get("/agents/{agent_slug}", response_model=ExecutionLimitsResponse)
async def get_agent_limits(
    agent_slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = ExecutionLimitsService(db)
    row = await service.get_scope(
        scope_type=ExecutionLimitScope.AGENT,
        scope_ref=agent_slug,
    )
    if row is not None:
        return ExecutionLimitsResponse.model_validate(row)
    effective = await service.get_effective(scope_type=ExecutionLimitScope.AGENT, scope_ref=agent_slug)
    return ExecutionLimitsResponse(scope_type=ExecutionLimitScope.AGENT, scope_ref=agent_slug, **effective.__dict__)


@router.patch("/agents/{agent_slug}", response_model=ExecutionLimitsResponse)
async def update_agent_limits(
    agent_slug: str,
    data: ExecutionLimitsUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = ExecutionLimitsService(db)
    row = await service.upsert_scope(
        scope_type=ExecutionLimitScope.AGENT,
        scope_ref=agent_slug,
        payload=_payload_from_update(data),
    )
    await db.commit()
    return ExecutionLimitsResponse.model_validate(row)


@router.get("/orchestrators/{role}", response_model=ExecutionLimitsResponse)
async def get_orchestrator_limits(
    role: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    role_key = (role or "").strip().lower()
    service = ExecutionLimitsService(db)
    row = await service.get_scope(
        scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
        scope_ref=role_key,
    )
    if row is not None:
        return ExecutionLimitsResponse.model_validate(row)
    effective = await service.get_effective(scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE, scope_ref=role_key)
    return ExecutionLimitsResponse(scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE, scope_ref=role_key, **effective.__dict__)


@router.patch("/orchestrators/{role}", response_model=ExecutionLimitsResponse)
async def update_orchestrator_limits(
    role: str,
    data: ExecutionLimitsUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    role_key = (role or "").strip().lower()
    service = ExecutionLimitsService(db)
    row = await service.upsert_scope(
        scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
        scope_ref=role_key,
        payload=_payload_from_update(data),
    )
    await db.commit()
    return ExecutionLimitsResponse.model_validate(row)
