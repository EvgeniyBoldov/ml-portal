"""Lifecycle facade over the canonical runtime event journal."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.services.runtime_event_logger import (
    RuntimeEventJournalFactory,
    RuntimeEventLogger,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType


class RunSession:
    """Logs one standalone agent journal using canonical runtime events."""

    def __init__(
        self, *, ctx: Any, agent_slug: str, logging_level: str, mode: str,
        context_snapshot: Optional[Dict[str, Any]] = None, enable_logging: bool = True,
        run_id_override: Optional[UUID] = None,
    ) -> None:
        self.ctx, self.agent_slug, self.mode = ctx, agent_slug, mode
        self.level = RuntimeLoggingLevel.parse(logging_level)
        self.context_snapshot = context_snapshot or {}
        self.enable_logging = enable_logging
        self.run_id_override = run_id_override
        self.run_id: Optional[UUID] = None
        self.logger: RuntimeEventLogger | Any | None = None
        self._owns_root_journal = False
        self._inherited_logger: RuntimeEventLogger | Any | None = None

    async def start(self) -> Optional[UUID]:
        if not self.enable_logging:
            return None
        self.run_id = self.run_id_override or uuid4()
        inherited = self.ctx.extra.get("runtime_event_logger") if isinstance(self.ctx.extra, dict) else None
        if inherited is not None and getattr(inherited, "context", None) is not None:
            self._inherited_logger = inherited
            parent = self.ctx.extra.get("runtime_log_parent") or {}
            self.logger = inherited.for_entity(
                entity_type="agent_execution",
                entity_id=str(self.run_id),
                parent_entity_type=parent.get("entity_type") or "run",
                parent_entity_id=parent.get("entity_id") or str(inherited.context.run_id),
                level=self.level,
            )
            self.ctx.extra["runtime_event_logger"] = self.logger
            self.ctx.extra["runtime_log_context"] = self.logger.worker_payload()
            return self.run_id
        deps = self.ctx.get_runtime_deps()
        overrides = getattr(deps, "sandbox_overrides", {}) or {}
        sandbox = bool(overrides.get("sandbox_run_id"))
        root_id = self.run_id
        raw_root_id = self.ctx.extra.get("runtime_root_run_id")
        if sandbox and raw_root_id:
            root_id = UUID(str(raw_root_id))
        parent = self.ctx.extra.get("runtime_log_parent") or {}
        context = RuntimeLogContext(
            run_id=root_id, level=RuntimeLoggingLevel.FULL if sandbox else self.level,
            origin="sandbox" if sandbox else "chat",
            tenant_id=self._uuid(getattr(self.ctx, "tenant_id", None)),
            user_id=self._uuid(getattr(self.ctx, "user_id", None)),
            chat_id=self._uuid(getattr(self.ctx, "chat_id", None)),
            entity_type="agent_execution", entity_id=str(self.run_id),
            parent_entity_type="run", parent_entity_id=str(root_id),
            stream_logs=sandbox,
            stream_progress=True,
            correlation_id=str(getattr(self.ctx, "request_id", "") or "") or None,
        )
        self.logger = RuntimeEventJournalFactory.create(
            context=context, session_factory=getattr(deps, "session_factory", None),
        )
        self._owns_root_journal = True
        self.ctx.extra["runtime_event_logger"] = self.logger
        self.ctx.extra["runtime_log_context"] = context.model_dump()
        await self._emit(RuntimeEvent.run_start(run_id=str(root_id)))
        await self._emit(RuntimeEvent.agent_start(
                agent_execution_id=str(self.run_id), parent_entity_id=str(root_id), parent_entity_type="run",
            agent_slug=self.agent_slug, executor_type="agent", task_title=self.context_snapshot.get("task_title"),
            context_snapshot=self.context_snapshot, mode=self.mode,
        ))
        return self.run_id

    async def record_event(
        self, step_type: str, data: Dict[str, Any], tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None, duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        if self.run_id is None:
            return
        payload = dict(data)
        if tokens_in is not None: payload["tokens_in"] = tokens_in
        if tokens_out is not None: payload["tokens_out"] = tokens_out
        if error: payload["error"] = error
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if step_type == "llm_turn":
            call_id = str(payload.get("llm_call_id") or uuid4())
            request_payload = dict(payload)
            response_payload = dict(payload)
            request_payload.pop("llm_call_id", None)
            response_payload.pop("llm_call_id", None)
            response_payload.pop("messages", None)
            request_payload.setdefault("parent_entity_type", "agent_execution")
            request_payload.setdefault("parent_entity_id", str(self.run_id))
            response_payload.setdefault("parent_entity_type", "agent_execution")
            response_payload.setdefault("parent_entity_id", str(self.run_id))
            await self._emit(RuntimeEvent.llm_request(
                **request_payload, llm_call_id=call_id,
            ))
            await self._emit(RuntimeEvent.llm_response(
                **response_payload, llm_call_id=call_id,
            ))
            return
        if step_type == "tool_call":
            await self._emit(RuntimeEvent.tool_call(
                tool=str(payload.get("tool") or "operation"),
                call_id=str(payload.get("call_id") or uuid4()),
                arguments=dict(payload.get("arguments") or payload.get("input") or {}),
                parent_entity_type="agent_execution", parent_entity_id=str(self.run_id),
                agent_slug=self.agent_slug, agent_execution_id=str(self.run_id),
            ))
            return
        if step_type == "tool_result":
            await self._emit(RuntimeEvent.tool_result(
                tool=str(payload.get("tool") or "operation"),
                call_id=str(payload.get("call_id") or uuid4()),
                success=bool(payload.get("success")), data=payload.get("data"),
                parent_entity_type="agent_execution", parent_entity_id=str(self.run_id),
                agent_slug=self.agent_slug, agent_execution_id=str(self.run_id),
                safe_message=payload.get("safe_message"), error_code=payload.get("error_code"),
                retryable=payload.get("retryable"),
            ))
            return
        event_type = {
            "budget_snapshot": RuntimeEventType.BUDGET_SNAPSHOT,
            "final_response": RuntimeEventType.FINAL,
            "direct_response": RuntimeEventType.FINAL,
            "protocol_retry": RuntimeEventType.PROTOCOL_RETRY,
            "intent": RuntimeEventType.INTENT,
            "user_request": RuntimeEventType.INTENT,
        }.get(step_type, RuntimeEventType.STATUS)
        if event_type is RuntimeEventType.FINAL:
            final_payload = dict(payload)
            content = str(final_payload.pop("content", "") or "")
            final_payload.pop("run_id", None)
            event = RuntimeEvent.final(content, run_id=str(self.run_id), **final_payload)
        elif event_type is RuntimeEventType.STATUS:
            event = RuntimeEvent.status(step_type, **payload)
        else:
            event = RuntimeEvent(event_type, payload)
        await self._emit(event)

    async def finish(self, status: str, error: Optional[str] = None) -> None:
        if self.run_id is None or getattr(self.logger, "context", None) is None:
            return
        outcome = "success" if status == "completed" else status
        if self._owns_root_journal:
            await self._emit(RuntimeEvent.agent_end(
                agent_execution_id=str(self.run_id), parent_entity_id=str(self.logger.context.run_id),
                parent_entity_type="run", agent_slug=self.agent_slug, status=status,
                outcome=outcome, summary=error,
            ))
            await self._emit(RuntimeEvent.run_end(
                run_id=str(self.logger.context.run_id), status=status,
            ))
        if error:
            await self._emit(RuntimeEvent.error(
                error, parent_entity_type="agent_execution", parent_entity_id=str(self.run_id),
                source="runtime", stage="agent_run_end",
            ))
        if self._inherited_logger is not None:
            self.ctx.extra["runtime_event_logger"] = self._inherited_logger

    async def _emit(self, event: RuntimeEvent) -> None:
        # Pipeline consumes the agent stream and is the sole semantic emitter.
        # Writing here as well would create a second copy of every LLM/tool event.
        if self._inherited_logger is not None:
            return
        if self.logger is not None:
            await self.logger.emit(event, phase=OrchestrationPhase.AGENT)

    @staticmethod
    def _uuid(value: Any) -> Optional[UUID]:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
