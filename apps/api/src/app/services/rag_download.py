"""
RAG document download service
"""
from typing import Tuple, Optional
import uuid
import logging

from app.core.config import get_settings
from app.repositories.factory import AsyncRepositoryFactory
from app.core.security import UserCtx
from app.models.rag import RAGDocument

logger = logging.getLogger(__name__)


def resolve_minio_path(
    source_id: str, 
    kind: str, 
    user: UserCtx,
    repo_factory: AsyncRepositoryFactory
) -> Tuple[str, str, str, str]:
    """
    Resolve MinIO path for RAG document download
    
    Args:
        source_id: Document ID
        kind: File kind ('original' or 'canonical')
        user: Current user context
        repo_factory: Repository factory for database access
        
    Returns:
        Tuple of (bucket, key, filename, content_type)
        
    Raises:
        ValueError: If source_id is invalid UUID
        HTTPException: If document not found or access denied
    """
    try:
        doc_uuid = uuid.UUID(source_id)
    except ValueError:
        raise ValueError(f"Invalid document ID: {source_id}")
    
    # Get document from database
    document = repo_factory.get_rag_document_by_id(doc_uuid, user.role)
    if not document:
        raise ValueError(f"Document not found: {source_id}")
    
    # Check permissions: editor can only access documents from their tenant
    if user.role == "editor" and document.tenant_id != repo_factory.tenant_id:
        raise ValueError(f"Access denied: you can only access documents from your tenant")
    
    # Determine S3 key based on kind
    if kind == "original":
        s3_key = document.s3_key_raw
        filename = document.name or f"document_{source_id}"
    elif kind == "canonical":
        s3_key = document.s3_key_processed
        filename = f"{document.name or f'document_{source_id}'}_canonical.jsonl"
    else:
        raise ValueError(f"Invalid kind: {kind}. Must be 'original' or 'canonical'")
    
    if not s3_key:
        raise ValueError(f"File not found for kind '{kind}'")
    
    # Get bucket from settings
    settings = get_settings()
    bucket = settings.S3_BUCKET_RAG
    
    # Determine content type
    if kind == "canonical":
        content_type = "application/json"
    else:
        # Try to determine from filename extension
        if filename.lower().endswith('.pdf'):
            content_type = "application/pdf"
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            content_type = "image/jpeg"
        elif filename.lower().endswith('.txt'):
            content_type = "text/plain"
        elif filename.lower().endswith('.docx'):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content_type = "application/octet-stream"
    
    logger.info(
        f"Resolved MinIO path for document {source_id}",
        extra={
            "user_id": user.id,
            "source_id": source_id,
            "kind": kind,
            "bucket": bucket,
            "key": s3_key,
            "file_name": filename,
            "content_type": content_type
        }
    )
    
    return bucket, s3_key, filename, content_type


async def resolve_minio_path_async(
    source_id: str, 
    kind: str, 
    user: UserCtx,
    repo_factory: AsyncRepositoryFactory
) -> Tuple[str, str, str, str]:
    """
    Async version of resolve_minio_path
    
    Args:
        source_id: Document ID
        kind: File kind ('original' or 'canonical')
        user: Current user context
        repo_factory: Repository factory for database access
        
    Returns:
        Tuple of (bucket, key, filename, content_type)
        
    Raises:
        ValueError: If source_id is invalid UUID
        HTTPException: If document not found or access denied
    """
    try:
        doc_uuid = uuid.UUID(source_id)
    except ValueError:
        raise ValueError(f"Invalid document ID: {source_id}")
    
    # Get document from database
    document = await repo_factory.get_rag_document_by_id(doc_uuid, user.role)
    if not document:
        raise ValueError(f"Document not found: {source_id}")
    
    # Check permissions: editor can only access documents from their tenant
    if user.role == "editor" and document.tenant_id != repo_factory.tenant_id:
        raise ValueError(f"Access denied: you can only access documents from your tenant")
    
    # Determine S3 key based on kind
    if kind == "original":
        s3_key = document.s3_key_raw
        filename = document.name or f"document_{source_id}"
    elif kind == "canonical":
        s3_key = document.s3_key_processed
        filename = f"{document.name or f'document_{source_id}'}_canonical.jsonl"
    else:
        raise ValueError(f"Invalid kind: {kind}. Must be 'original' or 'canonical'")
    
    if not s3_key:
        raise ValueError(f"File not found for kind '{kind}'")
    
    # Get bucket from settings
    settings = get_settings()
    bucket = settings.S3_BUCKET_RAG
    
    # Determine content type
    if kind == "canonical":
        content_type = "application/json"
    else:
        # Try to determine from filename extension
        if filename.lower().endswith('.pdf'):
            content_type = "application/pdf"
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            content_type = "image/jpeg"
        elif filename.lower().endswith('.txt'):
            content_type = "text/plain"
        elif filename.lower().endswith('.docx'):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content_type = "application/octet-stream"
    
    logger.info(
        f"Resolved MinIO path for document {source_id}",
        extra={
            "user_id": user.id,
            "source_id": source_id,
            "kind": kind,
            "bucket": bucket,
            "key": s3_key,
            "file_name": filename,
            "content_type": content_type
        }
    )
    
    return bucket, s3_key, filename, content_type

