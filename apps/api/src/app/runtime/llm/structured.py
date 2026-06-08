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
from app.models.execution_limit import ExecutionLimitScope
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.limits import LLMLimitExceededError, apply_llm_limits, estimate_tokens
from app.services.execution_limits_service import ExecutionLimitsPayload, ExecutionLimitsService, apply_limits_override
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
    model: str
    request_messages: list[dict[str, Any]]
    request_params: dict[str, Any]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


_ROLE_PROMPT_SECTIONS = [
    ("identity", "IDENTITY"),
    ("mission", "MISSION"),
    ("rules", "RULES"),
    ("safety", "SAFETY"),
    ("output_requirements", "OUTPUT REQUIREMENTS"),
]


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
        self.limits_service = ExecutionLimitsService(session)
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
        sandbox_overrides: Optional[Dict[str, Any]] = None,
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

        role_key = str(role.value).strip().lower()
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get(role_key)

        # Apply model / temperature override from sandbox
        model = role_config.get("model") or "unknown"
        temperature = role_config.get("temperature")
        if isinstance(role_override, dict):
            if role_override.get("model"):
                model = str(role_override["model"])
            if role_override.get("temperature") is not None:
                temperature = float(role_override["temperature"])

        # Recompile system prompt if prompt parts are overridden
        system_prompt = system_prompt or self._compile_role_prompt(role_config, role_override)
        user_message = json.dumps(payload, ensure_ascii=False, default=str)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        timeout_s = int(role_config.get("timeout_s") or 30)
        max_retries = int(role_config.get("max_retries") or 2)
        max_tokens = role_config.get("max_tokens")
        params: Dict[str, Any] = {}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        try:
            limits = await self.limits_service.get_effective(
                scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
                scope_ref=str(role.value).strip().lower(),
            )
        except Exception:
            limits = ExecutionLimitsPayload()
        role_key = str(role.value).strip().lower()
        role_override = ((sandbox_overrides or {}).get("orchestrator_limits") or {}).get(role_key)
        limits = apply_limits_override(limits, role_override)
        input_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_message)
        boundary = apply_llm_limits(
            limits=limits,
            input_tokens=input_tokens,
            requested_output_tokens=(int(max_tokens) if max_tokens is not None else None),
        )
        if boundary.output_tokens is not None:
            params["max_tokens"] = int(boundary.output_tokens)

        # JSON schema enforcement: constrain LLM output to the Pydantic schema.
        # Works with OpenAI, Groq, and other providers supporting response_format.
        if schema is not None:
            try:
                json_schema = schema.model_json_schema()
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": json_schema,
                        "strict": False,  # strict mode too restrictive for nested dicts
                    },
                }
            except Exception as schema_err:
                logger.debug(
                    "Failed to generate JSON schema for response_format, falling back to json_object: %s",
                    schema_err,
                )
                params["response_format"] = {"type": "json_object"}

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
            except LLMLimitExceededError:
                raise
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
                model=model,
                request_messages=messages,
                request_params=dict(params or {}),
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
                    model=model,
                    request_messages=messages,
                    request_params=dict(params or {}),
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
        except ValidationError:
            # Fallback: coerce common LLM output mismatches (weak models often
            # return objects where strings are expected).
            coerced = cls._coerce_schema_types(data, schema)
            try:
                return schema.model_validate(coerced)
            except ValidationError as exc:
                raise StructuredCallError(f"schema validation failed: {exc.errors()}") from exc

    @staticmethod
    def _coerce_schema_types(data: Any, schema: Type[T]) -> Any:
        """Coerce common weak-model mismatches: list[dict]→list[str], dict[str,dict]→dict[str,str], etc."""
        if not isinstance(data, dict):
            return data

        import typing

        result = dict(data)
        try:
            hints = typing.get_type_hints(schema)
        except Exception:
            return result

        for field_name, field_type in hints.items():
            if field_name not in result:
                continue
            value = result[field_name]
            origin = typing.get_origin(field_type)
            args = typing.get_args(field_type)

            # list[str] that came as list[dict] → take .text / .name / str()
            if origin is list and args and args[0] is str:
                if isinstance(value, list):
                    coerced: list[str] = []
                    for item in value:
                        if isinstance(item, str):
                            coerced.append(item)
                        elif isinstance(item, dict):
                            coerced.append(
                                item.get("text")
                                or item.get("name")
                                or item.get("description")
                                or str(item)
                            )
                        else:
                            coerced.append(str(item))
                    result[field_name] = coerced

            # dict[str, str] that came as dict[str, dict] → take .name / str()
            elif origin is dict and len(args) >= 2 and args[0] is str and args[1] is str:
                if isinstance(value, dict):
                    coerced_dict: dict[str, str] = {}
                    for k, v in value.items():
                        if isinstance(v, str):
                            coerced_dict[k] = v
                        elif isinstance(v, dict):
                            coerced_dict[k] = (
                                v.get("name")
                                or v.get("description")
                                or v.get("text")
                                or str(v)
                            )
                        else:
                            coerced_dict[k] = str(v)
                    result[field_name] = coerced_dict
                elif isinstance(value, list):
                    # list[dict] → dict[str, str]
                    coerced_dict = {}
                    for item in value:
                        if isinstance(item, dict):
                            key = item.get("id") or item.get("name") or str(len(coerced_dict))
                            val = (
                                item.get("name")
                                or item.get("description")
                                or item.get("text")
                                or str(item)
                            )
                            coerced_dict[str(key)] = str(val)
                    result[field_name] = coerced_dict

        return result

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

    @staticmethod
    def _compile_role_prompt(role_config: Dict[str, Any], role_override: Optional[Dict[str, Any]]) -> str:
        """Recompile system prompt from role_config parts + optional sandbox overrides.

        Mirrors SystemLLMRole.compiled_prompt logic so overrides to identity/mission/etc.
        are reflected in the final prompt sent to the LLM.
        """
        parts: list[str] = []
        for field, heading in _ROLE_PROMPT_SECTIONS:
            base = role_config.get(field)
            override_val = role_override.get(field) if isinstance(role_override, dict) else None
            val = override_val if override_val is not None else base
            if val:
                parts.append(f"# {heading}\n{val}")

        examples = role_config.get("examples")
        override_examples = role_override.get("examples") if isinstance(role_override, dict) else None
        effective_examples = override_examples if override_examples is not None else examples
        if effective_examples:
            parts.append("# EXAMPLES")
            for i, example in enumerate(effective_examples, 1):
                parts.append(f"## Example {i}")
                if isinstance(example, dict):
                    if example.get("description"):
                        parts.append(f"Description: {example['description']}")
                    if example.get("input"):
                        parts.append(f"Input: {example['input']}")
                    if example.get("output"):
                        parts.append(f"Output: {example['output']}")
                parts.append("")

        return "\n\n".join(parts) if parts else (role_config.get("prompt") or "You are a helpful assistant.")
