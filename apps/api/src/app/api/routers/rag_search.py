from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from app.core.db import get_db
from app.core.auth import get_current_user
from app.core.error_handling import create_error_response
from app.services.multi_index_search import multi_index_search
from app.core.config import settings

router = APIRouter(prefix="/rag-search", tags=["rag-search"])

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Поисковый запрос")
    chat_models: Optional[List[str]] = Field(None, description="Модели для чата")
    rag_models: Optional[List[str]] = Field(None, description="Модели для RAG")
    limit: int = Field(10, ge=1, le=100, description="Количество результатов")
    score_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Минимальный порог релевантности")
    rrf_rank: int = Field(60, ge=1, le=1000, description="Параметр R для RRF")

class SearchResult(BaseModel):
    id: str = Field(..., description="ID документа")
    score: float = Field(..., description="Релевантность (RRF score)")
    text: str = Field(..., description="Текст документа")
    snippet: str = Field(..., description="Сниппет для отображения")
    source: dict = Field(..., description="Источник документа")
    sources: List[dict] = Field(..., description="Все источники (модели)")

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str
    models_used: List[str]
    search_time_ms: float

@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    import time
    start_time = time.time()
    try:
        raw_results = await multi_index_search.search(
            query=request.query,
            chat_models=request.chat_models,
            rag_models=request.rag_models,
            limit=request.limit,
            score_threshold=request.score_threshold,
            rrf_rank=request.rrf_rank,
        )
        formatted_results = []
        for result in raw_results:
            payload = result.get("payload", {})
            formatted_results.append(SearchResult(
                id=str(result["id"]),
                score=result["score"],
                text=payload.get("text", ""),
                snippet=payload.get("snippet", payload.get("text", "")[:200] + "..."),
                source=payload.get("source", {}),
                sources=result.get("sources", []),
            ))
        models_used = sorted({src.get("alias", "unknown") for r in raw_results for src in r.get("sources", [])})
        return SearchResponse(
            results=formatted_results,
            total=len(formatted_results),
            query=request.query,
            models_used=models_used,
            search_time_ms=(time.time() - start_time) * 1000,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=create_error_response("search_failed", f"Search failed: {str(e)}").model_dump())

@router.get("/models")
async def get_available_models(current_user: dict = Depends(get_current_user)):
    return {
        "chat_models": settings.CHAT_EMB_MODELS,
        "rag_models": settings.RAG_EMB_MODELS,
        "default_models": {
            "chat": settings.CHAT_EMB_MODELS[0] if settings.CHAT_EMB_MODELS else "minilm",
            "rag": settings.RAG_EMB_MODELS[0] if settings.RAG_EMB_MODELS else "minilm",
        },
    }
