"""
ExecutionTraceLogger — unified observability facade for runtime execution.

This service does not replace existing persistence models. Instead, it
centralizes writing of:
- agent run envelopes and generic step logs
- routing decisions
- system LLM traces

The goal is to keep runtime/business logic unchanged while giving every
runtime component a single logging contract.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.core.logging import get_logger
from app.core.observability import span_id_var, tenant_id_var, trace_id_var, user_id_var
from app.models.routing_log import RoutingLog
from app.models.system_llm_trace import SystemLLMTrace
from app.repositories.routing_log_repository import RoutingLogRepository
from app.runtime.redactor import RuntimeRedactor
from app.services.run_store import RunStore
from app.services.system_llm_trace_service import SystemLLMTraceService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.agents.contracts import MissingRequirements, ProviderExecutionTarget, ResolvedOperation

logger = get_logger(__name__)


class TraceLevel(str, Enum):
    """Normalized trace verbosity used by runtime and sandbox."""

    NONE = "none"
    BRIEF = "brief"
    FULL = "full"

    @classmethod
    def normalize(cls, value: Optional[str]) -> "TraceLevel":
        if value is None:
            return cls.BRIEF
        normalized = str(value).strip().lower()
        if normalized == "short":
            normalized = "brief"
        try:
            return cls(normalized)
        except ValueError:
            return cls.BRIEF


class ExecutionTraceLogger:
    """Facade that records runtime traces across existing persistence layers."""

    def __init__(
        self,
        session: Optional["AsyncSession"] = None,
        run_store: Optional[RunStore] = None,
        routing_log_repo: Optional[RoutingLogRepository] = None,
        system_trace_service: Optional[SystemLLMTraceService] = None,
    ) -> None:
        self.session = session
        self.run_store = run_store or RunStore(session=session)
        self.routing_log_repo = routing_log_repo or (RoutingLogRepository(session) if session else None)
        self.system_trace_service = system_trace_service or (SystemLLMTraceService(session) if session else None)

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_level(value: Optional[str]) -> str:
        return TraceLevel.normalize(value).value

    @staticmethod
    def _trace_context() -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        trace_id = trace_id_var.get()
        if trace_id:
            context["trace_id"] = trace_id
        span_id = span_id_var.get()
        if span_id:
            context["span_id"] = span_id
        user_id = user_id_var.get()
        if user_id:
            context["user_id"] = user_id
        tenant_id = tenant_id_var.get()
        if tenant_id:
            context["tenant_id"] = tenant_id
        return context

    @classmethod
    def _merge_context_snapshot(cls, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(snapshot or {})
        trace_context = cls._trace_context()
        if trace_context:
            merged.setdefault("trace_context", {}).update(trace_context)
        return RuntimeRedactor().redact(merged)

    @staticmethod
    def _step_type(component: Optional[str], event: Optional[str], fallback: Optional[str] = None) -> str:
        if fallback:
            return fallback
        parts = [part for part in (component, event) if part]
        return "_".join(parts) if parts else "event"

    # ------------------------------------------------------------------
    # run envelope / generic steps
    # ------------------------------------------------------------------

    async def start_run(
        self,
        tenant_id: str,
        agent_slug: str,
        logging_level: str = "brief",
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        message_id: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> uuid.UUID:
        """Start a run using the existing RunStore."""
        snapshot = self._merge_context_snapshot(context_snapshot)
        return await self.run_store.start_run(
            tenant_id=tenant_id,
            agent_slug=agent_slug,
            logging_level=self.normalize_level(logging_level),
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            context_snapshot=snapshot,
        )

    async def log_step(
        self,
        run_id: Optional[uuid.UUID],
        step_type: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        *,
        component: Optional[str] = None,
        event: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Optional[uuid.UUID]:
        """Record a generic runtime step."""
        if run_id is None:
            return None
        resolved_step_type = self._step_type(component, event, step_type)
        return await self.run_store.add_step(
            run_id,
            resolved_step_type,
            data or {},
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            error=error,
        )

    async def finish_run(
        self,
        run_id: Optional[uuid.UUID],
        status: str,
        error: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
    ) -> None:
        """Finish a run using the existing RunStore."""
        if run_id is None:
            return
        await self.run_store.finish_run(
            run_id,
            status=status,
            error=error,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    # ------------------------------------------------------------------
    # routing / preflight
    # ------------------------------------------------------------------

    async def log_routing_decision(
        self,
        *,
        run_id: Optional[uuid.UUID],
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request_text: Optional[str],
        agent_slug: str,
        mode: Any,
        missing: "MissingRequirements",
        available_operations: List["ResolvedOperation"],
        available_collections: List[str],
        execution_targets: Dict[str, "ProviderExecutionTarget"],
        routing_reasons: List[str],
        status: Any,
        duration_ms: int,
        error_message: Optional[str] = None,
        intent: Optional[str] = None,
        intent_confidence: Optional[float] = None,
        agent_confidence: Optional[float] = None,
    ) -> Optional[RoutingLog]:
        """Persist a routing decision and mirror it into the generic run log."""
        if run_id is not None:
            await self.log_step(
                run_id,
                step_type="routing_decision",
                data={
                    "agent_slug": agent_slug,
                    "execution_mode": getattr(mode, "value", str(mode)),
                    "status": getattr(status, "value", str(status)),
                    "routing_reasons": routing_reasons,
                    "missing_tools": list(getattr(missing, "tools", []) or []),
                    "missing_collections": list(getattr(missing, "collections", []) or []),
                    "missing_credentials": list(getattr(missing, "credentials", []) or []),
                    "effective_operations": [operation.operation_slug for operation in available_operations],
                    "effective_data_instances": list(available_collections),
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                },
            )

        if run_id is None:
            return None

        if self.routing_log_repo is None:
            logger.debug("Routing log repository is unavailable; skipping routing log persistence")
            return None

        log = RoutingLog(
            run_id=run_id,
            user_id=user_id,
            tenant_id=tenant_id,
            request_text=request_text[:1000] if request_text else None,
            intent=intent,
            intent_confidence=intent_confidence,
            selected_agent_slug=agent_slug,
            agent_confidence=agent_confidence,
            routing_reasons=routing_reasons,
            missing_tools=list(getattr(missing, "tools", []) or []),
            missing_collections=list(getattr(missing, "collections", []) or []),
            missing_credentials=list(getattr(missing, "credentials", []) or []),
            execution_mode=getattr(mode, "value", str(mode)),
            effective_operations=[operation.operation_slug for operation in available_operations],
            effective_data_instances=list(available_collections),
            operation_targets={
                slug: target.model_dump(mode="json")
                for slug, target in execution_targets.items()
            },
            routing_duration_ms=duration_ms,
            status=getattr(status, "value", str(status)),
            error_message=error_message,
        )
        return await self.routing_log_repo.create(log)

    # ------------------------------------------------------------------
    # system LLM traces
    # ------------------------------------------------------------------

    async def log_system_llm_trace(
        self,
        *,
        trace_type: str,
        role_config: Dict[str, Any],
        structured_input: Dict[str, Any],
        messages: List[Dict[str, str]],
        llm_response: str,
        parsed_response: Optional[Dict[str, Any]],
        validation_status: str,
        start_time: float,
        model: str,
        temperature: float,
        max_tokens: int,
        run_id: Optional[uuid.UUID] = None,
        trace_summary: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> SystemLLMTrace:
        """Persist a system LLM trace and mirror a compact summary into run logs."""
        if self.system_trace_service is None:
            raise RuntimeError("ExecutionTraceLogger: no session for system trace logging")

        trace = await self.system_trace_service.create_trace_from_execution(
            trace_type=trace_type,
            role_config=role_config,
            structured_input=structured_input,
            messages=messages,
            llm_response=llm_response,
            parsed_response=parsed_response,
            validation_status=validation_status,
            start_time=start_time,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        if run_id is not None:
            summary = trace_summary or {}
            summary.update(
                {
                    "trace_id": str(trace.id),
                    "trace_type": trace_type,
                    "validation_status": validation_status,
                    "model": model,
                    "duration_ms": trace.duration_ms,
                }
            )
            await self.log_step(
                run_id,
                step_type="system_llm_trace",
                data=summary,
            )

        return trace
