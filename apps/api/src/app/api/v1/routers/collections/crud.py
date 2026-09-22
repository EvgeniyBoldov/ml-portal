"""
Collections tenant-level endpoints.
List and get collections for the current tenant (read-only).
CRUD operations are in admin router.
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, resolve_active_user_tenant_ids
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.services.collection_service import CollectionService
from app.services.permission_service import PermissionService

logger = get_logger(__name__)

router = APIRouter()


async def _build_collection_response(
    service: CollectionService,
    collection,
) -> CollectionResponse:
    if str(getattr(collection, "collection_type", "") or "") == "template":
        await service.ensure_contract_fields_present(collection)
    snapshot = await service.sync_collection_status(collection, persist=False)
    effective_total_rows = await service.get_effective_total_rows(collection)
    return CollectionResponse(
        id=collection.id,
        collection_type=collection.collection_type,
        slug=collection.slug,
        name=collection.name,
        fields=collection.fields,
        status=snapshot["status"],
        status_details=snapshot["details"],
        total_rows=effective_total_rows,
        is_active=collection.is_active,
        memory_enabled=bool(getattr(collection, "memory_enabled", False)),
        has_vector_search=collection.has_vector_search,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
    )


async def _resolve_collection_permissions(
    *,
    resolver: RuntimeRbacResolver,
    user: UserCtx,
    tenant_id: uuid.UUID,
):
    try:
        user_uuid = uuid.UUID(str(user.id))
    except (TypeError, ValueError):
        user_uuid = None
    return await resolver.resolve_effective_permissions(
        user_id=user_uuid,
        tenant_id=tenant_id,
        default_collection_allow=True,
    )


async def _resolve_user_tenants(
    session: AsyncSession,
    user: UserCtx,
) -> list[uuid.UUID]:
    return await resolve_active_user_tenant_ids(session, user)


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
    fields: List[dict]
    status: str
    status_details: Optional[dict] = None
    total_rows: int
    is_active: bool
    memory_enabled: bool = False
    has_vector_search: bool = False
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


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
    resolver = RuntimeRbacResolver(PermissionService(session))
    effective_permissions = await _resolve_collection_permissions(
        resolver=resolver,
        user=user,
        tenant_id=resolved_tenant_id,
    )
    collections = await service.list_collections(resolved_tenant_id, active_only=active_only)
    collections = [
        collection
        for collection in collections
        if resolver.is_collection_allowed(
            effective_permissions=effective_permissions,
            collection_slug=str(getattr(collection, "slug", "") or ""),
        )
    ]

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
    resolver = RuntimeRbacResolver(PermissionService(session))
    effective_permissions = await _resolve_collection_permissions(
        resolver=resolver,
        user=user,
        tenant_id=resolved_tenant_id,
    )
    collection = await service.get_by_slug(slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    if getattr(collection, "tenant_id", None) != resolved_tenant_id:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    if not resolver.is_collection_allowed(
        effective_permissions=effective_permissions,
        collection_slug=str(getattr(collection, "slug", "") or ""),
    ):
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    return await _build_collection_response(service, collection)
