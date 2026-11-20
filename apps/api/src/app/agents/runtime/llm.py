"""
LLMAdapter — обёртка над LLMClientProtocol для удобной работы в runtime.

Инкапсулирует:
- Синхронный вызов (call) с нормализацией ответа
- Стриминг (stream) с нормализацией чанков
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from app.core.http.clients import LLMClientProtocol
from app.adapters.interfaces.llm import LLMCallOptions
from app.core.logging import get_logger
from app.agents.runtime.llm_errors import classify_provider_error

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
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout_s: Optional[int] = None,
        on_transport_retry: Optional[Callable[[], Awaitable[None]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Non-streaming LLM call. Returns plain text response."""
        try:
            params: Dict[str, Any] = {"temperature": temperature}
            if tools:
                params["tools"] = tools
            if response_format:
                params["response_format"] = response_format
            request = self._client.chat(messages=messages, model=model, params=params,
                                        options=LLMCallOptions(timeout_s=timeout_s, on_transport_retry=on_transport_retry))
            response = await asyncio.wait_for(request, timeout=timeout_s) if timeout_s else await request
        except Exception as e:
            classified = classify_provider_error(e)
            if classified is not None:
                raise classified from e
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

        return self._normalize_response(response)

    async def call_raw(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        force_tool_choice: bool = False,
        timeout_s: Optional[int] = None,
        on_transport_retry: Optional[Callable[[], Awaitable[None]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Non-streaming LLM call. Returns raw response dict for native tool_calls parsing.

        When ``force_tool_choice=True`` the provider is instructed to call a tool
        (``tool_choice="required"``). Use this on retry steps where the model
        skipped a required tool call on the previous iteration.
        """
        params: Dict[str, Any] = {"temperature": temperature}
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "required" if force_tool_choice else "auto"
        if response_format:
            params["response_format"] = response_format
        try:
            request = self._client.chat(messages=messages, model=model, params=params,
                                        options=LLMCallOptions(timeout_s=timeout_s, on_transport_retry=on_transport_retry))
            return await asyncio.wait_for(request, timeout=timeout_s) if timeout_s else await request
        except Exception as e:
            classified = classify_provider_error(e)
            if classified is not None:
                raise classified from e
            logger.error(f"LLM call_raw failed: {e}", exc_info=True)
            raise

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        timeout_s: Optional[int] = None,
        on_transport_retry: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming LLM call. Yields normalized text chunks."""
        params: Dict[str, Any] = {"temperature": temperature}

        stream = self._client.chat_stream(messages=messages, model=model, params=params,
                                          options=LLMCallOptions(timeout_s=timeout_s, on_transport_retry=on_transport_retry))
        if timeout_s:
            async with asyncio.timeout(timeout_s):
                async for chunk in stream:
                    text = self._normalize_chunk(chunk)
                    if text:
                        yield text
            return
        async for chunk in stream:
            text = self._normalize_chunk(chunk)
            if text:
                yield text

    def normalize_response(self, response: Any) -> str:
        """Public entry point: normalize any LLM response format to plain text."""
        return self._normalize_response(response)

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


