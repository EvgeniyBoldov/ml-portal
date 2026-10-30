"""
Collections tenant-level endpoints.
List and get collections for the current tenant (read-only).
CRUD operations are in admin router.
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, resolve_active_user_tenant_ids
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.models.collection import Collection
from app.schemas.collections_public import (
    CollectionCapabilities,
    PublicCollectionCount,
    PublicCollectionSource,
    CollectionWorkspacesResponse,
    PublishedCollectionVersion,
)
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.services.collection_public_service import (
    CollectionPublicService,
    build_collection_display_metadata,
)
from app.services.collection_service import CollectionService
from app.services.permission_service import PermissionService

logger = get_logger(__name__)

router = APIRouter()


async def _build_collection_response(
    service: CollectionService,
    collection,
    *,
    user: UserCtx | None = None,
) -> CollectionResponse:
    raw_collection_type = getattr(collection, "collection_type", "")
    collection_type = str(getattr(raw_collection_type, "value", raw_collection_type) or "")
    is_external = collection_type in {"api", "sql"}
    if collection_type == "template":
        await service.ensure_contract_fields_present(collection, ensure_vector_infra=False)

    if is_external:
        status = "unknown"
        status_details = None
        effective_total_rows = 0  # Retained for older clients; external count is explicitly unknown below.
        count = PublicCollectionCount()
    else:
        snapshot = await service.sync_collection_status(collection, persist=False)
        status = snapshot["status"]
        status_details = snapshot["details"]
        effective_total_rows = await service.get_effective_total_rows(collection)
        count_kind, count_unit = {
            "document": ("documents", "документов"),
            "template": ("templates", "шаблонов"),
        }.get(collection_type, ("rows", "строк"))
        count = PublicCollectionCount(
            value=effective_total_rows,
            kind=count_kind,
            unit=count_unit,
        )

    display = build_collection_display_metadata(collection)
    if user is None:
        capabilities = CollectionCapabilities()
        capability_reasons = {"can_edit_content": "editing_permission_required"}
    else:
        capabilities, capability_reasons = await CollectionPublicService(session=service.session).build_capabilities(
            collection,
            user_id=str(user.id),
            collection_allowed=True,
        )

    return CollectionResponse(
        id=collection.id,
        tenant_id=collection.tenant_id,
        collection_type=collection_type,
        slug=collection.slug,
        name=collection.name,
        fields=collection.fields,
        status=status,
        status_details=status_details,
        total_rows=effective_total_rows,
        is_active=collection.is_active,
        memory_enabled=bool(getattr(collection, "memory_enabled", False)),
        has_vector_search=collection.has_vector_search,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
        source=display.source,
        description=display.description,
        purpose=display.purpose,
        version=display.version,
        count=count,
        capabilities=capabilities,
        capability_reasons=capability_reasons,
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


async def require_collection_permission(
    session: AsyncSession,
    user: UserCtx,
    collection: Collection,
) -> None:
    """Apply the same effective collection policy to metadata and data paths."""
    resolver = RuntimeRbacResolver(PermissionService(session))
    permissions = await _resolve_collection_permissions(
        resolver=resolver,
        user=user,
        tenant_id=collection.tenant_id,
    )
    if not resolver.is_collection_allowed(
        effective_permissions=permissions,
        collection_slug=collection.slug,
    ):
        raise HTTPException(status_code=404, detail="Collection not found")


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
        if user.role != "admin" and tenant_id not in user_tenant_ids:
            raise HTTPException(status_code=403, detail="Access denied")
        return tenant_id

    if user_tenant_ids:
        return user_tenant_ids[0]

    if not user_tenant_ids:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    raise HTTPException(status_code=400, detail="Unable to resolve tenant")


class CollectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
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
    source: PublicCollectionSource | None = None
    description: str | None = None
    purpose: str | None = None
    version: PublishedCollectionVersion | None = None
    count: PublicCollectionCount = Field(default_factory=PublicCollectionCount)
    capabilities: CollectionCapabilities = Field(default_factory=CollectionCapabilities)
    capability_reasons: dict[str, str] = Field(default_factory=dict)

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

    items = [await _build_collection_response(service, c, user=user) for c in collections]

    return CollectionListResponse(items=items, total=len(items))


@router.get("/workspaces", response_model=CollectionWorkspacesResponse)
async def list_collection_workspaces(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
) -> CollectionWorkspacesResponse:
    """List active tenant workspaces available to the current user."""
    workspaces = await CollectionPublicService(session).workspaces(str(user.id))
    return CollectionWorkspacesResponse(items=workspaces)


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
    collection = await service.get_by_slug(slug, include_inactive=True)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    if getattr(collection, "tenant_id", None) != resolved_tenant_id:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    await require_collection_permission(session, user, collection)

    return await _build_collection_response(service, collection, user=user)
