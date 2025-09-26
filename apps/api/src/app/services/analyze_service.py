from __future__ import annotations
from .rag_ingest_service import RagIngestService
from .rag_search_service import RagSearchService
from .chat_service import ChatService, ChatResult

class AnalyzeService:
    def __init__(self, ingest: RagIngestService, search: RagSearchService, chat: ChatService):
        self._ingest = ingest
        self._search = search
        self._chat = chat

    def analyze(self, tenant_id: str, doc_id: str, question: str, k: int = 5, model: str = "") -> ChatResult:
        return ChatResult(text="TODO", citations=[])
