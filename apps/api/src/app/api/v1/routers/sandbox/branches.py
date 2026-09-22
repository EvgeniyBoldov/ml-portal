"""Sandbox branches, branch overrides, and snapshots."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.sandbox import (
    SandboxBranchCreate,
    SandboxBranchForkRequest,
    SandboxBranchMemoryResponse,
    SandboxBranchListItem,
    SandboxBranchOverrideResponse,
    SandboxBranchOverrideUpsert,
    SandboxSnapshotResponse,
)
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.service import MemoryService
from app.runtime.memory.sandbox_overlays import (
    inspector_payload,
)
from app.models.chat import Chats
from app.models.glossary import GlossaryEntry
from app.models.memory import MemoryItem, MemoryItemSource
from app.models.project import Project
from app.services.chat_context_service import ChatContextService
from app.services.chat_visibility import make_sandbox_upload_chat_name
from app.services.sandbox_service import SandboxService
from app.services.sandbox_override_resolver import SandboxOverrideResolver

from .helpers import check_session_owner, tenant_uuid, user_uuid

router = APIRouter()


@router.get("/sessions/{session_id}/branches", response_model=list[SandboxBranchListItem])
async def list_branches(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branches = await svc.list_branches(session_id)
    return [
        SandboxBranchListItem(
            id=b.id,
            session_id=b.session_id,
            parent_branch_id=b.parent_branch_id,
            parent_run_id=b.parent_run_id,
            name=b.name,
            created_by=b.created_by,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
        for b in branches
    ]


@router.post("/sessions/{session_id}/branches", response_model=SandboxBranchListItem, status_code=201)
async def create_branch(
    session_id: uuid.UUID,
    data: SandboxBranchCreate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branch = await svc.create_branch(
        session_id=session_id,
        user_id=user_uuid(user),
        name=data.name,
        parent_branch_id=data.parent_branch_id,
        parent_run_id=data.parent_run_id,
    )
    await db.commit()
    await db.refresh(branch)
    return SandboxBranchListItem(
        id=branch.id,
        session_id=branch.session_id,
        parent_branch_id=branch.parent_branch_id,
        parent_run_id=branch.parent_run_id,
        name=branch.name,
        created_by=branch.created_by,
        created_at=branch.created_at,
        updated_at=branch.updated_at,
    )


@router.post(
    "/sessions/{session_id}/branches/{branch_id}/fork",
    response_model=SandboxBranchListItem,
    status_code=201,
)
async def fork_branch(
    session_id: uuid.UUID,
    branch_id: uuid.UUID,
    data: SandboxBranchForkRequest,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    source = await svc.get_branch(branch_id)
    if not source or source.session_id != session_id:
        raise HTTPException(status_code=404, detail="Source branch not found")

    branch = await svc.fork_branch(
        session_id=session_id,
        source_branch_id=branch_id,
        user_id=user_uuid(user),
        name=data.name,
        parent_run_id=data.parent_run_id,
        copy_overrides=data.copy_overrides,
    )
    await db.commit()
    await db.refresh(branch)
    return SandboxBranchListItem(
        id=branch.id,
        session_id=branch.session_id,
        parent_branch_id=branch.parent_branch_id,
        parent_run_id=branch.parent_run_id,
        name=branch.name,
        created_by=branch.created_by,
        created_at=branch.created_at,
        updated_at=branch.updated_at,
    )


@router.get(
    "/sessions/{session_id}/branches/{branch_id}/memory",
    response_model=SandboxBranchMemoryResponse,
)
async def get_branch_memory(
    session_id: uuid.UUID,
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Expose the two canonical memory layers for the sandbox navigation.

    This intentionally does not consult legacy branch artifact JSON.  Facts
    remain a branch overlay over durable memory; chat context stays isolated
    by the hidden chat and the selected branch.
    """
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branch = await svc.get_branch(branch_id)
    if not branch or branch.session_id != session_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    owner_id = user_uuid(user)
    tenant_id = await tenant_uuid(db, user)
    snapshot = await MemoryService(fact_store=FactStore(db)).read_snapshot(
        user_id=owner_id, tenant_id=tenant_id, limit=100,
    )
    effective = inspector_payload(snapshot.entries, branch.fact_overrides_json)["effective"]
    hidden_chat = await db.scalar(select(Chats).where(
        Chats.owner_id == owner_id,
        Chats.name == make_sandbox_upload_chat_name(session_id),
    ))
    chat_context = {}
    if hidden_chat is not None:
        chat_context = await ChatContextService(db, None, None).inspect_snapshot(
            chat_id=str(hidden_chat.id), owner_id=str(owner_id), tenant_id=str(tenant_id), branch_id=str(branch_id),
        )
    glossary_rows = list((await db.execute(
        select(GlossaryEntry, Project.key)
        .outerjoin(Project, Project.id == GlossaryEntry.project_id)
        .where(
            GlossaryEntry.is_active.is_(True),
            or_(
                GlossaryEntry.scope == "global",
                (GlossaryEntry.scope == "user") & (GlossaryEntry.user_id == owner_id),
                (GlossaryEntry.scope == "tenant") & (GlossaryEntry.tenant_id == tenant_id),
                GlossaryEntry.scope == "project",
            ),
        ).order_by(GlossaryEntry.canonical_term).limit(100)
    )).all())
    semantic_rows = list((await db.execute(
        select(MemoryItem, Project.key, func.count(MemoryItemSource.id))
        .outerjoin(Project, Project.id == MemoryItem.project_id)
        .outerjoin(MemoryItemSource, MemoryItemSource.memory_item_id == MemoryItem.id)
        .where(MemoryItem.scope == "project", MemoryItem.state == "active")
        .group_by(MemoryItem.id, Project.key)
        .order_by(MemoryItem.updated_at.desc()).limit(100)
    )).all())
    return SandboxBranchMemoryResponse(
        branch_id=branch_id,
        chat_context=chat_context,
        user_facts=list(effective.get("user", [])),
        tenant_facts=list(effective.get("tenant", [])),
        glossary=[{
            "term": entry.canonical_term, "description": entry.description or "",
            "aliases": list(entry.aliases or []), "scope": entry.scope, "project_key": project_key,
            "entity_type": entry.entity_type, "entity_id": entry.entity_id,
            "status": entry.status, "support_count": entry.support_count,
        } for entry, project_key in glossary_rows],
        project_memory=[{
            "subject": item.subject, "content": item.content_text, "item_type": item.item_type,
            "project_key": project_key, "confidence": item.confidence, "state": item.state,
            "applicability": item.applicability, "visibility": item.visibility,
            "last_verified_at": item.last_verified_at, "source_count": source_count,
        } for item, project_key, source_count in semantic_rows],
    )


@router.get(
    "/sessions/{session_id}/branches/{branch_id}/overrides",
    response_model=list[SandboxBranchOverrideResponse],
)
async def list_branch_overrides(
    session_id: uuid.UUID,
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branch = await svc.get_branch(branch_id)
    if not branch or branch.session_id != session_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    items = await svc.list_branch_overrides(branch_id)
    return [
        SandboxBranchOverrideResponse(
            id=i.id,
            branch_id=i.branch_id,
            entity_type=i.entity_type,
            entity_id=i.entity_id,
            field_path=i.field_path,
            value_json=i.value_json,
            value_type=i.value_type,
            updated_by=i.updated_by,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in items
    ]


@router.put(
    "/sessions/{session_id}/branches/{branch_id}/overrides",
    response_model=SandboxBranchOverrideResponse,
)
async def upsert_branch_override(
    session_id: uuid.UUID,
    branch_id: uuid.UUID,
    data: SandboxBranchOverrideUpsert,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    is_allowed, reason = SandboxOverrideResolver.is_override_allowed(
        entity_type=data.entity_type,
        field_path=data.field_path,
    )
    if not is_allowed:
        raise HTTPException(status_code=422, detail=reason)

    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branch = await svc.get_branch(branch_id)
    if not branch or branch.session_id != session_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    item = await svc.upsert_branch_override(
        branch_id=branch_id,
        user_id=user_uuid(user),
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        field_path=data.field_path,
        value_json=data.value_json,
        value_type=data.value_type,
    )
    await db.commit()
    await db.refresh(item)
    return SandboxBranchOverrideResponse(
        id=item.id,
        branch_id=item.branch_id,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        field_path=item.field_path,
        value_json=item.value_json,
        value_type=item.value_type,
        updated_by=item.updated_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/sessions/{session_id}/branches/{branch_id}/overrides", status_code=204)
async def delete_branch_overrides(
    session_id: uuid.UUID,
    branch_id: uuid.UUID,
    entity_type: Optional[str] = Query(default=None),
    field_path: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    branch = await svc.get_branch(branch_id)
    if not branch or branch.session_id != session_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    if entity_type and field_path:
        await svc.delete_branch_override(
            branch_id=branch_id,
            entity_type=entity_type,
            field_path=field_path,
            entity_id=entity_id,
        )
    elif entity_type:
        await svc.delete_branch_overrides_for_entity(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    else:
        await svc.reset_branch_overrides(branch_id=branch_id)

    await db.commit()


@router.get(
    "/sessions/{session_id}/snapshots/{snapshot_id}",
    response_model=SandboxSnapshotResponse,
)
async def get_snapshot(
    session_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    snapshot = await svc.get_snapshot(snapshot_id)
    if not snapshot or snapshot.session_id != session_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return SandboxSnapshotResponse(
        id=snapshot.id,
        session_id=snapshot.session_id,
        branch_id=snapshot.branch_id,
        snapshot_hash=snapshot.snapshot_hash,
        payload_json=snapshot.payload_json,
        created_by=snapshot.created_by,
        created_at=snapshot.created_at,
    )
