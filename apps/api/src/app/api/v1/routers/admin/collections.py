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
from app.models.collection import SearchMode

logger = get_logger(__name__)

router = APIRouter(tags=["collections"])


class FieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(..., pattern="^(text|integer|float|boolean|datetime|date)$")
    required: bool = False
    search_modes: List[str] = Field(default_factory=lambda: ["exact"])
    description: Optional[str] = None
    
    def validate_search_modes(self):
        """Validate search_modes based on field type and dependencies"""
        valid_modes = {"exact", "like", "range", "vector"}
        for mode in self.search_modes:
            if mode not in valid_modes:
                raise ValueError(f"Invalid search mode: {mode}")
        
        # Vector only for text fields
        if "vector" in self.search_modes and self.type != "text":
            raise ValueError("Vector search is only available for text fields")
        
        # Vector requires like
        if "vector" in self.search_modes and "like" not in self.search_modes:
            raise ValueError("Vector search requires 'like' in search_modes")
        
        # Like only for text fields
        if "like" in self.search_modes and self.type != "text":
            raise ValueError("LIKE search is only available for text fields")


class VectorConfigSchema(BaseModel):
    """Configuration for vector search"""
    chunk_strategy: str = Field(default="by_paragraphs", pattern="^(by_tokens|by_paragraphs|by_sentences|by_markdown)$")
    chunk_size: int = Field(default=512, ge=128, le=2048)
    overlap: int = Field(default=50, ge=0, le=512)
    

class CreateCollectionRequest(BaseModel):
    tenant_id: uuid.UUID
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fields: List[FieldSchema] = Field(..., min_length=1)
    vector_config: Optional[VectorConfigSchema] = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    description: Optional[str]
    fields: List[dict]
    row_count: int
    table_name: str
    
    # Vector search fields
    has_vector_search: bool
    vector_config: Optional[dict]
    qdrant_collection_name: Optional[str]
    
    # Vectorization statistics
    total_rows: int
    vectorized_rows: int
    total_chunks: int
    failed_rows: int
    vectorization_progress: float
    is_fully_vectorized: bool
    
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
                    fields=c.fields,
                    row_count=c.row_count,
                    table_name=c.table_name,
                    has_vector_search=c.has_vector_search,
                    vector_config=c.vector_config,
                    qdrant_collection_name=c.qdrant_collection_name,
                    total_rows=c.total_rows,
                    vectorized_rows=c.vectorized_rows,
                    total_chunks=c.total_chunks,
                    failed_rows=c.failed_rows,
                    vectorization_progress=c.vectorization_progress,
                    is_fully_vectorized=c.is_fully_vectorized,
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
        # Validate fields
        for field in body.fields:
            field.validate_search_modes()
        
        collection = await service.create_collection(
            tenant_id=body.tenant_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            fields=[f.model_dump() for f in body.fields],
            vector_config=body.vector_config.model_dump() if body.vector_config else None,
        )

        await session.commit()

        return CollectionResponse(
            id=collection.id,
            tenant_id=collection.tenant_id,
            slug=collection.slug,
            name=collection.name,
            description=collection.description,
            fields=collection.fields,
            row_count=collection.row_count,
            table_name=collection.table_name,
            has_vector_search=collection.has_vector_search,
            vector_config=collection.vector_config,
            qdrant_collection_name=collection.qdrant_collection_name,
            total_rows=collection.total_rows,
            vectorized_rows=collection.vectorized_rows,
            total_chunks=collection.total_chunks,
            failed_rows=collection.failed_rows,
            vectorization_progress=collection.vectorization_progress,
            is_fully_vectorized=collection.is_fully_vectorized,
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
        fields=collection.fields,
        row_count=collection.row_count,
        table_name=collection.table_name,
        has_vector_search=collection.has_vector_search,
        vector_config=collection.vector_config,
        qdrant_collection_name=collection.qdrant_collection_name,
        total_rows=collection.total_rows,
        vectorized_rows=collection.vectorized_rows,
        total_chunks=collection.total_chunks,
        failed_rows=collection.failed_rows,
        vectorization_progress=collection.vectorization_progress,
        is_fully_vectorized=collection.is_fully_vectorized,
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
