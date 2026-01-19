"""
Collections CRUD endpoints.
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.collection_service import (
    CollectionService,
    CollectionExistsError,
    CollectionNotFoundError,
    InvalidSchemaError,
)
from app.models.collection import CollectionType

logger = get_logger(__name__)

router = APIRouter()


class FieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(..., pattern="^(text|integer|float|boolean|datetime|date)$")
    required: bool = False
    searchable: bool = False
    search_mode: Optional[str] = Field(None, pattern="^(exact|like|range)$")
    description: Optional[str] = None


class CreateCollectionRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str = Field(default="sql", pattern="^(sql|vector|hybrid)$")
    fields: List[FieldSchema] = Field(..., min_length=1)


class CollectionResponse(BaseModel):
    id: uuid.UUID
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


@router.post("", response_model=CollectionResponse)
async def create_collection(
    body: CreateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Create a new collection with its dynamic table"""
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)

    try:
        collection = await service.create_collection(
            tenant_id=tenant_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            collection_type=CollectionType(body.type),
            fields=[f.model_dump() for f in body.fields],
        )

        await session.commit()

        return CollectionResponse(
            id=collection.id,
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


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    active_only: bool = True,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """List all collections for the current tenant"""
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collections = await service.list_collections(tenant_id, active_only=active_only)

    items = [
        CollectionResponse(
            id=c.id,
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
        for c in collections
    ]

    return CollectionListResponse(items=items, total=len(items))


@router.get("/{slug}", response_model=CollectionResponse)
async def get_collection(
    slug: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Get a collection by slug"""
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collection = await service.get_by_slug(tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    return CollectionResponse(
        id=collection.id,
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


@router.delete("/{slug}")
async def delete_collection(
    slug: str,
    drop_table: bool = True,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Delete a collection and optionally its data table"""
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    deleted = await service.delete_collection(tenant_id, slug, drop_table=drop_table)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    await session.commit()

    return {"status": "deleted", "slug": slug, "table_dropped": drop_table}


@router.get("/{slug}/schema")
async def get_collection_schema(
    slug: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Get collection schema for tool generation"""
    from app.agents.builtins.collection_search import create_collection_tool

    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collection = await service.get_by_slug(tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    return create_collection_tool(collection)
