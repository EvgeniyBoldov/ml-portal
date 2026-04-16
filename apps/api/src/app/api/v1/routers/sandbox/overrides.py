"""Sandbox session-level overrides — list, create, update, delete, activate, reset."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.sandbox import (
    SandboxOverrideCreate,
    SandboxOverrideResponse,
    SandboxOverrideUpdate,
)
from app.services.sandbox_service import SandboxService

from .helpers import check_session_owner

router = APIRouter()


@router.get(
    "/sessions/{session_id}/overrides",
    response_model=list[SandboxOverrideResponse],
)
async def list_overrides(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """List all overrides for a session."""
    svc = SandboxService(db)
    items = await svc.list_overrides(session_id)
    return [
        SandboxOverrideResponse(
            id=o.id,
            entity_type=o.entity_type,
            entity_id=o.entity_id,
            label=o.label,
            is_active=o.is_active,
            config_snapshot=o.config_snapshot,
            created_at=o.created_at,
            updated_at=o.updated_at,
        )
        for o in items
    ]


@router.post(
    "/sessions/{session_id}/overrides",
    response_model=SandboxOverrideResponse,
    status_code=201,
)
async def create_override(
    session_id: uuid.UUID,
    data: SandboxOverrideCreate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Create phantom version override. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    override = await svc.create_override(
        session_id=session_id,
        entity_type=data.entity_type,
        label=data.label,
        config_snapshot=data.config_snapshot,
        entity_id=data.entity_id,
        is_active=data.is_active,
    )
    await db.commit()
    await db.refresh(override)

    return SandboxOverrideResponse(
        id=override.id,
        entity_type=override.entity_type,
        entity_id=override.entity_id,
        label=override.label,
        is_active=override.is_active,
        config_snapshot=override.config_snapshot,
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


@router.patch(
    "/sessions/{session_id}/overrides/{override_id}",
    response_model=SandboxOverrideResponse,
)
async def update_override(
    session_id: uuid.UUID,
    override_id: uuid.UUID,
    data: SandboxOverrideUpdate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Update an override. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    override = await svc.update_override(override_id, update_data)
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    await db.commit()
    await db.refresh(override)

    return SandboxOverrideResponse(
        id=override.id,
        entity_type=override.entity_type,
        entity_id=override.entity_id,
        label=override.label,
        is_active=override.is_active,
        config_snapshot=override.config_snapshot,
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


@router.delete("/sessions/{session_id}/overrides/{override_id}", status_code=204)
async def delete_override(
    session_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Delete an override. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    deleted = await svc.delete_override(override_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Override not found")
    await db.commit()


@router.post(
    "/sessions/{session_id}/overrides/{override_id}/activate",
    response_model=SandboxOverrideResponse,
)
async def activate_override(
    session_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Set override as active (deactivates siblings). Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    override = await svc.activate_override(override_id)
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    await db.commit()
    await db.refresh(override)

    return SandboxOverrideResponse(
        id=override.id,
        entity_type=override.entity_type,
        entity_id=override.entity_id,
        label=override.label,
        is_active=override.is_active,
        config_snapshot=override.config_snapshot,
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


@router.post("/sessions/{session_id}/reset", status_code=200)
async def reset_overrides(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Reset (delete) all overrides for session. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    count = await svc.reset_overrides(session_id)
    await db.commit()
    return {"deleted": count}
