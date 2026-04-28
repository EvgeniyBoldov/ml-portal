"""
LLMAdapter — обёртка над LLMClientProtocol для удобной работы в runtime.

Инкапсулирует:
- Синхронный вызов (call) с нормализацией ответа
- Стриминг (stream) с нормализацией чанков
"""
from __future__ import annotations

import json
import re
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
            fallback = self._coerce_tool_choice_error_to_operation_call(e)
            if fallback is not None:
                logger.warning(
                    "LLM returned tool_use_failed/tool_choice mismatch; coercing failed_generation to operation_call block",
                )
                return fallback
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

        return self._normalize_response(response)

    async def call_raw(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        force_tool_choice: bool = False,
    ) -> Any:
        """Non-streaming LLM call. Returns raw response dict for native tool_calls parsing.

        When ``force_tool_choice=True`` the provider is instructed to call a tool
        (``tool_choice="required"``). Use this on retry steps where the model
        skipped a required tool call on the previous iteration.
        """
        params: Dict[str, Any] = {"temperature": temperature}
        if max_tokens:
            params["max_tokens"] = max_tokens
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "required" if force_tool_choice else "auto"
        try:
            return await self._client.chat(messages=messages, model=model, params=params)
        except Exception as e:
            logger.error(f"LLM call_raw failed: {e}", exc_info=True)
            raise

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

    @staticmethod
    def _coerce_tool_choice_error_to_operation_call(exc: Exception) -> Optional[str]:
        """Convert provider tool-choice mismatch into textual operation_call protocol.

        Some OpenAI-compatible providers (e.g. Groq) return HTTP 400 with
        error.code=tool_use_failed and a failed_generation payload when
        tool_choice=none but the model tried to call a tool anyway.
        Salvage the call by converting it to a textual operation_call block.
        """
        # Path 1: openai SDK — structured body dict, no string parsing needed
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error") or {}
            if isinstance(error, dict) and error.get("code") == "tool_use_failed":
                raw = error.get("failed_generation") or ""
                payload = None
                if isinstance(raw, dict):
                    payload = raw
                elif isinstance(raw, str):
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        pass
                if isinstance(payload, dict) and payload.get("name"):
                    op_name = str(payload["name"]).strip()
                    arguments = payload.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    call = {"operation": op_name, "arguments": arguments}
                    return "```operation_call\n" + json.dumps(call, ensure_ascii=False, indent=2) + "\n```"

        # Path 2: non-openai providers — plain string heuristic
        text = str(exc or "")
        lowered = text.lower()
        if "tool_use_failed" not in lowered and "tool choice is none" not in lowered:
            return None

        payload = LLMAdapter._extract_failed_generation_json(text)
        if payload is None:
            return None

        op_name = str(payload.get("name") or "").strip()
        if not op_name:
            return None
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        call = {"operation": op_name, "arguments": arguments}
        return "```operation_call\n" + json.dumps(call, ensure_ascii=False, indent=2) + "\n```"

    @staticmethod
    def _extract_failed_generation_json(text: str) -> Optional[Dict[str, Any]]:
        marker_idx = text.find("failed_generation")
        if marker_idx < 0:
            return None

        # Path 1: Groq Python-repr format — 'failed_generation': '{"name": ..., "arguments": ...}'
        # The JSON payload is a single-quoted string value in the Python repr of the error dict.
        quote_start = text.find("'", marker_idx)
        if quote_start >= 0:
            # skip past the key's closing quote and colon/space to reach the value quote
            val_quote = text.find("'", quote_start + 1)
            if val_quote >= 0 and text[val_quote] == "'":
                end_quote = text.find("'", val_quote + 1)
                if end_quote > val_quote:
                    candidate = text[val_quote + 1:end_quote]
                    for raw in (candidate, LLMAdapter._unescape_json_candidate(candidate)):
                        if not raw:
                            continue
                        try:
                            data = json.loads(raw)
                        except Exception:
                            pass
                        else:
                            if isinstance(data, dict) and "name" in data:
                                return data

        # Path 2: standard inline JSON object after the marker
        start = text.find("{", marker_idx)
        if start < 0:
            return None
        candidate = LLMAdapter._extract_balanced_braces(text, start)
        if not candidate:
            return None
        for raw in (candidate, LLMAdapter._unescape_json_candidate(candidate)):
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if isinstance(data, dict) and "name" in data:
                return data
        return None

    @staticmethod
    def _extract_balanced_braces(text: str, start: int) -> Optional[str]:
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        return None

    @staticmethod
    def _unescape_json_candidate(value: str) -> str:
        if not value:
            return value
        try:
            return re.sub(r"\\\\([\"\\\\/bfnrt])", r"\\\1", value)
        except Exception:
            return value
