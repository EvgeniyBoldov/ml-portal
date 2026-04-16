"""
LLMAdapter — обёртка над LLMClientProtocol для удобной работы в runtime.

Инкапсулирует:
- Синхронный вызов (call) с нормализацией ответа
- Стриминг (stream) с нормализацией чанков
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMAdapter:
    """Thin wrapper over LLMClientProtocol with response normalization."""

    def __init__(self, client: LLMClientProtocol) -> None:
        self._client = client

    @property
    def raw_client(self) -> LLMClientProtocol:
        """Access the underlying client (for edge cases)."""
        return self._client

    async def call(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Non-streaming LLM call. Returns plain text response."""
        try:
            params: Dict[str, Any] = {"temperature": temperature}
            if max_tokens:
                params["max_tokens"] = max_tokens
            if tools:
                params["tools"] = tools
            response = await self._client.chat(
                messages=messages, model=model, params=params,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

        return self._normalize_response(response)

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming LLM call. Yields normalized text chunks."""
        params: Dict[str, Any] = {"temperature": temperature}
        if max_tokens:
            params["max_tokens"] = max_tokens

        async for chunk in self._client.chat_stream(
            messages=messages, model=model, params=params,
        ):
            text = self._normalize_chunk(chunk)
            if text:
                yield text

    @staticmethod
    def _normalize_response(response: Any) -> str:
        """Normalize any LLM response format to plain text."""
        if hasattr(response, "text"):
            return str(response.text or "")
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                return str(choices[0].get("message", {}).get("content", ""))
            return str(response.get("content", ""))
        return str(response or "")

    @staticmethod
    def _normalize_chunk(chunk: Any) -> str:
        """Normalize a streaming chunk to plain text."""
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            return chunk.get("content", "") or ""
        return str(chunk) if chunk else ""
