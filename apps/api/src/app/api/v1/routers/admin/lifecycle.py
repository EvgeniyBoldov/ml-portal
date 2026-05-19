from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.core.security import UserCtx
from app.schemas.lifecycle import DependencyGraphResponse, LifecycleReportResponse
from app.services.lifecycle_admin_service import LifecycleAdminService

router = APIRouter(tags=["lifecycle"])
LifecycleKind = Literal["tenant", "user", "collection", "agent", "rbac_rule"]


class SoftDeleteBody(BaseModel):
    reason: str | None = None
    retention_days: int | None = Field(default=None, ge=0, le=3650)


@router.get("/{kind}/{entity_id}/dependencies", response_model=DependencyGraphResponse)
async def get_dependencies(
    kind: LifecycleKind,
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    _: UserCtx = Depends(require_admin),
):
    svc = LifecycleAdminService(session)
    try:
        dependencies = await svc.get_dependencies(kind, entity_id)
        return {"kind": kind, "entity_id": str(entity_id), "dependencies": dependencies}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{kind}/{entity_id}", response_model=LifecycleReportResponse)
async def delete_entity(
    kind: LifecycleKind,
    entity_id: uuid.UUID,
    mode: Literal["soft", "hard"] = Query(default="soft"),
    force: bool = Query(default=False),
    body: SoftDeleteBody | None = None,
    session: AsyncSession = Depends(db_uow),
    admin_user: UserCtx = Depends(require_admin),
):
    svc = LifecycleAdminService(session)
    try:
        if mode == "soft":
            report = await svc.soft_delete(
                kind,
                entity_id,
                actor_id=uuid.UUID(str(admin_user.id)) if admin_user.id else None,
                reason=(body.reason if body else None),
                retention_days=(body.retention_days if body else None),
            )
        else:
            deps = await svc.get_dependencies(kind, entity_id)
            blocking = [item for item in deps if item.get("will_be") == "blocker"]
            if blocking and not force:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "hard_delete_requires_force",
                        "dependencies": blocking,
                    },
                )
            report = await svc.hard_delete(kind, entity_id)
    except ValueError as exc:
        if str(exc) == "not_found":
            raise HTTPException(status_code=404, detail="not_found") from exc
        if str(exc) == "cannot_delete_default_tenant":
            raise HTTPException(status_code=409, detail="cannot_delete_default_tenant") from exc
        if str(exc) == "platform_default_tenant_not_found":
            raise HTTPException(status_code=409, detail="platform_default_tenant_not_found") from exc
        if str(exc) == "last_admin":
            raise HTTPException(status_code=409, detail="last_admin") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "kind": report.kind,
        "entity_id": report.entity_id,
        "mode": report.mode,
        "lifecycle_status": report.lifecycle_status,
        "details": report.details,
        "migrated": report.migrated,
        "cascaded": report.cascaded,
        "set_null": report.set_null,
        "rbac_rules_removed": report.rbac_rules_removed,
        "renamed": report.renamed,
    }


@router.post("/{kind}/{entity_id}/restore", response_model=LifecycleReportResponse)
async def restore_entity(
    kind: LifecycleKind,
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    _: UserCtx = Depends(require_admin),
):
    svc = LifecycleAdminService(session)
    try:
        report = await svc.restore(kind, entity_id)
    except ValueError as exc:
        if str(exc) == "not_found":
            raise HTTPException(status_code=404, detail="not_found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "kind": report.kind,
        "entity_id": report.entity_id,
        "mode": report.mode,
        "lifecycle_status": report.lifecycle_status,
        "details": report.details,
        "migrated": report.migrated,
        "cascaded": report.cascaded,
        "set_null": report.set_null,
        "rbac_rules_removed": report.rbac_rules_removed,
        "renamed": report.renamed,
    }
