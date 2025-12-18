"""
RAG Upload endpoints.
"""
from __future__ import annotations
from typing import Any, Optional
import uuid
import json

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.deps import db_uow, get_current_user, get_redis_client
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.core.config import get_settings
from app.core.s3_links import S3ContentType
from app.adapters.s3_client import s3_manager, PresignOptions
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory

logger = get_logger(__name__)

router = APIRouter()


@router.post("/upload")
async def upload_rag_file(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Upload a RAG file"""
    from app.services.rag_upload_service import RAGUploadService
    from app.services.rag_event_publisher import RAGEventPublisher
    
    logger.info(f"Upload request received: file={file.filename if file else None}, name={name}, tags={tags}")
    
    if not file:
        logger.error("No file provided in upload request")
        raise HTTPException(status_code=400, detail="No file provided")
    
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    
    from app.models.tenant import Tenants
    from sqlalchemy import select
    tenant_check = await session.execute(select(Tenants.id).where(Tenants.id == tenant_id))
    if not tenant_check.scalar_one_or_none():
        logger.error(f"Tenant {tenant_id} not found in database for user {user.id}")
        raise HTTPException(
            status_code=400, 
            detail="Your tenant configuration is invalid. Please contact administrator."
        )
    
    try:
        doc_tags = []
        if tags:
            try:
                doc_tags = json.loads(tags)
            except json.JSONDecodeError:
                doc_tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        file_content = await file.read()
        
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis) if redis else None
        
        upload_service = RAGUploadService(
            session=session,
            repo_factory=repo_factory,
            event_publisher=event_publisher
        )
        
        result = await upload_service.upload_document(
            file_content=file_content,
            filename=file.filename or f"upload_{uuid.uuid4()}",
            content_type=file.content_type,
            name=name,
            tags=doc_tags,
            user_id=user.id
        )
        
        return result
        
    except IntegrityError as e:
        logger.error(f"Database integrity error during upload: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Database error: tenant or user configuration is invalid"
        )
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/upload/presign")
def presign_rag_upload(body: dict[str, Any]) -> dict:
    """Generate presigned URL for upload"""
    doc_id = body.get("document_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    content_type = body.get("content_type", S3ContentType.OCTET)
    key = f"docs/{doc_id}"
    s = get_settings()
    url = s3_manager.generate_presigned_url(
        bucket=s.S3_BUCKET_RAG,
        key=key,
        options=PresignOptions(operation="put", expiry_seconds=3600, content_type=content_type),
    )
    return {"presigned_url": url, "bucket": s.S3_BUCKET_RAG, "key": key, "content_type": content_type, "expires_in": 3600}
