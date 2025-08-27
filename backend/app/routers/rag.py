from fastapi import APIRouter, Depends
from app.schemas.models import (
    RAGAddRequest, RAGListResponse, RAGDeleteResponse, RAGReindexResponse
)
from app.core.dependencies import current_user

router = APIRouter()

# Простейшее in-memory хранилище (только для заглушек)
_FAKE_VECTOR_STORE: dict[str, dict] = {}

@router.post("/vectors", response_model=RAGListResponse)
async def rag_add(payload: RAGAddRequest, user = Depends(current_user)):
    for item in payload.items:
        _FAKE_VECTOR_STORE[str(item.get("id"))] = item
    return RAGListResponse(items=list(_FAKE_VECTOR_STORE.values()))

@router.get("/vectors", response_model=RAGListResponse)
async def rag_list(user = Depends(current_user)):
    return RAGListResponse(items=list(_FAKE_VECTOR_STORE.values()))

@router.delete("/vectors/{item_id}", response_model=RAGDeleteResponse)
async def rag_delete(item_id: str, user = Depends(current_user)):
    deleted: list[str] = []
    if item_id in _FAKE_VECTOR_STORE:
        _FAKE_VECTOR_STORE.pop(item_id, None)
        deleted.append(item_id)
    return RAGDeleteResponse(deleted=deleted)

@router.post("/vectors/reindex", response_model=RAGReindexResponse)
async def rag_reindex(user = Depends(current_user)):
    # Заглушка: ничего не делаем, просто возвращаем статус
    return RAGReindexResponse(status="ok", details={"count": len(_FAKE_VECTOR_STORE)})
