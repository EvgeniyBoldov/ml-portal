"""
Admin Collections CRUD endpoints.
Only admins can create/delete collections (schema management).
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.core.logging import get_logger
from app.services.collection_service import (
    CollectionService,
    CollectionExistsError,
    CollectionNotFoundError,
    InvalidSchemaError,
)
from app.models.collection import CollectionType

logger = get_logger(__name__)

router = APIRouter(tags=["collections"])


class FieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(..., pattern="^(text|integer|float|boolean|datetime|date)$")
    required: bool = False
    searchable: bool = False
    search_mode: Optional[str] = Field(None, pattern="^(exact|like|range)$")
    description: Optional[str] = None


class CreateCollectionRequest(BaseModel):
    tenant_id: uuid.UUID
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str = Field(default="sql", pattern="^(sql|vector|hybrid)$")
    fields: List[FieldSchema] = Field(..., min_length=1)


class CollectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    description: Optional[str]
    type: str
    fields: List[dict]
    row_count: int
    table_name: str
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CollectionListResponse(BaseModel):
    items: List[CollectionResponse]
    total: int
    page: int
    size: int
    has_more: bool


@router.get("", response_model=CollectionListResponse)
async def list_all_collections(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    """List all collections across tenants (admin only)"""
    from sqlalchemy.future import select
    from app.models.collection import Collection

    try:
        query = select(Collection)

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

        return CollectionListResponse(
            items=[
                CollectionResponse(
                    id=c.id,
                    tenant_id=c.tenant_id,
                    slug=c.slug,
                    name=c.name,
                    description=c.description,
                    type=c.type,
                    fields=c.fields,
                    row_count=c.row_count,
                    table_name=c.table_name,
                    is_active=c.is_active,
                    created_at=c.created_at.isoformat(),
                    updated_at=c.updated_at.isoformat(),
                )
                for c in items
            ],
            total=total,
            page=page,
            size=size,
            has_more=end_idx < total,
        )

    except Exception as e:
        logger.error(f"Failed to list collections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@router.post("", response_model=CollectionResponse)
async def create_collection(
    body: CreateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    """Create a new collection with its dynamic table (admin only)"""
    service = CollectionService(session)

    try:
        collection = await service.create_collection(
            tenant_id=body.tenant_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            collection_type=CollectionType(body.type),
            fields=[f.model_dump() for f in body.fields],
        )

        await session.commit()

        return CollectionResponse(
            id=collection.id,
            tenant_id=collection.tenant_id,
            slug=collection.slug,
            name=collection.name,
            description=collection.description,
            type=collection.type,
            fields=collection.fields,
            row_count=collection.row_count,
            table_name=collection.table_name,
            is_active=collection.is_active,
            created_at=collection.created_at.isoformat(),
            updated_at=collection.updated_at.isoformat(),
        )

    except CollectionExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidSchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create collection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    """Get a collection by ID (admin only)"""
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    return CollectionResponse(
        id=collection.id,
        tenant_id=collection.tenant_id,
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        type=collection.type,
        fields=collection.fields,
        row_count=collection.row_count,
        table_name=collection.table_name,
        is_active=collection.is_active,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
    )


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    drop_table: bool = Query(True),
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    """Delete a collection and optionally its data table (admin only)"""
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    deleted = await service.delete_collection(
        collection.tenant_id, collection.slug, drop_table=drop_table
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Collection not found")

    await session.commit()

    return {"status": "deleted", "id": str(collection_id), "table_dropped": drop_table}


@router.get("/{collection_id}/schema")
async def get_collection_schema(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    """Get collection schema for tool generation (admin only)"""
    from app.agents.builtins.collection_search import create_collection_tool

    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    return create_collection_tool(collection)
