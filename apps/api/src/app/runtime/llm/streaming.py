from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.execution_limit import ExecutionLimitScope
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.budgets import BudgetRegistry
from app.runtime.llm.limits import LLMLimitExceededError, apply_llm_limits, estimate_tokens
from app.services.execution_limits_service import ExecutionLimitsPayload, ExecutionLimitsService, apply_limits_override
from app.services.system_llm_role_service import SystemLLMRoleService


@dataclass(frozen=True)
class StreamDelta:
    kind: Literal["delta"] = "delta"
    chunk: str = ""


@dataclass(frozen=True)
class StreamTurn:
    kind: Literal["turn"] = "turn"
    llm_call_id: str = ""
    model: str = "unknown"
    messages: List[Dict[str, Any]] = None  # type: ignore[assignment]
    content: str = ""
    response_length: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_total: int = 0
    duration_ms: int = 0
    partial: bool = False
    error_message: Optional[str] = None


@dataclass(frozen=True)
class StreamError:
    kind: Literal["error"] = "error"
    code: str = ""
    message: str = ""
    recoverable: bool = True


StreamEvent = StreamDelta | StreamTurn | StreamError


class RoleStreamingCall:
    """Streaming counterpart of StructuredLLMCall for role-driven text output."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._llm_client = llm_client
        self._role_service = SystemLLMRoleService(session)
        self._limits_service = ExecutionLimitsService(session)

    async def invoke_stream(
        self,
        *,
        role: SystemLLMRoleType,
        messages: List[Dict[str, Any]],
        llm_call_id: str,
        role_config: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
        params_override: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_entity_id: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]:
        role_cfg = role_config or await self._role_service.get_role_config(role)
        model = model_override if model_override is not None else role_cfg.get("model")
        _timeout_s = int(role_cfg.get("timeout_s") or 30)
        params: Dict[str, Any] = {}
        if role_cfg.get("temperature") is not None:
            params["temperature"] = role_cfg["temperature"]
        if role_cfg.get("max_tokens") is not None:
            params["max_tokens"] = role_cfg["max_tokens"]
        if isinstance(params_override, dict):
            params.update(params_override)

        try:
            limits = await self._limits_service.get_effective(
                scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
                scope_ref=str(role.value).strip().lower(),
            )
        except Exception:
            limits = ExecutionLimitsPayload()
        role_key = str(role.value).strip().lower()
        role_override = ((sandbox_overrides or {}).get("orchestrator_limits") or {}).get(role_key)
        limits = apply_limits_override(limits, role_override if isinstance(role_override, dict) else None)

        input_tokens = estimate_tokens(str(messages))
        requested_output_tokens = int(params["max_tokens"]) if params.get("max_tokens") is not None else None
        try:
            boundary = apply_llm_limits(
                limits=limits,
                input_tokens=input_tokens,
                requested_output_tokens=requested_output_tokens,
            )
        except LLMLimitExceededError as exc:
            yield StreamError(code=exc.code, message=str(exc), recoverable=False)
            return
        if boundary.output_tokens is not None:
            params["max_tokens"] = int(boundary.output_tokens)

        if budget_registry is not None and budget_entity_id:
            budget_registry.consume(budget_entity_id, "tokens_in", input_tokens, reason="llm_input")

        buffer: List[str] = []
        started_at = time.monotonic()
        stream_error: Optional[Exception] = None
        try:
            stream_iter = self._llm_client.chat_stream(messages, model=model, params=params or None)
            async for chunk in _collect_stream(stream_iter):
                if not chunk:
                    continue
                buffer.append(chunk)
                yield StreamDelta(chunk=chunk)
        except LLMLimitExceededError as exc:
            stream_error = exc
        except Exception as exc:  # noqa: BLE001
            stream_error = exc

        content = "".join(buffer).strip()
        tokens_out = estimate_tokens(content)
        tokens_total = input_tokens + tokens_out
        duration_ms = int((time.monotonic() - started_at) * 1000)

        if budget_registry is not None and budget_entity_id:
            if tokens_out > 0:
                budget_registry.consume(budget_entity_id, "tokens_out", tokens_out, reason="llm_output")
            if tokens_total > 0:
                budget_registry.consume(budget_entity_id, "tokens_total", tokens_total, reason="llm_total")
            if duration_ms > 0:
                budget_registry.consume(budget_entity_id, "wall_time_ms", duration_ms, reason="llm_time")

        if stream_error is not None and not content:
            if isinstance(stream_error, LLMLimitExceededError):
                yield StreamError(code=stream_error.code, message=str(stream_error), recoverable=False)
            else:
                yield StreamError(code="llm_stream_error", message=str(stream_error), recoverable=True)
            return

        yield StreamTurn(
            llm_call_id=llm_call_id,
            model=str(model or "unknown"),
            messages=messages,
            content=content,
            response_length=len(content),
            tokens_in=input_tokens,
            tokens_out=tokens_out,
            tokens_total=tokens_total,
            duration_ms=duration_ms,
            partial=stream_error is not None,
            error_message=str(stream_error) if stream_error is not None else None,
        )


async def _collect_stream(stream_iter: AsyncIterator[str]) -> AsyncIterator[str]:
    async for item in stream_iter:
        yield item
