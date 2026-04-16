"""
Admin Collections router facade.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.schemas.collections import CollectionListResponse, CollectionResponse, CreateCollectionRequest

from .collections_audit import router as audit_router
from .collections_core import router as core_router
from .collections_core import create_collection as create_collection_core
from .collections_core import list_all_collections as list_all_collections_core
from .collections_versions import router as versions_router

router = APIRouter(tags=["collections"])
router.include_router(audit_router)
router.include_router(core_router)
router.include_router(versions_router)


@router.get("", response_model=CollectionListResponse)
async def list_all_collections_no_slash(
    page: int = 1,
    size: int = 20,
    tenant_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    return await list_all_collections_core(
        page=page,
        size=size,
        tenant_id=tenant_id,
        is_active=is_active,
        session=session,
        admin_user=admin_user,
    )


@router.post("", response_model=CollectionResponse)
async def create_collection_no_slash(
    body: CreateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    return await create_collection_core(
        body=body,
        session=session,
        admin_user=admin_user,
    )

__all__ = ["router"]
