"""
StructuredLLMCall — shared helper used by Triage, Planner and Synthesizer.

Responsibilities:
    * Render role system prompt + structured JSON user payload
    * Call LLM with timeout + retries
    * Extract JSON (handles ```json fences and prose wrappers)
    * Validate against Pydantic schema; fall back or raise
    * Log a SystemLLMTrace row for observability

Callers get a typed `StructuredCallResult` with the parsed model instance and
the trace_id they can attach to downstream events.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredCallError(RuntimeError):
    """Raised when LLM output cannot be coerced into the requested schema."""


@dataclass
class StructuredCallResult(Generic[T]):
    value: T
    trace_id: Optional[UUID]
    raw_response: str
    duration_ms: int


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


class StructuredLLMCall:
    """Thin, reusable wrapper over LLM chat for structured (JSON) outputs."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.role_service = SystemLLMRoleService(session)
        # Trace logging deferred: v3 pipeline will use a dedicated RuntimeTrace
        # service (see TODO in runtime/__init__.py). For now traces are skipped
        # and trace_id is returned as None.

    async def invoke(
        self,
        *,
        role: SystemLLMRoleType,
        payload: Dict[str, Any],
        schema: Type[T],
        system_prompt: Optional[str] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None,
        fallback_factory: Optional[Callable[[str], T]] = None,
    ) -> StructuredCallResult[T]:
        """Execute the role with structured JSON payload, validate output against `schema`.

        Args:
            role: SystemLLMRoleType — used only for model/temperature/timeout
                  configuration (retrieved from `system_llm_roles` table).
            system_prompt: Prompt text to use. If None, falls back to the
                  DB-stored compiled_prompt for the role.
            payload: JSON-serializable dict passed as user message.
            schema: Pydantic class the result must validate against.
            fallback_factory: Called with raw response if validation fails;
                  if it returns a valid instance, we use it instead of raising.
        """
        role_config = await self.role_service.get_role_config(role)

        system_prompt = system_prompt or role_config["prompt"]
        user_message = json.dumps(payload, ensure_ascii=False, default=str)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        model = role_config.get("model") or "unknown"
        timeout_s = int(role_config.get("timeout_s") or 30)
        max_retries = int(role_config.get("max_retries") or 2)
        temperature = role_config.get("temperature")
        max_tokens = role_config.get("max_tokens")
        params: Dict[str, Any] = {}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        last_error: Optional[str] = None
        raw_response = ""
        start = time.time()

        for attempt in range(max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self.llm_client.chat(messages, model=model, params=params or None),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                last_error = f"llm_timeout after {timeout_s}s (attempt {attempt + 1})"
                logger.warning("StructuredLLMCall timeout role=%s attempt=%s", role, attempt + 1)
                continue
            except Exception as exc:  # network / upstream failure
                last_error = f"llm_error: {exc}"
                logger.warning("StructuredLLMCall error role=%s attempt=%s: %s", role, attempt + 1, exc)
                if self._is_non_retryable_llm_error(exc):
                    logger.warning(
                        "StructuredLLMCall fail-fast role=%s attempt=%s due to non-retryable upstream error",
                        role,
                        attempt + 1,
                    )
                    break
                continue

            raw_response = self._extract_text(response)
            if not raw_response:
                last_error = "empty_response"
                continue

            try:
                parsed = self._parse_and_validate(raw_response, schema)
            except StructuredCallError as exc:
                last_error = str(exc)
                logger.info(
                    "StructuredLLMCall schema mismatch role=%s attempt=%s: %s",
                    role, attempt + 1, exc,
                )
                continue

            duration_ms = int((time.time() - start) * 1000)
            return StructuredCallResult(
                value=parsed,
                trace_id=None,
                raw_response=raw_response,
                duration_ms=duration_ms,
            )

        # All attempts failed — try fallback factory if provided.
        duration_ms = int((time.time() - start) * 1000)
        if fallback_factory is not None:
            try:
                fallback = fallback_factory(raw_response)
                return StructuredCallResult(
                    value=fallback,
                    trace_id=None,
                    raw_response=raw_response,
                    duration_ms=duration_ms,
                )
            except Exception as fallback_exc:
                logger.error("StructuredLLMCall fallback failed role=%s: %s", role, fallback_exc)

        raise StructuredCallError(
            f"LLM failed to produce a valid {schema.__name__} after "
            f"{max_retries + 1} attempts: {last_error}"
        )

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract assistant text from LLMClient response (OpenAI-style or string)."""
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            try:
                choices = response.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                direct = response.get("content") or response.get("text")
                if isinstance(direct, str):
                    return direct
            except Exception:
                pass
        return str(response or "")

    @classmethod
    def _parse_and_validate(cls, raw: str, schema: Type[T]) -> T:
        data = cls._extract_json(raw)
        if data is None:
            raise StructuredCallError("no JSON block detected in LLM response")
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise StructuredCallError(f"schema validation failed: {exc.errors()}") from exc

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
        text = (text or "").strip()
        if not text:
            return None
        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2. Fenced code block
        match = _JSON_FENCE.search(text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 3. Greedy braces
        match = _JSON_OBJECT.search(text)
        if match:
            candidate = match.group(1)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _is_non_retryable_llm_error(exc: Exception) -> bool:
        """Detect upstream failures where immediate retry is wasteful.

        Focus on payload/token-limit failures:
        - HTTP 413 request too large / context too long
        - explicit provider token rate-limit exceeded for current request size
        """
        text = str(exc or "").lower()
        if not text:
            return False
        patterns = (
            "error code: 413",
            "request too large",
            "context_length_exceeded",
            "maximum context length",
            "rate_limit_exceeded",
            "tokens per minute",
        )
        return any(p in text for p in patterns)
