"""
RAG Document lifecycle endpoints (archive, unarchive, delete, scope, tags).
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, get_redis_client
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.models.rag import DocumentScope
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager
from app.services.rag_event_publisher import RAGEventPublisher

logger = get_logger(__name__)

router = APIRouter()


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
        
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="Tags must be a list")
        
        sanitized_tags = []
        for tag in tags:
            if tag and isinstance(tag, str):
                tag = tag.strip()
                if tag and len(tag) <= 50:
                    sanitized_tags.append(tag)
        
        document.tags = sanitized_tags
        document.updated_at = datetime.now(timezone.utc)
        
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


@router.post("/{doc_id}/archive")
async def archive_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Archive RAG document"""
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis)
        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
        
        await status_manager.archive_document(doc_uuid)
        
        document.status = "archived"
        document.updated_at = datetime.now(timezone.utc)
        
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
    try:
        doc_uuid = uuid.UUID(doc_id)
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        redis = get_redis_client()
        event_publisher = RAGEventPublisher(redis)
        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
        
        await status_manager.unarchive_document(doc_uuid)
        await status_manager._update_aggregate_status(doc_uuid)
        
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
        
        from app.workers.tasks_rag_ingest import cleanup_document_artifacts
        
        cleanup_document_artifacts.delay(
            str(document.tenant_id), 
            str(document.id)
        )
        
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
        
        if scope == "global":
            # Only admins can change scope to global
            if user.role != "admin":
                raise HTTPException(
                    status_code=403, 
                    detail="Only admins can change document scope to global"
                )
        
        document.scope = DocumentScope(scope)
        document.updated_at = datetime.now(timezone.utc)
        
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
