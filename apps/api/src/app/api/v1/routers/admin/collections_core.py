"""
Admin collection core CRUD endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_uow, require_admin
from app.core.exceptions import InvalidSchemaError
from app.models.collection import Collection
from app.schemas.collections import (
    DiscoverApiEntitiesResponse,
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    DiscoveredApiEntity,
    DiscoverSqlTablesResponse,
    DiscoveredSqlTable,
    UpdateCollectionRequest,
)
from app.services.collection.type_profiles import (
    ApiCollectionTypeProfile,
    SqlCollectionTypeProfile,
    get_collection_type_profile,
)
from app.services.collection_service import CollectionService, _UNSET

from .collections_shared import build_collection_response

router = APIRouter()


@router.get("/", response_model=CollectionListResponse)
async def list_all_collections(
    page: int = 1,
    size: int = 20,
    tenant_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    query = select(Collection).options(
        selectinload(Collection.schema),
        selectinload(Collection.current_version),
    )
    if tenant_id:
        query = query.where(Collection.tenant_id == tenant_id)
    if is_active is not None:
        query = query.where(Collection.is_active == is_active)
    query = query.order_by(Collection.created_at.desc())

    result = await session.execute(query)
    all_collections = list(result.scalars().all())

    total = len(all_collections)
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    items = all_collections[start_idx:end_idx]

    response_items = []
    service = CollectionService(session)
    for c in items:
        response_items.append(await build_collection_response(service, c))

    return CollectionListResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        has_more=end_idx < total,
    )


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    body: CreateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    from sqlalchemy.future import select as sa_select

    resolved_tenant_id = body.tenant_id
    if resolved_tenant_id is None:
        for raw_tenant_id in (admin_user.tenant_ids or []):
            try:
                resolved_tenant_id = uuid.UUID(str(raw_tenant_id))
                break
            except (TypeError, ValueError):
                continue
    if resolved_tenant_id is None:
        raise HTTPException(status_code=400, detail="tenant_id is required when user has no tenant context")

    service = CollectionService(session)
    collection = await service.create_collection(
        tenant_id=resolved_tenant_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
        source_contract=body.source_contract,
        vector_config=body.vector_config.model_dump() if body.vector_config else None,
        collection_type=body.collection_type,
        data_instance_id=body.data_instance_id,
        table_schema=body.table_schema,
    )
    await session.commit()

    stmt = (
        sa_select(Collection)
        .options(
            selectinload(Collection.schema),
            selectinload(Collection.current_version),
        )
        .where(Collection.id == collection.id)
    )
    result = await session.execute(stmt)
    collection = result.scalar_one()
    return await build_collection_response(service, collection)


@router.post("/{collection_id}/discover-tables", response_model=DiscoverSqlTablesResponse)
async def discover_sql_tables(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    profile = get_collection_type_profile(collection.collection_type)
    if not isinstance(profile, SqlCollectionTypeProfile):
        raise HTTPException(status_code=400, detail="Table discovery is available only for sql collections")

    try:
        discovered = await profile.discover(collection=collection, session=session, admin_user=admin_user)
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredSqlTable(**item) for item in discovered.items]
    return DiscoverSqlTablesResponse(items=items, total=len(items))


@router.post("/{collection_id}/discover-entities", response_model=DiscoverApiEntitiesResponse)
async def discover_api_entities(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    profile = get_collection_type_profile(collection.collection_type)
    if not isinstance(profile, ApiCollectionTypeProfile):
        raise HTTPException(status_code=400, detail="Entity discovery is available only for api collections")

    try:
        discovered = await profile.discover(collection=collection, session=session, admin_user=admin_user)
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredApiEntity(**item) for item in discovered.items]
    return DiscoverApiEntitiesResponse(items=items, total=len(items))


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await build_collection_response(service, collection)


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: UpdateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.update_collection(
        collection_id=collection_id,
        name=body.name if "name" in body.model_fields_set else _UNSET,
        description=body.description if "description" in body.model_fields_set else _UNSET,
        is_active=body.is_active if "is_active" in body.model_fields_set else _UNSET,
        data_instance_id=body.data_instance_id if "data_instance_id" in body.model_fields_set else _UNSET,
        table_name=body.table_name if "table_name" in body.model_fields_set else _UNSET,
        table_schema=body.table_schema if "table_schema" in body.model_fields_set else _UNSET,
        schema_ops=[op.model_dump() for op in body.schema_ops],
    )
    await session.commit()
    await session.refresh(collection)
    return await build_collection_response(service, collection)


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    drop_table: bool = True,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    deleted = await service.delete_collection(collection.tenant_id, collection.slug, drop_table=drop_table)
    if not deleted:
        raise HTTPException(status_code=404, detail="Collection not found")

    await session.commit()
    return {"status": "deleted", "id": str(collection_id), "table_dropped": drop_table}
