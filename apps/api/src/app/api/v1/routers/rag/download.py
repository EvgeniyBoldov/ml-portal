"""
RAG Download endpoints.
"""
from __future__ import annotations
import uuid

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager, PresignOptions
from app.models.rag_ingest import Source
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.document_artifacts import get_document_artifact_key
from app.services.file_delivery_service import FileDeliveryService

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{doc_id}/download")
async def download_rag_file(
    doc_id: str,
    kind: str = Query("original", regex="^(original|canonical)$"),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Download RAG file"""
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        settings = get_settings()
        
        if kind == "original":
            s3_key = document.s3_key_raw
        else:
            s3_key = document.s3_key_processed
            if not s3_key:
                source_meta_result = await session.execute(
                    select(Source.meta).where(
                        Source.source_id == uuid.UUID(doc_id),
                        Source.tenant_id == document.tenant_id,
                    )
                )
                source_meta = source_meta_result.scalar_one_or_none()
                s3_key = get_document_artifact_key(source_meta, "canonical")
            
            if not s3_key:
                prefix = f"{document.tenant_id}/{doc_id}/canonical/"
                try:
                    objects = await s3_manager.list_objects(
                        bucket=settings.S3_BUCKET_RAG,
                        prefix=prefix,
                        max_keys=1
                    )
                    if objects:
                        s3_key = objects[0].get('Key')
                        document.s3_key_processed = s3_key
                        session.add(document)
                        await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to search for canonical file: {e}")
        
        if not s3_key:
            raise HTTPException(status_code=404, detail="File not found")
        
        url = await s3_manager.generate_presigned_url(
            bucket=settings.S3_BUCKET_RAG,
            key=s3_key,
            options=PresignOptions(method="GET", expires_in=3600)
        )
        
        file_id = FileDeliveryService.make_rag_document_file_id(doc_id, kind)
        return {
            "url": url,
            "file_id": file_id,
            "download_url": f"/api/v1/files/{file_id}/download",
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {str(e)}")
