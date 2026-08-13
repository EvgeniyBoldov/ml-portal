"""
StructuredLLMCall — shared helper used by Triage, Planner and Synthesizer.

Responsibilities:
    * Render role system prompt + structured JSON user payload
    * Call LLM with timeout + retries
    * Extract JSON (handles ```json fences and prose wrappers)
    * Validate against Pydantic schema; fall back or raise
    * Emit canonical runtime events through the caller's logger

Callers get a typed `StructuredCallResult` with the parsed model instance and
the trace_id they can attach to downstream events.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, Optional, Type, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.adapters.interfaces.llm import LLMCallOptions, LLMProviderError
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.limits import estimate_tokens
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.services.model_call_config_service import ModelCallConfigService
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredCallError(RuntimeError):
    """Raised when LLM output cannot be coerced into the requested schema."""

    def __init__(
        self,
        message: str,
        *,
        original_exception: Optional[BaseException] = None,
        traceback_text: Optional[str] = None,
        llm_call_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.original_exception = original_exception
        self.traceback_text = traceback_text
        self.llm_call_id = llm_call_id

    @property
    def error_type(self) -> Optional[str]:
        return type(self.original_exception).__name__ if self.original_exception is not None else None

    def debug_payload(self) -> Optional[Dict[str, Any]]:
        if self.original_exception is None and not self.traceback_text:
            return None
        payload: Dict[str, Any] = {}
        if self.original_exception is not None:
            payload["exception_type"] = type(self.original_exception).__name__
            payload["exception_message"] = str(self.original_exception)
        if self.traceback_text:
            payload["traceback"] = self.traceback_text
        return payload or None


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
        self.model_call_config_service = ModelCallConfigService(session)
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
        agent_execution_id: Optional[UUID] = None,
        event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
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
        system_prompt = system_prompt or self._compile_role_prompt(
            role_config,
            role_override,
            schema=schema,
        )
        user_message = json.dumps(payload, ensure_ascii=False, default=str)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        model_call_config = await self.model_call_config_service.resolve(model)
        configured_timeout_s = model_call_config.request_timeout_s
        timeout_s = int(role_config.get("timeout_s") or configured_timeout_s)
        max_retries = int(role_config.get("max_retries") if role_config.get("max_retries") is not None else model_call_config.max_retries)
        retry_backoff = str(role_config.get("retry_backoff") or "exp")
        max_tokens = role_config.get("max_tokens")
        if max_tokens is None:
            max_tokens = model_call_config.max_output_tokens
        params: Dict[str, Any] = {}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        role_key = str(role.value).strip().lower()
        input_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_message)
        # The adapter owns the actual SDK request timeout. Keeping the limit
        # here as well bounds callers that use a test/different implementation.

        # JSON schema enforcement: constrain LLM output to the Pydantic schema.
        # Works with OpenAI, Groq, and other providers supporting response_format.
        if schema is not None:
            try:
                json_schema = self._compact_response_schema(schema.model_json_schema())
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

        request_bytes = len(json.dumps(
            {"messages": messages, "params": params},
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8"))
        response_schema_bytes = len(json.dumps(
            params.get("response_format") or {},
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8"))
        logger.info(
            "Structured LLM effective limits role=%s model=%s configured_timeout_s=%s "
            "effective_timeout_s=%s max_retries=%s max_tokens=%s input_tokens_estimate=%s "
            "request_bytes=%s response_schema_bytes=%s",
            role_key,
            model,
            configured_timeout_s,
            timeout_s,
            max_retries,
            params.get("max_tokens"),
            input_tokens,
            request_bytes,
            response_schema_bytes,
        )

        last_error: Optional[str] = None
        last_exception: Optional[BaseException] = None
        last_traceback: Optional[str] = None
        raw_response = ""
        start = time.monotonic()
        # A structured invocation may retry at the provider, but it remains
        # one user-visible request.  Reuse one call id for every request and
        # response in that retry chain; the logical id remains available for
        # compatibility with consumers that group historical traces.
        logical_llm_call_id = str(uuid4())
        llm_call_id = str(uuid4())

        for attempt in range(max_retries + 1):
            attempt_started = time.monotonic()
            attempt_request_bytes = len(json.dumps(
                {"messages": messages, "params": params},
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8"))
            attempt_response_schema_bytes = len(json.dumps(
                params.get("response_format") or {},
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8"))

            logger.info(
                "Structured LLM attempt started role=%s model=%s attempt=%s/%s "
                "timeout_s=%s max_tokens=%s llm_call_id=%s",
                role_key,
                model,
                attempt + 1,
                max_retries + 1,
                timeout_s,
                params.get("max_tokens"),
                llm_call_id,
            )

            async def emit_protocol_retry(
                *, reason: str, retry_after_ms: Optional[int] = None
            ) -> None:
                if event_sink is None or agent_execution_id is None or attempt >= max_retries:
                    return
                await event_sink(RuntimeEvent(
                    RuntimeEventType.PROTOCOL_RETRY,
                    {
                        "entity_type": "llm_call",
                        "entity_id": llm_call_id,
                        "logical_llm_call_id": logical_llm_call_id,
                        "parent_entity_type": "agent_execution",
                        "parent_entity_id": str(agent_execution_id),
                        "agent_execution_id": str(agent_execution_id),
                        "agent_slug": role_key,
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1,
                        "reason": reason,
                        "retry_delay_ms": self._retry_delay_ms(
                            attempt=attempt,
                            retry_after_ms=retry_after_ms,
                            strategy=retry_backoff,
                        ),
                    },
                ))

            async def wait_before_retry(*, retry_after_ms: Optional[int] = None) -> None:
                if attempt >= max_retries:
                    return
                retry_delay_ms = self._retry_delay_ms(
                    attempt=attempt,
                    retry_after_ms=retry_after_ms,
                    strategy=retry_backoff,
                )
                logger.info(
                    "Structured LLM retry scheduled role=%s attempt=%s/%s delay_ms=%s retry_after_ms=%s",
                    role_key, attempt + 1, max_retries + 1, retry_delay_ms, retry_after_ms,
                )
                await asyncio.sleep(retry_delay_ms / 1000)

            if event_sink is not None and agent_execution_id is not None:
                await event_sink(RuntimeEvent.llm_request(
                    llm_call_id=llm_call_id,
                    logical_llm_call_id=logical_llm_call_id,
                    parent_entity_type="agent_execution",
                    parent_entity_id=str(agent_execution_id),
                    agent_execution_id=str(agent_execution_id),
                    agent_slug=role_key,
                    purpose="planning_decision" if role_key == "planner" else role_key,
                    model=model,
                    temperature=temperature,
                    max_tokens=params.get("max_tokens"),
                    input_tokens_estimate=input_tokens,
                    request_bytes=attempt_request_bytes,
                    response_schema_bytes=attempt_response_schema_bytes,
                    messages=messages,
                ))
            try:
                response = await asyncio.wait_for(
                    self.llm_client.chat(messages, model=model, params=params or None,
                                         options=LLMCallOptions(timeout_s=timeout_s)),
                    timeout=timeout_s,
                )
            except asyncio.CancelledError:
                logger.warning(
                    "Structured LLM attempt cancelled role=%s model=%s attempt=%s/%s "
                    "timeout_s=%s attempt_elapsed_ms=%s total_elapsed_ms=%s task_cancelling=%s "
                    "llm_call_id=%s",
                    role_key,
                    model,
                    attempt + 1,
                    max_retries + 1,
                    timeout_s,
                    int((time.monotonic() - attempt_started) * 1000),
                    int((time.monotonic() - start) * 1000),
                    asyncio.current_task().cancelling() if asyncio.current_task() else None,
                    llm_call_id,
                )
                raise
            except asyncio.TimeoutError:
                timeout_exc = asyncio.TimeoutError(f"llm_timeout after {timeout_s}s")
                last_exception = timeout_exc
                last_traceback = traceback.format_exc()
                last_error = f"{type(timeout_exc).__name__}: {timeout_exc} (attempt {attempt + 1})"
                logger.warning(
                    "Structured LLM attempt timeout role=%s model=%s attempt=%s/%s "
                    "timeout_s=%s attempt_elapsed_ms=%s total_elapsed_ms=%s llm_call_id=%s",
                    role_key,
                    model,
                    attempt + 1,
                    max_retries + 1,
                    timeout_s,
                    int((time.monotonic() - attempt_started) * 1000),
                    int((time.monotonic() - start) * 1000),
                    llm_call_id,
                )
                if event_sink is not None and agent_execution_id is not None:
                    await event_sink(RuntimeEvent.llm_response(
                        llm_call_id=llm_call_id,
                        logical_llm_call_id=logical_llm_call_id,
                        parent_entity_type="agent_execution",
                        parent_entity_id=str(agent_execution_id),
                        agent_execution_id=str(agent_execution_id),
                        agent_slug=role_key,
                        purpose="planning_decision" if role_key == "planner" else role_key,
                        model=model,
                        error_type="TimeoutError",
                        error_code="llm_timeout",
                        retryable=True,
                        status="waiting_retry" if attempt < max_retries else "failed",
                        terminal=attempt >= max_retries,
                        attempt=attempt + 1,
                        max_attempts=max_retries + 1,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    ))
                await emit_protocol_retry(reason="timeout")
                await wait_before_retry()
                continue
            except Exception as exc:  # network / upstream failure
                last_exception = exc
                last_traceback = traceback.format_exc()
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("StructuredLLMCall error role=%s attempt=%s: %s", role, attempt + 1, exc)
                provider_retryable = exc.retryable if isinstance(exc, LLMProviderError) else True
                adaptive_retry = (
                    isinstance(exc, LLMProviderError)
                    and exc.code.value == "llm_request_too_large"
                    and attempt < max_retries
                    and self._shrink_request_for_provider_limit(params)
                )
                fail_fast = (
                    (isinstance(exc, LLMProviderError) and not exc.retryable)
                    or self._is_non_retryable_llm_error(exc)
                )
                will_retry = adaptive_retry or (provider_retryable and not fail_fast and attempt < max_retries)
                if event_sink is not None and agent_execution_id is not None:
                    await event_sink(RuntimeEvent.llm_response(
                        llm_call_id=llm_call_id,
                        logical_llm_call_id=logical_llm_call_id,
                        parent_entity_type="agent_execution",
                        parent_entity_id=str(agent_execution_id),
                        agent_execution_id=str(agent_execution_id),
                        agent_slug=role_key,
                        purpose="planning_decision" if role_key == "planner" else role_key,
                        model=model,
                        error_type=type(exc).__name__,
                        error_code=(exc.code.value if isinstance(exc, LLMProviderError) else "llm_unknown_error"),
                        safe_message=(exc.safe_message if isinstance(exc, LLMProviderError) else "LLM request failed"),
                        retryable=will_retry,
                        status_code=(exc.status_code if isinstance(exc, LLMProviderError) else None),
                        provider_code=(exc.provider_code if isinstance(exc, LLMProviderError) else None),
                        retry_after_ms=(exc.retry_after_ms if isinstance(exc, LLMProviderError) else None),
                        status="waiting_retry" if will_retry else "failed",
                        terminal=not will_retry,
                        attempt=attempt + 1,
                        max_attempts=max_retries + 1,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    ))
                if fail_fast and not adaptive_retry:
                    logger.warning(
                        "StructuredLLMCall fail-fast role=%s attempt=%s due to non-retryable upstream error",
                        role,
                        attempt + 1,
                    )
                    break
                retry_after_ms = exc.retry_after_ms if isinstance(exc, LLMProviderError) else None
                await emit_protocol_retry(
                    reason="reduce_request_size" if adaptive_retry else "transport_error",
                    retry_after_ms=retry_after_ms,
                )
                await wait_before_retry(retry_after_ms=retry_after_ms)
                continue

            # A response starts a new failure mode; do not report a stale
            # transport exception if the final attempts fail validation.
            last_exception = None
            last_traceback = None
            raw_response = self._extract_text(response)
            if event_sink is not None and agent_execution_id is not None:
                await event_sink(RuntimeEvent.llm_response(
                    llm_call_id=llm_call_id,
                    logical_llm_call_id=logical_llm_call_id,
                    parent_entity_type="agent_execution",
                    parent_entity_id=str(agent_execution_id),
                    agent_execution_id=str(agent_execution_id),
                    agent_slug=role_key,
                    purpose="planning_decision" if role_key == "planner" else role_key,
                    model=model,
                    response=raw_response,
                    content=raw_response,
                    status="running",
                    terminal=False,
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                    duration_ms=int((time.monotonic() - start) * 1000),
                ))
            if not raw_response:
                last_error = "empty_response"
                await emit_protocol_retry(reason="empty_response")
                await wait_before_retry()
                continue

            try:
                parsed = self._parse_and_validate(raw_response, schema)
            except StructuredCallError as exc:
                last_error = str(exc)
                logger.info(
                    "StructuredLLMCall schema mismatch role=%s attempt=%s: %s",
                    role, attempt + 1, exc,
                )
                await emit_protocol_retry(reason="schema_validation")
                await wait_before_retry()
                continue

            duration_ms = int((time.monotonic() - start) * 1000)
            if event_sink is not None and agent_execution_id is not None:
                await event_sink(RuntimeEvent.llm_response(
                    llm_call_id=llm_call_id,
                    logical_llm_call_id=logical_llm_call_id,
                    parent_entity_type="agent_execution",
                    parent_entity_id=str(agent_execution_id),
                    agent_execution_id=str(agent_execution_id),
                    agent_slug=role_key,
                    purpose="planning_decision" if role_key == "planner" else role_key,
                    model=model,
                    response=raw_response,
                    content=raw_response,
                    result_kind="plan" if role_key == "planner" else "answer",
                    status="completed",
                    terminal=True,
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                    duration_ms=duration_ms,
                ))
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
        duration_ms = int((time.monotonic() - start) * 1000)
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
            f"{max_retries + 1} attempts: {last_error}",
            original_exception=last_exception,
            traceback_text=last_traceback,
            llm_call_id=llm_call_id,
        )

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _compact_response_schema(value: Any) -> Any:
        """Project a JSON Schema to the validation keywords needed by an LLM.

        Local Pydantic validation remains authoritative.  Titles, defaults
        and descriptions are useful to humans, but duplicate the prompt and
        can make an otherwise valid provider request exceed its body limit.
        """
        if isinstance(value, list):
            return [StructuredLLMCall._compact_response_schema(item) for item in value]
        if not isinstance(value, dict):
            return value
        # These are maps whose keys are user-defined schema names, not JSON
        # Schema keywords. Preserve each name and compact only its value.
        if set(value).isdisjoint({"type", "properties", "items", "$ref", "anyOf", "oneOf", "allOf", "enum", "required"}):
            return {
                key: StructuredLLMCall._compact_response_schema(item)
                for key, item in value.items()
            }
        allowed = {
            "$defs", "$ref", "type", "properties", "required", "items",
            "additionalProperties", "enum", "const", "anyOf", "oneOf", "allOf",
            "format", "pattern", "minLength", "maxLength", "minimum", "maximum",
            "minItems", "maxItems", "minProperties", "maxProperties",
        }
        result: Dict[str, Any] = {}
        for key, item in value.items():
            if key not in allowed:
                continue
            if key in {"properties", "$defs"} and isinstance(item, dict):
                result[key] = {
                    name: StructuredLLMCall._compact_response_schema(child)
                    for name, child in item.items()
                }
            else:
                result[key] = StructuredLLMCall._compact_response_schema(item)
        return result

    @staticmethod
    def _shrink_request_for_provider_limit(params: Dict[str, Any]) -> bool:
        """Prepare one bounded adaptive retry after an HTTP 413.

        ``max_tokens`` is a ceiling, so lowering it after a provider rejects
        the whole request does not change the requested semantics.  The first
        retry also removes the optional JSON Schema transport envelope; the
        local Pydantic validator still enforces the same contract.
        """
        changed = False
        response_format = params.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            params["response_format"] = {"type": "json_object"}
            changed = True
        current = params.get("max_tokens")
        if isinstance(current, int) and current > 256:
            params["max_tokens"] = max(256, current // 2)
            changed = True
        return changed

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
    def _retry_delay_ms(
        *, attempt: int, retry_after_ms: Optional[int], strategy: str = "exp"
    ) -> int:
        """Bound retries and honour the provider's rate-limit hint when present."""
        if strategy == "none":
            base_ms = 0
        elif strategy == "linear":
            base_ms = min(10_000, 500 * (attempt + 1))
        else:
            base_ms = min(10_000, 500 * (2 ** max(0, attempt)))
        if retry_after_ms is None:
            return base_ms
        return min(30_000, max(base_ms, max(0, retry_after_ms)))

    @staticmethod
    def _compile_role_prompt(
        role_config: Dict[str, Any],
        role_override: Optional[Dict[str, Any]],
        *,
        schema: Optional[Type[BaseModel]] = None,
    ) -> str:
        """Recompile system prompt from role_config parts + optional sandbox overrides.

        Mirrors SystemLLMRole.compiled_prompt logic so overrides to identity/mission/etc.
        are reflected in the final prompt sent to the LLM. The database keeps the
        operator-authored output requirements; structured roles additionally receive
        the non-editable runtime schema that the parser enforces.
        """
        parts: list[str] = []
        role_type = str(role_config.get("role_type") or "").strip().lower()
        for field, heading in _ROLE_PROMPT_SECTIONS:
            base = role_config.get(field)
            override_val = role_override.get(field) if isinstance(role_override, dict) else None
            val = override_val if override_val is not None else base
            if val:
                parts.append(f"# {heading}\n{val}")

        if role_type != SystemLLMRoleType.SYNTHESIZER.value and schema is not None:
            generated_schema = StructuredLLMCall._compact_response_schema(schema.model_json_schema())
            if role_type == SystemLLMRoleType.PLANNER.value:
                parts.append(
                    "# PLANNER RUNTIME CONTRACT\n"
                    "Планер не формирует пользовательский ответ и не завершает план напрямую. "
                    "Для любого ответа, включая простой, добавь задачу с executor из available_agents; "
                    "завершённый граф передаётся synthesizer-у оркестратором.\n"
                    "Планер НИКОГДА не создаёт поле needs и не объявляет новые зависимости-данные. "
                    "needs создаёт только исполнитель задачи после фактической попытки работы. "
                    "Если во входе есть pending needs, разреши каждую из них только одним способом: "
                    "добавь задачу-производитель с expected_outputs, содержащим тот же key, и свяжи её "
                    "с ожидающей задачей через depends_on; либо верни ask_user с одним конкретным вопросом; "
                    "либо верни fail. Не повторяй неизменный граф при pending needs.\n"
                    "Для project knowledge используй только ключ проекта из memory_context.type=project. "
                    "Если проект для знания нужен, но ключ отсутствует или контекст неоднозначен, верни ask_user "
                    "с одним вопросом вместо догадки. Когда вызываешь executor=knowledge, передай точный project_key "
                    "в task.inputs."
                )
            parts.append(
                "# RUNTIME RESPONSE CONTRACT\n"
                "Верни строго валидный JSON по следующей схеме (без markdown и пояснений):\n"
                f"{json.dumps(generated_schema, ensure_ascii=False, indent=2)}"
            )

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
