"""
Collections tenant-level endpoints.
List and get collections for the current tenant (read-only).
CRUD operations are in admin router.
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.core.config import is_local
from app.models.tenant import UserTenants, Tenants
from app.services.collection_service import CollectionService

logger = get_logger(__name__)

router = APIRouter()


async def _build_collection_response(
    service: CollectionService,
    collection,
) -> CollectionResponse:
    snapshot = await service.sync_collection_status(collection, persist=False)
    return CollectionResponse(
        id=collection.id,
        collection_type=collection.collection_type,
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        fields=collection.fields,
        status=snapshot["status"],
        status_details=snapshot["details"],
        total_rows=collection.total_rows or 0,
        is_active=collection.is_active,
        has_vector_search=collection.has_vector_search,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
    )


async def _resolve_user_tenants(
    session: AsyncSession,
    user: UserCtx,
) -> list[uuid.UUID]:
    resolved: list[uuid.UUID] = []
    for raw_tenant_id in (user.tenant_ids or []):
        try:
            resolved.append(uuid.UUID(str(raw_tenant_id)))
        except (TypeError, ValueError):
            continue

    if resolved:
        return resolved

    try:
        user_id = uuid.UUID(str(user.id))
    except (TypeError, ValueError):
        return []

    result = await session.execute(
        select(UserTenants.tenant_id)
        .where(UserTenants.user_id == user_id)
        .order_by(UserTenants.is_default.desc())
    )
    db_tenants = [row[0] for row in result.all() if row[0] is not None]
    if db_tenants:
        user.tenant_ids = [str(tid) for tid in db_tenants]
        return db_tenants

    if is_local():
        fallback = await session.execute(
            select(Tenants.id)
            .where(Tenants.is_active.is_(True))
            .order_by(Tenants.created_at.asc())
            .limit(1)
        )
        tenant_id = fallback.scalar_one_or_none()
        if tenant_id:
            user.tenant_ids = [str(tenant_id)]
            return [tenant_id]

    return []


async def _resolve_requested_tenant_id(
    session: AsyncSession,
    user: UserCtx,
    tenant_id: Optional[uuid.UUID],
) -> uuid.UUID:
    """
    Resolve tenant scope for tenant-level collection endpoints.

    These routes are intentionally tenant-scoped even for admins.
    Admin-wide access belongs to the dedicated admin router.
    """
    user_tenant_ids = await _resolve_user_tenants(session, user)

    if tenant_id:
        if user.role != "admin" and user_tenant_ids and tenant_id not in user_tenant_ids:
            raise HTTPException(status_code=403, detail="Access denied")
        return tenant_id

    if user_tenant_ids:
        return user_tenant_ids[0]

    if not user_tenant_ids:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    raise HTTPException(status_code=400, detail="Unable to resolve tenant")


class CollectionResponse(BaseModel):
    id: uuid.UUID
    collection_type: str = "table"
    slug: str
    name: str
    description: Optional[str]
    fields: List[dict]
    status: str
    status_details: Optional[dict] = None
    total_rows: int
    is_active: bool
    has_vector_search: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CollectionListResponse(BaseModel):
    items: List[CollectionResponse]
    total: int


@router.get("/", response_model=CollectionListResponse)
async def list_collections(
    active_only: bool = True,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    """List collections for the resolved tenant scope."""
    service = CollectionService(session)
    resolved_tenant_id = await _resolve_requested_tenant_id(session, user, tenant_id)
    collections = await service.list_collections(resolved_tenant_id, active_only=active_only)

    items = [await _build_collection_response(service, c) for c in collections]

    return CollectionListResponse(items=items, total=len(items))


@router.get("/{slug}", response_model=CollectionResponse)
async def get_collection(
    slug: str,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    """Get a collection by slug inside the resolved tenant scope."""
    service = CollectionService(session)
    resolved_tenant_id = await _resolve_requested_tenant_id(session, user, tenant_id)
    collection = await service.get_by_slug(resolved_tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    return await _build_collection_response(service, collection)
