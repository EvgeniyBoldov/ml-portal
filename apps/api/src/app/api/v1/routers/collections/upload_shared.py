"""
Shared helpers for collection upload/data routers.
"""
from __future__ import annotations

from typing import Optional
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import resolve_active_user_tenant_ids
from app.core.security import UserCtx
from app.models.collection import Collection, CollectionType
from app.services.collection_service import CollectionService
from app.services.collection_content_access_service import CollectionContentAccessService
from .crud import require_collection_permission


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
    user_tenant_ids = await _resolve_user_tenants(session, user)

    if tenant_id:
        if user.role != "admin" and tenant_id not in user_tenant_ids:
            raise HTTPException(status_code=403, detail="Access denied")
        return tenant_id

    if user_tenant_ids:
        return user_tenant_ids[0]

    raise HTTPException(status_code=400, detail="User has no tenant assigned")


async def _resolve_table_collection_by_slug(
    slug: str,
    session: AsyncSession,
    user: UserCtx,
    tenant_id: Optional[uuid.UUID],
    *,
    for_write: bool = False,
):
    resolved_tenant_id = await _resolve_requested_tenant_id(session, user, tenant_id)
    service = CollectionService(session)
    collection = await service.get_by_slug(slug, include_inactive=True)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    if getattr(collection, "tenant_id", None) != resolved_tenant_id:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    await require_collection_permission(session, user, collection)
    if collection.collection_type not in {
        CollectionType.TABLE.value,
        CollectionType.SQL.value,
        CollectionType.API.value,
    }:
        raise HTTPException(status_code=400, detail="Operation is only available for table/sql/api collections")
    if for_write:
        await _require_collection_editor(session, user, collection)
        if collection.collection_type != CollectionType.TABLE.value:
            raise HTTPException(status_code=400, detail="Content editing is only available for table collections")
    if collection.collection_type in {CollectionType.SQL.value, CollectionType.API.value}:
        await service.ensure_sql_storage_table(collection)

    return collection, service, resolved_tenant_id


async def _resolve_collection(
    collection_id: uuid.UUID,
    session: AsyncSession,
    user: UserCtx,
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if user.role != "admin":
        tenant_ids = await _resolve_user_tenants(session, user)
        if collection.tenant_id not in tenant_ids:
            raise HTTPException(status_code=404, detail="Collection not found")

    await require_collection_permission(session, user, collection)

    return collection


async def _require_collection_editor(
    session: AsyncSession,
    user: UserCtx,
    collection: Collection,
) -> None:
    """Collection content writes require an editor role in that collection's tenant."""
    if not collection.is_active or getattr(collection, "lifecycle_status", "active") == "deprecated":
        raise HTTPException(status_code=409, detail="Collection is inactive")
    if await CollectionContentAccessService(session).can_edit_tenant(user.id, collection.tenant_id):
        return
    raise HTTPException(status_code=403, detail="Tenant collection editor permission required")
