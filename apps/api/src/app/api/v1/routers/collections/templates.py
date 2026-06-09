"""
Template collection endpoints: upload, list, get, update schema.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType
from app.services.collection.template_upload_service import TemplateUploadService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService

logger = get_logger(__name__)
router = APIRouter()


class UpdateTemplateSchemaRequest(BaseModel):
    template_schema: dict


async def _resolve_template_collection(
    collection_id: uuid.UUID,
    session: AsyncSession,
    user: UserCtx,
) -> Collection:
    from app.services.collection_service import CollectionService
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if str(collection.tenant_id) not in {str(t) for t in user.tenant_ids}:
        raise HTTPException(status_code=403, detail="Access denied")
    if collection.collection_type != CollectionType.TEMPLATE.value:
        raise HTTPException(status_code=400, detail="Collection is not a template collection")
    return collection


@router.post("/{collection_id}/templates/upload")
async def upload_template(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    file_content = await file.read()

    upload_service = TemplateUploadService(session)
    result = await upload_service.upload_template(
        collection=collection,
        file_content=file_content,
        filename=file.filename or f"template_{uuid.uuid4()}",
        content_type=file.content_type,
        user_id=user.id,
    )
    await session.commit()
    return result


@router.get("/{collection_id}/templates")
async def list_templates(
    collection_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    offset = (page - 1) * size
    rows = await row_service.search(collection, limit=size, offset=offset)
    total = await row_service.count(collection)
    return {
        "items": rows,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/{collection_id}/templates/{row_id}")
async def get_template(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    row = await row_service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template row not found")
    return row


@router.patch("/{collection_id}/templates/{row_id}/schema")
async def update_template_schema(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: UpdateTemplateSchemaRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    updated = await row_service.update_row(
        collection,
        row_id,
        {"template_schema": data.template_schema},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Template row not found")
    await session.commit()
    return updated
