from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date

class ChatMessage(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool']
    content: str
    created_at: Optional[datetime] = Field(None)

class ChatTurnRequest(BaseModel):
    response_stream: Optional[bool] = Field(None)
    use_rag: Optional[bool] = Field(None)
    rag_params: Optional[Dict[str, Any]] = Field(None)
    messages: Optional[List[ChatMessage]] = Field(None)
    temperature: Optional[float] = Field(None)
    max_tokens: Optional[int] = Field(None)
    idempotency_key: Optional[str] = Field(None)

class ChatTurnResponse(BaseModel):
    chat_id: Optional[str] = Field(None)
    message_id: Optional[str] = Field(None)
    created_at: Optional[datetime] = Field(None)
    assistant_message: Optional[ChatMessage] = Field(None)
    usage: Optional[Dict[str, Any]] = Field(None)
    rag: Optional[Dict[str, Any]] = Field(None)
