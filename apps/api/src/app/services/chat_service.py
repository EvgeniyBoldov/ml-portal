from __future__ import annotations
from typing import List, Dict, Any, Optional, Iterable

class ChatResult:
    def __init__(self, text: str, citations: Optional[List[Dict[str, Any]]] = None):
        self.text = text
        self.citations = citations or []

class ChatService:
    def __init__(self, llm_client: Any):
        self._llm = llm_client

    def chat(self, tenant_id: str, messages: List[Dict[str, str]], model: str, **gen_params) -> ChatResult:
        return ChatResult(text="TODO")

    def chat_stream(self, tenant_id: str, messages: List[Dict[str, str]], model: str, **gen_params) -> Iterable[str]:
        yield "TODO"
