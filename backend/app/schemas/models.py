from pydantic import BaseModel, Field
from typing import Any, List, Optional

# --- Чат ---
class ChatMessage(BaseModel):
    message: str = Field(..., description="Сообщение пользователя")
    session_id: Optional[str] = Field(None, description="ID сессии чата (опционально)")

class ChatReply(BaseModel):
    reply: str
    session_id: Optional[str] = None

# --- Чат с RAG ---
class RAGChatRequest(BaseModel):
    message: str
    top_k: int = 5

class RAGChatReply(BaseModel):
    reply: str
    references: List[dict] = []  # [{"id": "doc1", "score": 0.9}] (заглушка)

# --- Анализ документа с RAG ---
class AnalyzeRequest(BaseModel):
    document_id: str
    question: str
    top_k: int = 5

class AnalyzeResponse(BaseModel):
    summary: str
    references: List[dict] = []

# --- Действия с RAG ---
class RAGAddRequest(BaseModel):
    items: List[dict]  # [{"id": "doc1", "text": "..."}, ...]

class RAGListResponse(BaseModel):
    items: List[dict]

class RAGDeleteResponse(BaseModel):
    deleted: List[str]

class RAGReindexResponse(BaseModel):
    status: str
    details: Optional[Any] = None

