"""Lifecycle facade over the canonical runtime event journal."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.services.runtime_event_logger import (
    RuntimeEventLogger,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)


_EVENT_NAMES = {
    "llm_turn": "llm_response", "llm_request": "llm_request", "tool_call": "tool_request",
    "tool_result": "tool_result", "budget_snapshot": "budget_snapshot",
    "final_response": "final", "direct_response": "final", "error": "error",
    "intent": "planner_decision", "user_request": "user_request",
}


class RunSession:
    """Logs one executor run; it does not create a legacy run envelope."""

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
        self.logger: RuntimeEventLogger | Any = RuntimeEventLogger.disabled()

    async def start(self) -> Optional[UUID]:
        if not self.enable_logging or self.level is RuntimeLoggingLevel.NONE:
            return None
        self.run_id = self.run_id_override or uuid4()
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
            entity_type="executor_run", entity_id=str(self.run_id),
            parent_entity_type=parent.get("entity_type"), parent_entity_id=parent.get("entity_id"),
            stream=sandbox, correlation_id=str(getattr(self.ctx, "request_id", "") or "") or None,
        )
        # Sandbox persists the canonical pipeline stream once.  Agent-local
        # calls still receive an executor id for correlation, but must not
        # write a duplicate copy of LLM/tool events.
        if sandbox:
            self.logger = RuntimeEventLogger.disabled()
            return self.run_id
        self.logger = RuntimeEventLogger(context=context, session_factory=getattr(deps, "session_factory", None))
        self.ctx.extra["runtime_event_logger"] = self.logger
        self.ctx.extra["runtime_log_context"] = context.model_dump()
        await self.logger.event("executor_started", payload={
            "agent_slug": self.agent_slug, "mode": self.mode, "context_snapshot": self.context_snapshot,
        })
        return self.run_id

    async def log_step(
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
        event_type = _EVENT_NAMES.get(step_type, step_type)
        await self.logger.event(event_type, payload=payload, duration_ms=duration_ms)

    async def finish(self, status: str, error: Optional[str] = None) -> None:
        if self.run_id is None:
            return
        payload = {"status": status, "agent_slug": self.agent_slug}
        if error: payload["error"] = error
        await self.logger.event("executor_finished", payload=payload)
        if error:
            await self.logger.error(error, payload={"stage": "executor_finished"})

    @staticmethod
    def _uuid(value: Any) -> Optional[UUID]:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
