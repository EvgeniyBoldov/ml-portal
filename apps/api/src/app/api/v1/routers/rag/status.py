"""
RAG Status endpoints (status-graph, models).
"""
from __future__ import annotations
from typing import List
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager
from app.services.status_aggregator import calculate_aggregate_status

from .schemas import StatusGraphResponse, PipelineStage, EmbeddingModel

logger = get_logger(__name__)

router = APIRouter()


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
        
        document = await repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        from app.repositories.rag_status_repo import AsyncRAGStatusRepository
        status_repo = AsyncRAGStatusRepository(session)
        
        pipeline_nodes = await status_repo.get_pipeline_nodes(doc_uuid)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_uuid)
        index_nodes = await status_repo.get_index_nodes(doc_uuid)
        
        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_uuid)
        
        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_uuid,
            pipeline_nodes=pipeline_nodes,
            embedding_nodes=embedding_nodes,
            target_models=target_models,
            index_nodes=index_nodes
        )
        
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
                pipeline_stages.append(PipelineStage(
                    key=stage,
                    status='pending',
                    error=None,
                    metrics=None,
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime.now(timezone.utc).isoformat()
                ))
        
        embedding_models = []
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
        
        existing_index_models = {node.node_key for node in index_nodes}
        for emb_node in embedding_nodes:
            if emb_node.node_key not in existing_index_models:
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
