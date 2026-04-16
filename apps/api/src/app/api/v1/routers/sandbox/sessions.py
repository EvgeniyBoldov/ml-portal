"""Sandbox sessions CRUD — list, create, get, update, delete."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.sandbox import (
    SandboxOverrideResponse,
    SandboxRunListItem,
    SandboxSessionCreate,
    SandboxSessionDetailResponse,
    SandboxSessionListItem,
    SandboxSessionUpdate,
)
from app.services.sandbox_service import SandboxService

from .helpers import check_session_owner, get_owner_email, tenant_uuid, user_uuid

router = APIRouter()


@router.get("/sessions", response_model=list[SandboxSessionListItem])
async def list_sessions(
    status: Optional[str] = Query(None, description="Filter by status: active | archived"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """List sandbox sessions for current tenant."""
    svc = SandboxService(db)
    rows, _ = await svc.list_sessions_with_counts(await tenant_uuid(db, user), status, skip, limit)

    items = []
    for s, overrides_count, runs_count in rows:
        email = await get_owner_email(db, s.owner_id)
        items.append(SandboxSessionListItem(
            id=s.id,
            owner_id=s.owner_id,
            owner_email=email,
            name=s.name,
            status=s.status,
            ttl_days=s.ttl_days,
            expires_at=s.expires_at,
            last_activity_at=s.last_activity_at,
            overrides_count=overrides_count,
            runs_count=runs_count,
            created_at=s.created_at,
        ))
    return items


@router.post("/sessions", response_model=SandboxSessionDetailResponse, status_code=201)
async def create_session(
    data: SandboxSessionCreate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Create a new sandbox session."""
    svc = SandboxService(db)
    session = await svc.create_session(
        owner_id=user_uuid(user),
        tenant_id=await tenant_uuid(db, user),
        name=data.name,
        ttl_days=data.ttl_days,
    )
    await db.commit()
    await db.refresh(session)

    email = await get_owner_email(db, session.owner_id)
    return SandboxSessionDetailResponse(
        id=session.id,
        owner_id=session.owner_id,
        owner_email=email,
        name=session.name,
        status=session.status,
        ttl_days=session.ttl_days,
        expires_at=session.expires_at,
        last_activity_at=session.last_activity_at,
        overrides=[],
        runs=[],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions/{session_id}", response_model=SandboxSessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Get sandbox session detail. Non-owners get read-only view."""
    svc = SandboxService(db)
    session = await svc.get_session_detail(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    email = await get_owner_email(db, session.owner_id)

    overrides = [
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
        for o in session.overrides
    ]

    runs = []
    for r in session.runs:
        steps_count = await svc.get_run_steps_count(r.id)
        runs.append(SandboxRunListItem(
            id=r.id,
            branch_id=r.branch_id,
            snapshot_id=r.snapshot_id,
            parent_run_id=r.parent_run_id,
            request_text=r.request_text,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            steps_count=steps_count,
        ))

    return SandboxSessionDetailResponse(
        id=session.id,
        owner_id=session.owner_id,
        owner_email=email,
        name=session.name,
        status=session.status,
        ttl_days=session.ttl_days,
        expires_at=session.expires_at,
        last_activity_at=session.last_activity_at,
        overrides=overrides,
        runs=runs,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.patch("/sessions/{session_id}", response_model=SandboxSessionDetailResponse)
async def update_session(
    session_id: uuid.UUID,
    data: SandboxSessionUpdate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Update session name or TTL. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    session = await svc.update_session(session_id, update_data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()

    # Re-fetch with relations
    return await get_session(session_id, db, user)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Delete sandbox session. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    deleted = await svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()
