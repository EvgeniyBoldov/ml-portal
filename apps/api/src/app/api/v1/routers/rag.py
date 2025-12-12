from __future__ import annotations
from typing import Any, Optional, List, Dict
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends, Request
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.adapters.s3_client import s3_manager, PresignOptions
from app.core.config import get_settings
from app.core.s3_links import S3ContentType
from app.api.deps import db_uow, get_current_user, get_current_user_optional
from app.core.security import UserCtx
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.models.rag import RAGDocument, DocumentStatus, DocumentScope
import uuid
import json
from datetime import datetime, timezone
from app.services.rag_status_manager import RAGStatusManager
from app.services.status_aggregator import calculate_aggregate_status
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["rag"])


class StatusNode(BaseModel):
    """Status node in the graph"""
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str
    model_version: Optional[str] = None

class PipelineStage(BaseModel):
    """Pipeline stage status"""
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str

class EmbeddingModel(BaseModel):
    """Embedding model status"""
    model: str
    version: Optional[str] = None
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str

class StatusGraphResponse(BaseModel):
    """Response model for status graph"""
    doc_id: str
    pipeline: List[PipelineStage]
    embeddings: List[EmbeddingModel]
    index: List[EmbeddingModel]
    agg_status: str
    agg_details: Dict[str, Any]
    seq: int = 0  # Sequence number for event ordering


@router.get("/{doc_id}")
async def get_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Get single RAG document by ID"""
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Calculate aggregate status
        if document.agg_status is None:
            try:
                from app.repositories.rag_status_repo import AsyncRAGStatusRepository
                status_repo = AsyncRAGStatusRepository(session)
                
                pipeline_nodes = await status_repo.get_pipeline_nodes(document.id)
                embedding_nodes = await status_repo.get_embedding_nodes(document.id)
                
                status_manager = RAGStatusManager(session, repo_factory)
                target_models = await status_manager._get_target_models(document.id)
                
                agg_status, agg_details = calculate_aggregate_status(
                    doc_id=document.id,
                    pipeline_nodes=pipeline_nodes,
                    embedding_nodes=embedding_nodes,
                    target_models=target_models
                )
            except Exception as e:
                logger.warning(f"Failed to calculate aggregate status for {document.id}: {e}")
                agg_status = document.status
                agg_details = {}
        else:
            agg_status = document.agg_status
            agg_details = document.agg_details_json or {}
        
        # Get vectorized models list
        # If we didn't fetch nodes above, fetch them now
        if 'embedding_nodes' not in locals():
            from app.repositories.rag_status_repo import AsyncRAGStatusRepository
            status_repo = AsyncRAGStatusRepository(session)
            embedding_nodes = await status_repo.get_embedding_nodes(document.id)
            
        vectorized_models = [
            node.node_key for node in embedding_nodes 
            if node.status == 'completed'
        ]
        
        return {
            "id": str(document.id),
            "name": document.filename,
            "status": agg_status,
            "agg_status": agg_status,
            "agg_details": agg_details,
            "scope": document.scope,
            "created_at": document.created_at.isoformat() + "Z" if document.created_at else None,
            "updated_at": document.updated_at.isoformat() + "Z" if document.updated_at else None,
            "tags": document.tags or [],
            "size": document.size,
            "content_type": document.content_type,
            "vectorized_models": vectorized_models,
            "tenant_name": "Default Tenant"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")

@router.get("")
async def list_rag_documents(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """List RAG documents with pagination and search (tenant-wide, shared across all users)"""
    try:
        # Get RAG documents repository
        rag_repo = repo_factory.get_rag_documents_repository()
        
        # Get all documents for the tenant (not filtered by user_id)
        documents = await rag_repo.get_tenant_documents(
            status=status,
            search=search,
            limit=size,
            offset=(page - 1) * size
        )
        
        # Get total count for pagination
        total_count = await rag_repo.count_tenant_documents(
            status=status,
            search=search
        )
        
        # Convert to response format with aggregate status
        items = []
        for doc in documents:
            # Calculate aggregate status on the fly if not stored
            if doc.agg_status is None:
                try:
                    # Get status repository
                    from app.repositories.rag_status_repo import AsyncRAGStatusRepository
                    status_repo = AsyncRAGStatusRepository(session)
                    
                    # Get pipeline and embedding nodes
                    pipeline_nodes = await status_repo.get_pipeline_nodes(doc.id)
                    embedding_nodes = await status_repo.get_embedding_nodes(doc.id)
                    
                    # Get target models for tenant
                    status_manager = RAGStatusManager(session, repo_factory)
                    target_models = await status_manager._get_target_models(doc.id)
                    
                    # Calculate aggregate status
                    agg_status, agg_details = calculate_aggregate_status(
                        doc_id=doc.id,
                        pipeline_nodes=pipeline_nodes,
                        embedding_nodes=embedding_nodes,
                        target_models=target_models
                    )
                except Exception as e:
                    logger.warning(f"Failed to calculate aggregate status for {doc.id}: {e}")
                    agg_status = doc.status
                    agg_details = {}
            else:
                agg_status = doc.agg_status
                agg_details = doc.agg_details_json or {}
            
            # Only populate vectorized_models if we already fetched embedding_nodes
            # otherwise leave empty to avoid N+1 queries in list view
            vectorized_models = []
            if 'embedding_nodes' in locals() and embedding_nodes:
                 vectorized_models = [
                    node.node_key for node in embedding_nodes 
                    if node.status == 'completed'
                ]

            items.append({
                "id": str(doc.id),
                "name": doc.filename,
                "status": agg_status,  # Always use calculated aggregate status
                "agg_status": agg_status,
                "agg_details": agg_details,
                "scope": doc.scope,
                "created_at": doc.created_at.isoformat() + "Z" if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() + "Z" if doc.updated_at else None,
                "tags": doc.tags or [],
                "size": doc.size,
                "content_type": doc.content_type,
                "vectorized_models": vectorized_models,
                "tenant_name": "Default Tenant"
            })
        
        return {
            "items": items,
            "pagination": {
                "page": page,
                "size": size,
                "total": total_count,
                "total_pages": (total_count + size - 1) // size,
                "has_next": page * size < total_count,
                "has_prev": page > 1
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")

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
    from app.api.deps import get_redis_client
    from app.services.rag_upload_service import RAGUploadService
    from app.services.rag_event_publisher import RAGEventPublisher
    from sqlalchemy.exc import IntegrityError
    
    logger.info(f"Upload request received: file={file.filename if file else None}, name={name}, tags={tags}")
    
    if not file:
        logger.error("No file provided in upload request")
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Validate tenant exists
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    
    # Check tenant exists in DB
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
        # Parse tags from JSON string
        doc_tags = []
        if tags:
            try:
                doc_tags = json.loads(tags)
            except json.JSONDecodeError:
                # Fallback: treat as comma-separated string
                doc_tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Read file content
        file_content = await file.read()
        
        # Initialize upload service
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis) if redis else None
        
        upload_service = RAGUploadService(
            session=session,
            repo_factory=repo_factory,
            event_publisher=event_publisher
        )
        
        # Upload document
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

@router.put("/{doc_id}/tags")
async def update_rag_document_tags(
    doc_id: str,
    tags: list[str],
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Update RAG document tags"""
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Validate tags
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="Tags must be a list")
        
        # Sanitize tags
        sanitized_tags = []
        for tag in tags:
            if tag and isinstance(tag, str):
                tag = tag.strip()
                if tag and len(tag) <= 50:  # Max tag length
                    sanitized_tags.append(tag)
        
        # Update tags
        document.tags = sanitized_tags
        document.updated_at = datetime.now(timezone.utc)
        
        # Emit event for SSE
        from app.services.outbox_helper import emit_tags_updated
        await emit_tags_updated(
            session=session,
            repo_factory=repo_factory,
            document_id=doc_uuid,
            tags=sanitized_tags
        )
        
        return {"id": doc_id, "tags": sanitized_tags}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document tags: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update tags: {str(e)}")

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
        
        # Determine S3 key based on kind
        if kind == "original":
            s3_key = document.s3_key_raw
        else:
            # For canonical, try s3_key_processed first
            s3_key = document.s3_key_processed
            
            # Fallback: search for canonical file in S3 if not in DB
            if not s3_key:
                # Try to find canonical file by pattern
                prefix = f"{document.tenant_id}/{doc_id}/canonical/"
                try:
                    objects = await s3_manager.list_objects(
                        bucket=settings.S3_BUCKET_RAG,
                        prefix=prefix,
                        max_keys=1
                    )
                    if objects:
                        s3_key = objects[0].get('Key')
                        # Update document with found key for future requests
                        document.s3_key_processed = s3_key
                        session.add(document)
                        await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to search for canonical file: {e}")
        
        if not s3_key:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Generate presigned URL for download
        url = await s3_manager.generate_presigned_url(
            bucket=settings.S3_BUCKET_RAG,
            key=s3_key,
            options=PresignOptions(method="GET", expires_in=3600)
        )
        
        return {"url": url}
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {str(e)}")

@router.post("/{doc_id}/archive")
async def archive_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Archive RAG document"""
    from app.api.deps import get_redis_client
    from app.services.rag_event_publisher import RAGEventPublisher
    
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Use RAGStatusManager for archiving
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis)
        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
        
        await status_manager.archive_document(doc_uuid)
        
        # Update document status
        document.status = "archived"
        document.updated_at = datetime.now(timezone.utc)
        
        # Publish event
        await event_publisher.publish_document_archived(
            doc_id=doc_uuid,
            tenant_id=document.tenant_id,
            archived=True
        )
        
        return {"id": doc_id, "archived": True}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to archive document: {str(e)}")

@router.post("/{doc_id}/unarchive")
async def unarchive_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Unarchive RAG document"""
    from app.api.deps import get_redis_client
    from app.services.rag_event_publisher import RAGEventPublisher
    
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Use RAGStatusManager for unarchiving
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis)
        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
        
        await status_manager.unarchive_document(doc_uuid)
        
        # Recalculate aggregate status
        await status_manager._update_aggregate_status(doc_uuid)
        
        # Publish event
        await event_publisher.publish_document_archived(
            doc_id=doc_uuid,
            tenant_id=document.tenant_id,
            archived=False
        )
        
        return {"id": doc_id, "archived": False}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unarchive document: {str(e)}")

@router.delete("/{doc_id}")
async def delete_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Delete RAG document and clean up all artifacts"""
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Trigger background cleanup of S3 artifacts and Vector Store data
        from app.workers.tasks_rag_ingest import cleanup_document_artifacts
        
        # Send to cleanup queue
        cleanup_document_artifacts.delay(
            str(document.tenant_id), 
            str(document.id)
        )
        
        # Delete document from database (this will cascade delete status nodes if configured)
        # Or the repo handles it
        await repo_factory.delete_rag_document(uuid.UUID(doc_id))
        
        return {"id": doc_id, "deleted": True}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@router.put("/{doc_id}/scope")
async def update_rag_document_scope(
    doc_id: str,
    scope: str = Form(...),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Update RAG document scope (local/global) with RBAC validation"""
    if scope not in ["local", "global"]:
        raise HTTPException(status_code=400, detail="Scope must be 'local' or 'global'")
    
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # RBAC validation for global scope
        if scope == "global":
            from app.core.rbac import RBACValidator
            permission_check = RBACValidator.can_edit_global_docs(user)
            if not permission_check.allowed:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Cannot change scope to global: {permission_check.reason}"
                )
            
            # Additional check: user can only change scope of their own documents
            if document.user_id != user.id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only change scope of your own documents"
                )
        
        # Update scope
        document.scope = DocumentScope(scope)
        document.updated_at = datetime.now(timezone.utc)
        
        # If changing to global, set published fields
        if scope == "global":
            document.published_at = datetime.now(timezone.utc)
            document.published_by = user.id
            document.global_version = 1
        
        return {
            "id": doc_id, 
            "scope": scope, 
            "message": f"Document scope updated to {scope}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update scope: {str(e)}")

@router.get("/{doc_id}/status-graph")
async def get_status_graph(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Get status graph for a document from new status nodes"""
    try:
        doc_uuid = uuid.UUID(doc_id)
        
        # Get document
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get status repository
        from app.repositories.rag_status_repo import AsyncRAGStatusRepository
        status_repo = AsyncRAGStatusRepository(session)
        
        # Get pipeline, embedding and index nodes
        pipeline_nodes = await status_repo.get_pipeline_nodes(doc_uuid)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_uuid)
        index_nodes = await status_repo.get_index_nodes(doc_uuid)
        
        # Get target models for tenant
        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_uuid)
        
        # Calculate aggregate status
        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_uuid,
            pipeline_nodes=pipeline_nodes,
            embedding_nodes=embedding_nodes,
            target_models=target_models,
            index_nodes=index_nodes
        )
        
        # Build pipeline stages - 5 stages (upload, extract, normalize, chunk, archive)
        # index removed - it's an aggregate of embeddings status
        pipeline_stages = []
        for stage in ['upload', 'extract', 'normalize', 'chunk', 'archive']:
            node = next((n for n in pipeline_nodes if n.node_key == stage), None)
            if node:
                pipeline_stages.append(PipelineStage(
                    key=node.node_key,
                    status=node.status,
                    error=node.error_short,
                    metrics=node.metrics_json,
                    started_at=node.started_at.isoformat() if node.started_at else None,
                    finished_at=node.finished_at.isoformat() if node.finished_at else None,
                    updated_at=node.updated_at.isoformat()
                ))
            else:
                # Create default pending stage
                pipeline_stages.append(PipelineStage(
                    key=stage,
                    status='pending',
                    error=None,
                    metrics=None,
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime.now(timezone.utc).isoformat()
                ))
        
        # Build embedding models - show all existing embedding nodes, not just target_models
        embedding_models = []
        # First add all existing embedding nodes
        for node in embedding_nodes:
            embedding_models.append(EmbeddingModel(
                model=node.node_key,
                version=node.model_version,
                status=node.status,
                error=node.error_short,
                metrics=node.metrics_json,
                started_at=node.started_at.isoformat() if node.started_at else None,
                finished_at=node.finished_at.isoformat() if node.finished_at else None,
                updated_at=node.updated_at.isoformat()
            ))
        
        # Then add missing target models as pending
        existing_models = {node.node_key for node in embedding_nodes}
        for model in target_models:
            if model not in existing_models:
                embedding_models.append(EmbeddingModel(
                    model=model,
                    version=None,
                    status='pending',
                    error=None,
                    metrics=None,
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime.now(timezone.utc).isoformat()
                ))
        
        # Build index models array
        index_models: List[EmbeddingModel] = []
        for node in index_nodes:
            index_models.append(EmbeddingModel(
                model=node.node_key,
                version=node.model_version,
                status=node.status,
                error=node.error_short,
                metrics=node.metrics_json,
                started_at=node.started_at.isoformat() if node.started_at else None,
                finished_at=node.finished_at.isoformat() if node.finished_at else None,
                updated_at=node.updated_at.isoformat()
            ))
        
        # Add missing index entries for models that have embeddings but no index yet
        existing_index_models = {node.node_key for node in index_nodes}
        for emb_node in embedding_nodes:
            if emb_node.node_key not in existing_index_models:
                # Only show pending if embedding is completed
                if emb_node.status == 'completed':
                    index_models.append(EmbeddingModel(
                        model=emb_node.node_key,
                        version=emb_node.model_version,
                        status='pending',
                        error=None,
                        metrics=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=datetime.now(timezone.utc).isoformat()
                    ))
        
        # Clean agg_details - remove duplicate pipeline field
        clean_agg_details = {k: v for k, v in agg_details.items() if k != 'pipeline'}
        
        return StatusGraphResponse(
            doc_id=doc_id,
            pipeline=pipeline_stages,
            embeddings=embedding_models,
            index=index_models,
            agg_status=agg_status,
            agg_details=clean_agg_details
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        logger.error(f"Failed to get status graph for {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status graph: {str(e)}")

@router.get("/{doc_id}/models")
async def get_rag_document_models(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Get vectorized models for a document"""
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding nodes from status repository
        from app.repositories.rag_status_repo import AsyncRAGStatusRepository
        status_repo = AsyncRAGStatusRepository(session)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_uuid)
        
        # Get target models for tenant
        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_uuid)
        
        # Build list of vectorized models (with status 'completed')
        vectorized_models = []
        for node in embedding_nodes:
            if node.status == 'completed':
                vectorized_models.append({
                    "alias": node.node_key,
                    "version": node.model_version,
                    "status": node.status
                })
        
        # Get all available models from config
        from app.core.config import get_embedding_models
        available_models = get_embedding_models()
        
        return {
            "id": doc_id,
            "vectorized_models": [m["alias"] for m in vectorized_models],
            "vectorized_models_detail": vectorized_models,
            "target_models": target_models,
            "available_models": available_models
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")

@router.post("/upload/presign")
def presign_rag_upload(body: dict[str, Any]) -> dict:
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

