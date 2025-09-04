from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# --- Базовые типы сообщений ---
Role = Literal["system", "user", "assistant"]

class ChatMessageIn(BaseModel):
    role: Role
    content: str = Field(..., min_length=1)

class ChatMessageOut(BaseModel):
    id: Optional[int] = None       # для истории из БД (может быть None для стрима)
    role: Literal["user", "assistant"]
    content: str

# --- Чат ---
class ChatOut(BaseModel):
    id: int
    title: str
    rag_enabled: bool = False

    class Config:
        from_attributes = True

# --- Создание чата "вручную" (не используется в новой логике, но оставим на будущее) ---
class ChatCreate(BaseModel):
    title: Optional[str] = None
    rag_enabled: bool = False

class ChatUpdate(BaseModel):
    title: Optional[str] = None
    rag_enabled: Optional[bool] = None

# --- Запросы/ответы на отправку сообщений ---
class ChatSendRequest(BaseModel):
    messages: List[ChatMessageIn]
    use_rag: bool
    temperature: Optional[float] = 0.2
    top_k: Optional[int] = 5

class ChatSendResponse(BaseModel):
    assistant: ChatMessageOut
    references: Optional[List[dict]] = None

class ChatCreatedResponse(BaseModel):
    chat: ChatOut
    assistant: ChatMessageOut
    references: Optional[List[dict]] = None
