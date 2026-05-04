"""
Collection document download endpoint.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.config import get_settings
from app.core.security import UserCtx
from app.adapters.s3_client import s3_manager, PresignOptions
from app.services.document_artifacts import get_document_artifact_key
from app.services.file_delivery_service import FileDeliveryService

from .stream_shared import _resolve_collection_and_doc_with_membership

router = APIRouter()


@router.get("/{collection_id}/docs/{doc_id}/download")
async def download_collection_doc(
    collection_id: uuid.UUID,
    doc_id: str,
    kind: str = Query("original", pattern="^(original|canonical)$"),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, document, doc_uuid, repo_factory, membership = await _resolve_collection_and_doc_with_membership(
        collection_id, doc_id, session, user
    )

    settings = get_settings()
    if kind == "original":
        s3_key = document.s3_key_raw
    else:
        s3_key = document.s3_key_processed
        if not s3_key:
            source_meta = (membership.source.meta if membership.source else None)
            s3_key = get_document_artifact_key(source_meta, "canonical")
        if not s3_key:
            prefix = f"{document.tenant_id}/{doc_id}/canonical/"
            try:
                objects = await s3_manager.list_objects(
                    bucket=settings.S3_BUCKET_RAG,
                    prefix=prefix,
                    max_keys=1,
                )
                if objects:
                    s3_key = objects[0].get("Key")
                    document.s3_key_processed = s3_key
                    session.add(document)
                    await session.commit()
            except Exception:
                pass

    if not s3_key:
        raise HTTPException(status_code=404, detail="File not found")

    url = await s3_manager.generate_presigned_url(
        bucket=settings.S3_BUCKET_RAG,
        key=s3_key,
        options=PresignOptions(method="GET", expires_in=3600),
    )

    file_id = FileDeliveryService.make_rag_document_file_id(doc_id, kind)
    return {"url": url, "file_id": file_id, "download_url": f"/api/v1/files/{file_id}/download"}
