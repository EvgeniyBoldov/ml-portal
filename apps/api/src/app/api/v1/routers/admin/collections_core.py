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
from app.models.collection import Collection, CollectionType
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
from app.services.collection_service import CollectionService, _UNSET

from .collections_shared import build_collection_response

router = APIRouter()


def _extract_remote_sql_tables(table_schema: dict | None, source_contract: dict | None) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _push(schema_name: str | None, table_name: str | None, columns=None) -> None:
        table = str(table_name or "").strip()
        if not table:
            return
        schema = str(schema_name or "").strip() or "public"
        key = (schema, table)
        if key in seen:
            return
        seen.add(key)
        result.append(
            {
                "schema_name": schema,
                "table_name": table,
                "object_type": "BASE TABLE",
                "table_schema": {"columns": columns} if isinstance(columns, list) else {},
            }
        )

    for source in (table_schema, source_contract):
        if not isinstance(source, dict):
            continue

        tables = source.get("tables")
        if isinstance(tables, list):
            for item in tables:
                if isinstance(item, str):
                    _push(None, item)
                elif isinstance(item, dict):
                    _push(item.get("schema"), item.get("name") or item.get("table"), item.get("columns"))

        schemas = source.get("schemas")
        if isinstance(schemas, list):
            for schema_obj in schemas:
                if not isinstance(schema_obj, dict):
                    continue
                schema_name = schema_obj.get("schema") or schema_obj.get("name")
                schema_tables = schema_obj.get("tables")
                if isinstance(schema_tables, list):
                    for item in schema_tables:
                        if isinstance(item, str):
                            _push(schema_name, item)
                        elif isinstance(item, dict):
                            _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))
        elif isinstance(schemas, dict):
            for schema_name, schema_tables in schemas.items():
                if isinstance(schema_tables, list):
                    for item in schema_tables:
                        if isinstance(item, str):
                            _push(schema_name, item)
                        elif isinstance(item, dict):
                            _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))

    result.sort(key=lambda item: (item["schema_name"], item["table_name"]))
    return result


def _extract_api_entities(table_schema: dict | None, source_contract: dict | None) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()

    def _norm_list(value) -> list[str]:
        if isinstance(value, list):
            values = value
        elif isinstance(value, str):
            values = [value]
        else:
            values = []
        normalized: list[str] = []
        for item in values:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _push(entity_type: str | None, aliases=None, examples=None) -> None:
        entity = str(entity_type or "").strip()
        if not entity:
            return
        key = entity.lower()
        if key in seen:
            return
        seen.add(key)
        result.append(
            {
                "entity_type": entity,
                "aliases": _norm_list(aliases),
                "examples": _norm_list(examples),
            }
        )

    for source in (table_schema, source_contract):
        if not isinstance(source, dict):
            continue

        entities = source.get("entities")
        if isinstance(entities, list):
            for item in entities:
                if isinstance(item, str):
                    _push(item)
                elif isinstance(item, dict):
                    _push(
                        item.get("entity_type") or item.get("name") or item.get("resource"),
                        item.get("aliases"),
                        item.get("examples"),
                    )

        entity_types = source.get("entity_types")
        if isinstance(entity_types, list):
            for item in entity_types:
                if isinstance(item, str):
                    _push(item)

        resources = source.get("resources")
        if isinstance(resources, list):
            for item in resources:
                if isinstance(item, dict):
                    _push(
                        item.get("entity_type") or item.get("name") or item.get("resource"),
                        item.get("aliases"),
                        item.get("examples"),
                    )

    result.sort(key=lambda item: item["entity_type"].lower())
    return result


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
        selectinload(Collection.data_instance),
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
            selectinload(Collection.data_instance),
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
    if str(collection.collection_type or "").strip().lower() != CollectionType.SQL.value:
        raise HTTPException(status_code=400, detail="Table discovery is available only for sql collections")

    try:
        discovered = _extract_remote_sql_tables(
            collection.table_schema if isinstance(collection.table_schema, dict) else {},
            collection.source_contract if isinstance(collection.source_contract, dict) else {},
        )
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredSqlTable(**item) for item in discovered]
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
    if str(collection.collection_type or "").strip().lower() != CollectionType.API.value:
        raise HTTPException(status_code=400, detail="Entity discovery is available only for api collections")

    try:
        discovered = _extract_api_entities(
            collection.table_schema if isinstance(collection.table_schema, dict) else {},
            collection.source_contract if isinstance(collection.source_contract, dict) else {},
        )
        if not discovered and collection.entity_type:
            discovered = [
                {
                    "entity_type": collection.entity_type,
                    "aliases": [],
                    "examples": [],
                }
            ]
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredApiEntity(**item) for item in discovered]
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
