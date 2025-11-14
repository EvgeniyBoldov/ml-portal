"""
RAG Search API endpoints
"""
from __future__ import annotations
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.db import get_session_factory
from app.services.rag_search_service import RagSearchService, SearchResult
from app.repositories.rag_ingest_repos import AsyncEmbStatusRepository, AsyncSourceRepository
from app.models.user import Users

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag-search"])


class SearchResultResponse(BaseModel):
    """Ответ с результатом поиска"""
    text: str
    score: float
    source_id: str
    chunk_id: str
    page: int
    model_hits: List[dict] = Field(description="Результаты по каждой модели")
    meta: dict = Field(description="Метаданные чанка")


class SearchResponse(BaseModel):
    """Ответ на поисковый запрос"""
    results: List[SearchResultResponse]
    total: int
    query: str
    models_used: List[str]


class SourceStatusResponse(BaseModel):
    """Статус источника"""
    status: str
    progress: List[dict] = Field(description="Прогресс по моделям")
    updated_at: str


@router.get("/search", response_model=SearchResponse)
async def search_rag(
    query: str = Query(..., description="Поисковый запрос"),
    k: int = Query(5, ge=1, le=50, description="Количество результатов"),
    models: Optional[str] = Query(None, description="Модели для поиска (через запятую)"),
    current_user: Users = Depends(get_current_user)
):
    """
    Поиск по RAG данным
    
    Args:
        query: Поисковый запрос
        k: Количество результатов (1-50)
        models: Список моделей через запятую (например: "all-MiniLM-L6-v2,all-MiniLM-L12-v2")
        current_user: Текущий пользователь
        
    Returns:
        Результаты поиска с цитатами и метаданными
    """
    try:
        # TODO: Integrate with model_registry - check tenant_profile.embed_models state='active'
        # Should use only active embedding models from tenant profile for query encoding
        # and active rerank model for result reranking
        
        # Получаем tenant_id из пользователя
        tenant_id = current_user.tenant_ids[0] if current_user.tenant_ids else "fb983a10-c5f8-4840-a9d3-856eea0dc729"  # Default tenant
        
        # Парсим модели
        model_list = None
        if models:
            model_list = [m.strip() for m in models.split(",") if m.strip()]
        
        # Выполняем поиск
        search_service = RagSearchService()
        results = await search_service.search(
            tenant_id=tenant_id,
            query=query,
            k=k,
            models=model_list
        )
        
        # Конвертируем в response модель
        response_results = []
        for result in results:
            response_results.append(SearchResultResponse(
                text=result.text,
                score=result.score,
                source_id=result.source_id,
                chunk_id=result.chunk_id,
                page=result.page,
                model_hits=result.model_hits,
                meta=result.meta
            ))
        
        return SearchResponse(
            results=response_results,
            total=len(response_results),
            query=query,
            models_used=model_list or ["all-MiniLM-L6-v2"]
        )
        
    except Exception as e:
        logger.error(f"Error in RAG search: {e}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/sources/{source_id}/status", response_model=SourceStatusResponse)
async def get_source_status(
    source_id: str,
    current_user: Users = Depends(get_current_user)
):
    """
    Получить статус источника и прогресс обработки
    
    Args:
        source_id: ID источника
        current_user: Текущий пользователь
        
    Returns:
        Статус источника и прогресс по моделям
    """
    try:
        # Получаем tenant_id из пользователя
        tenant_id = current_user.tenant_ids[0] if current_user.tenant_ids else "fb983a10-c5f8-4840-a9d3-856eea0dc729"  # Default tenant
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            source_repo = AsyncSourceRepository(session, UUID(tenant_id))
            emb_status_repo = AsyncEmbStatusRepository(session, UUID(tenant_id))
            
            # Получаем источник
            source = await source_repo.get_by_id(UUID(source_id))
            if not source:
                raise HTTPException(status_code=404, detail="Source not found")
            
            # Получаем статусы эмбеддингов
            emb_statuses = await emb_status_repo.get_by_source_id(UUID(source_id))
            
            # Формируем прогресс
            progress = []
            for emb_status in emb_statuses:
                progress.append({
                    "alias": emb_status.model_alias,
                    "done": emb_status.done_count,
                    "total": emb_status.total_count,
                    "version": emb_status.model_version
                })
            
            return SourceStatusResponse(
                status=source.status,
                progress=progress,
                updated_at=source.updated_at.isoformat() if source.updated_at else ""
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting source status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")