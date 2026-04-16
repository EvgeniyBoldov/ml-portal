"""RuntimeTraceLogger — lifecycle, routing and trace logging for runtime."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.services.execution_trace_logger import ExecutionTraceLogger

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.services.run_store import RunStore
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class RuntimeTraceLogger:
    def __init__(
        self,
        session: Optional["AsyncSession"] = None,
        session_factory: Any = None,
        run_store: Optional["RunStore"] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.run_store = run_store
        self.sandbox_overrides = sandbox_overrides or {}
        self.trace = ExecutionTraceLogger(session=session, run_store=run_store)

    def attach_context(self, ctx: Any) -> Any:
        if hasattr(ctx, "get_runtime_deps") and hasattr(ctx, "set_runtime_deps"):
            deps = ctx.get_runtime_deps()
            if self.session_factory is not None:
                deps.session_factory = deps.session_factory or self.session_factory
            if self.sandbox_overrides:
                merged_overrides: Dict[str, Any] = {}
                if isinstance(deps.sandbox_overrides, dict):
                    merged_overrides.update(deps.sandbox_overrides)
                merged_overrides.update(self.sandbox_overrides)
                deps.sandbox_overrides = merged_overrides
            deps.runtime_trace_logger = self
            ctx.set_runtime_deps(deps)
            return ctx

        extra = getattr(ctx, "extra", None)
        if extra is None:
            extra = {}
            setattr(ctx, "extra", extra)
        if self.session_factory is not None:
            extra.setdefault("session_factory", self.session_factory)
        if self.sandbox_overrides:
            merged_overrides = dict(extra.get("sandbox_overrides") or {})
            merged_overrides.update(self.sandbox_overrides)
            extra["sandbox_overrides"] = merged_overrides
        extra.setdefault("runtime_trace_logger", self)
        return ctx

    def make_run_session(
        self,
        *,
        ctx: "ToolContext",
        agent_slug: str,
        mode: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        logging_level: str = "brief",
        context_snapshot: Optional[Dict[str, Any]] = None,
        enable_logging: bool = True,
    ) -> Any:
        from app.agents.runtime.session import RunSession

        snapshot = {"agent_slug": agent_slug, "mode": mode}
        if context_snapshot:
            snapshot.update(context_snapshot)
        return RunSession(
            run_store=self.run_store,
            tenant_id=tenant_id or getattr(ctx, "tenant_id", None),
            agent_slug=agent_slug,
            logging_level=logging_level,
            user_id=user_id or getattr(ctx, "user_id", None),
            chat_id=chat_id if chat_id is not None else getattr(ctx, "chat_id", None),
            context_snapshot=snapshot,
            enable_logging=enable_logging,
            trace_logger=self.trace,
        )

    async def log_error(
        self,
        run_id: Optional[UUID],
        *,
        stage: str,
        error: Exception | str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[UUID]:
        payload = dict(data or {})
        payload.setdefault("stage", stage)
        payload.setdefault("error_type", type(error).__name__ if isinstance(error, Exception) else "error")
        payload.setdefault("message", str(error))
        logger.error("[Runtime] %s failed: %s", stage, error)
        return await self.trace.log_step(
            run_id,
            step_type="error",
            data=payload,
            error=str(error),
        )
