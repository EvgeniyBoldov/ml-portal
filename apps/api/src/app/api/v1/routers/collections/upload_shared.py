"""
Shared helpers for collection upload/data routers.
"""
from __future__ import annotations

from typing import Optional
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import is_local
from app.core.security import UserCtx
from app.models.collection import CollectionType
from app.models.tenant import Tenants, UserTenants
from app.services.collection_service import CollectionService


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
    user_tenant_ids = await _resolve_user_tenants(session, user)

    if tenant_id:
        if user.role != "admin" and user_tenant_ids and tenant_id not in user_tenant_ids:
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
):
    service = CollectionService(session)
    resolved_tenant_id = await _resolve_requested_tenant_id(session, user, tenant_id)
    collection = await service.get_by_slug(resolved_tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    if collection.collection_type not in {
        CollectionType.TABLE.value,
        CollectionType.SQL.value,
        CollectionType.API.value,
    }:
        raise HTTPException(status_code=400, detail="Operation is only available for table/sql/api collections")
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
        user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
        if not user_tenant_id or str(collection.tenant_id) != user_tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return collection
