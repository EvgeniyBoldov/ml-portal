"""
RAG Status endpoints (status-graph, models).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{doc_id}/status-graph")
async def get_status_graph(
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Compatibility endpoint using the canonical document status graph builder."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    document = await repo_factory.get_rag_document_by_id(doc_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.services.rag_status_snapshot import build_document_status_graph

    graph = await build_document_status_graph(session, doc_uuid, repo_factory)
    if graph is None:
        raise HTTPException(status_code=500, detail="Failed to build document status graph")
    return graph

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
        
        from app.repositories.rag_status_repo import AsyncRAGStatusRepository
        status_repo = AsyncRAGStatusRepository(session)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_uuid)
        
        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_uuid)
        
        vectorized_models = []
        for node in embedding_nodes:
            if node.status == 'completed':
                vectorized_models.append({
                    "alias": node.node_key,
                    "version": node.model_version,
                    "status": node.status
                })
        
        from sqlalchemy import text
        models_result = await session.execute(
            text(
                "SELECT alias FROM models "
                "WHERE type = 'EMBEDDING' AND enabled = true AND status = 'AVAILABLE' "
                "ORDER BY is_default DESC, alias ASC"
            )
        )
        available_models = [row[0] for row in models_result.all()]
        
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
