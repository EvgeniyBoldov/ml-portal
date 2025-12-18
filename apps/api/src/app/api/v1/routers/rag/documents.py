"""
RAG Documents CRUD endpoints.
"""
from __future__ import annotations
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager
from app.services.status_aggregator import calculate_aggregate_status

logger = get_logger(__name__)

router = APIRouter()


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
    """List RAG documents with pagination and search"""
    try:
        rag_repo = repo_factory.get_rag_documents_repository()
        
        documents = await rag_repo.get_tenant_documents(
            status=status,
            search=search,
            limit=size,
            offset=(page - 1) * size
        )
        
        total_count = await rag_repo.count_tenant_documents(
            status=status,
            search=search
        )
        
        items = []
        for doc in documents:
            if doc.agg_status is None:
                try:
                    from app.repositories.rag_status_repo import AsyncRAGStatusRepository
                    status_repo = AsyncRAGStatusRepository(session)
                    
                    pipeline_nodes = await status_repo.get_pipeline_nodes(doc.id)
                    embedding_nodes = await status_repo.get_embedding_nodes(doc.id)
                    
                    status_manager = RAGStatusManager(session, repo_factory)
                    target_models = await status_manager._get_target_models(doc.id)
                    
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
            
            vectorized_models = []
            if 'embedding_nodes' in locals() and embedding_nodes:
                vectorized_models = [
                    node.node_key for node in embedding_nodes 
                    if node.status == 'completed'
                ]

            items.append({
                "id": str(doc.id),
                "name": doc.filename,
                "status": agg_status,
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
