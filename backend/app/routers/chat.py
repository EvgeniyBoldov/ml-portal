from fastapi import APIRouter, Depends
from app.schemas.models import ChatMessage, ChatReply, RAGChatRequest, RAGChatReply
from app.core.dependencies import current_user

router = APIRouter()

@router.post("/message", response_model=ChatReply)
async def chat_message(payload: ChatMessage, user = Depends(current_user)):
    # Заглушка: просто эхо-ответ
    return ChatReply(reply=f"echo: {payload.message}", session_id=payload.session_id)

@router.post("/rag", response_model=RAGChatReply)
async def chat_with_rag(payload: RAGChatRequest, user = Depends(current_user)):
    # Заглушка: эхо и фиктивные ссылки
    refs = [{"id": f"doc_{i}", "score": 1.0 - i*0.1} for i in range(min(3, payload.top_k))]
    return RAGChatReply(reply=f"rag-echo: {payload.message}", references=refs)

