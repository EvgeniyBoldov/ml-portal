
from __future__ import annotations
from typing import Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(..., pattern="^(user|system|assistant|tool)$")
    content: Union[str, Dict[str, Any]]

    @field_validator('content')
    @classmethod
    def non_empty(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("content must be non-empty")
        if isinstance(v, dict) and not v:
            raise ValueError("content dict must be non-empty")
        return v

    @classmethod
    def create_user_message(cls, text: str) -> "ChatMessage":
        return cls(role="user", content=text)

    @classmethod
    def create_system_message(cls, text: str) -> "ChatMessage":
        return cls(role="system", content=text)

    @classmethod
    def create_assistant_message(cls, text: str) -> "ChatMessage":
        return cls(role="assistant", content=text)

    @classmethod
    def create_tool_message(cls, tool_call_id: str, content: str) -> "ChatMessage":
        return cls(role="tool", content={'tool_call_id': tool_call_id, 'content': content})
