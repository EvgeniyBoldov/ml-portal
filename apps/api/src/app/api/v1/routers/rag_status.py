# app/api/v1/routers/rag_status.py
from __future__ import annotations
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.api.deps import db_session, get_current_user, require_editor_or_admin
from app.core.security import UserCtx
from app.repositories.factory import AsyncRepositoryFactory, get_async_repository_factory
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG Status"])

@router.get("/{source_id}/status")
async def get_rag_source_status(
    source_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_editor_or_admin),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Get aggregated status for RAG source processing"""
    try:
        # Validate source_id
        try:
            source_uuid = uuid.UUID(source_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid source ID")
        
        # Get ingest repository
        ingest_repo = repo_factory.get_rag_ingest_repository()
        
        # Get source with relations
        source = await ingest_repo.get_source_with_relations(source_uuid)
        if not source:
            # Try to find in old RAG documents table as fallback
            rag_repo = repo_factory.get_rag_documents_repository()
            old_doc = await rag_repo.get_rag_document_by_id(source_uuid, user.role)
            if old_doc:
                # Create source record for old document
                await ingest_repo.create_source(
                    source_id=source_uuid,
                    status="ready" if old_doc.status == "processed" else "processing",
                    meta={"legacy_document": True, "original_status": old_doc.status}
                )
                source = await ingest_repo.get_source_with_relations(source_uuid)
            
            if not source:
                raise HTTPException(status_code=404, detail="Source not found")
        
        # Build status response
        status_response = {
            "source_id": str(source.source_id),
            "status": source.status,
            "stages": {
                "extract": {
                    "ok": source.status in ["normalized", "chunked", "embedding", "ready"],
                    "at": source.created_at.isoformat() if source.status in ["normalized", "chunked", "embedding", "ready"] else None
                },
                "chunk": {
                    "ok": source.status in ["chunked", "embedding", "ready"],
                    "total_chunks": len(source.chunks) if source.chunks else 0
                },
                "embed": {}
            },
            "updated_at": source.updated_at.isoformat()
        }
        
        # Add embedding status for each model
        for emb_status in source.emb_statuses:
            status_response["stages"]["embed"][emb_status.model_alias] = {
                "done": emb_status.done_count,
                "total": emb_status.total_count,
                "model_version": emb_status.model_version,
                "last_error": emb_status.last_error,
                "updated_at": emb_status.updated_at.isoformat()
            }
        
        return status_response
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        logger.error(f"Failed to get source status {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get source status: {str(e)}")

@router.get("/{source_id}/progress")
async def get_rag_source_progress(
    source_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_editor_or_admin),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Get detailed progress for RAG source processing"""
    try:
        # Validate source_id
        try:
            source_uuid = uuid.UUID(source_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid source ID")
        
        # Get ingest repository
        ingest_repo = repo_factory.get_rag_ingest_repository()
        
        # Get source with relations
        source = await ingest_repo.get_source_with_relations(source_uuid)
        if not source:
            # Try to find in old RAG documents table as fallback
            rag_repo = repo_factory.get_rag_documents_repository()
            old_doc = await rag_repo.get_rag_document_by_id(source_uuid, user.role)
            if old_doc:
                # Create source record for old document
                await ingest_repo.create_source(
                    source_id=source_uuid,
                    status="ready" if old_doc.status == "processed" else "processing",
                    meta={"legacy_document": True, "original_status": old_doc.status}
                )
                source = await ingest_repo.get_source_with_relations(source_uuid)
            
            if not source:
                raise HTTPException(status_code=404, detail="Source not found")
        
        # Calculate overall progress
        total_stages = 4  # extract, chunk, embed, commit
        completed_stages = 0
        
        if source.status in ["normalized", "chunked", "embedding", "ready"]:
            completed_stages += 1  # extract completed
        
        if source.status in ["chunked", "embedding", "ready"]:
            completed_stages += 1  # chunk completed
        
        if source.status in ["embedding", "ready"]:
            completed_stages += 1  # embedding in progress or completed
        
        if source.status == "ready":
            completed_stages += 1  # commit completed
        
        # Calculate embedding progress
        embedding_progress = 0
        if source.emb_statuses:
            total_embeddings = sum(emb.total_count for emb in source.emb_statuses)
            done_embeddings = sum(emb.done_count for emb in source.emb_statuses)
            if total_embeddings > 0:
                embedding_progress = (done_embeddings / total_embeddings) * 100
        
        progress_response = {
            "source_id": str(source.source_id),
            "status": source.status,
            "overall_progress": (completed_stages / total_stages) * 100,
            "stage_progress": {
                "extract": 100 if source.status in ["normalized", "chunked", "embedding", "ready"] else 0,
                "chunk": 100 if source.status in ["chunked", "embedding", "ready"] else 0,
                "embed": embedding_progress,
                "commit": 100 if source.status == "ready" else 0
            },
            "chunks": {
                "total": len(source.chunks) if source.chunks else 0,
                "processed": sum(emb.done_count for emb in source.emb_statuses) if source.emb_statuses else 0
            },
            "models": {
                emb.model_alias: {
                    "progress": (emb.done_count / emb.total_count * 100) if emb.total_count > 0 else 0,
                    "done": emb.done_count,
                    "total": emb.total_count,
                    "version": emb.model_version,
                    "error": emb.last_error
                }
                for emb in source.emb_statuses
            },
            "updated_at": source.updated_at.isoformat()
        }
        
        return progress_response
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        logger.error(f"Failed to get source progress {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get source progress: {str(e)}")
