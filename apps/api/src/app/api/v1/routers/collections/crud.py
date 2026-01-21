"""
Collections tenant-level endpoints.
List and get collections for the current tenant (read-only).
CRUD operations are in admin router.
"""
from __future__ import annotations
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.collection_service import CollectionService

logger = get_logger(__name__)

router = APIRouter()


class CollectionResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: Optional[str]
    type: str
    fields: List[dict]
    row_count: int
    is_active: bool
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
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """List all collections for the current tenant (or all if admin)"""
    service = CollectionService(session)
    
    # Admin sees all collections, regular users see only their tenant's collections
    if user.role == "admin":
        from sqlalchemy.future import select
        from app.models.collection import Collection
        
        query = select(Collection)
        if active_only:
            query = query.where(Collection.is_active == True)
        query = query.order_by(Collection.created_at.desc())
        
        result = await session.execute(query)
        collections = list(result.scalars().all())
    else:
        tenant_id = repo_factory.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="User has no tenant assigned")
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
    """Get a collection by slug (admin sees all, users see only their tenant's)"""
    service = CollectionService(session)
    
    # Admin can access any collection by slug, regular users only their tenant's
    if user.role == "admin":
        from sqlalchemy.future import select
        from app.models.collection import Collection
        
        query = select(Collection).where(Collection.slug == slug)
        result = await session.execute(query)
        collection = result.scalar_one_or_none()
    else:
        tenant_id = repo_factory.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="User has no tenant assigned")
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
        is_active=collection.is_active,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
    )
