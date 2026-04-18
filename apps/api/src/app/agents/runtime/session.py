"""
RunSession — lifecycle logging для runtime execution.
Инкапсулирует start → log_step → finish.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.services.runtime_terminal_status import normalize_run_status_for_storage

if TYPE_CHECKING:
    from app.services.execution_trace_logger import ExecutionTraceLogger
    from app.services.run_store import RunStore

logger = get_logger(__name__)


class RunSession:
    """Helper class to encapsulate run lifecycle: start, log_step, finish."""

    def __init__(
        self,
        run_store: Optional[RunStore],
        tenant_id: str,
        agent_slug: str,
        logging_level: str = "brief",
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
        enable_logging: bool = True,
        trace_logger: Optional["ExecutionTraceLogger"] = None,
    ) -> None:
        self.run_store = run_store
        self.tenant_id = tenant_id
        self.agent_slug = agent_slug
        self.logging_level = logging_level
        self.user_id = user_id
        self.chat_id = chat_id
        self.context_snapshot = context_snapshot
        self.enable_logging = enable_logging
        self.run_id: Optional[UUID] = None
        self.trace_logger = trace_logger or self._build_trace_logger(run_store)
        self._should_log = enable_logging and run_store is not None

    @staticmethod
    def _build_trace_logger(run_store: Optional["RunStore"]) -> "ExecutionTraceLogger":
        from app.services.execution_trace_logger import ExecutionTraceLogger

        return ExecutionTraceLogger(run_store=run_store)

    async def start(self) -> Optional[UUID]:
        """Start run logging. Returns run_id or None if logging disabled."""
        if not self._should_log:
            return None
        try:
            self.run_id = await self.trace_logger.start_run(
                tenant_id=self.tenant_id,
                agent_slug=self.agent_slug,
                logging_level=self.logging_level,
                user_id=self.user_id,
                chat_id=self.chat_id,
                context_snapshot=self.context_snapshot,
            )
            return self.run_id
        except Exception as e:
            logger.warning(f"Failed to start run logging: {e}")
            self._should_log = False
            return None

    async def log_step(
        self,
        step_type: str,
        data: Dict[str, Any],
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log a step. Silently disables logging on first failure."""
        if not self._should_log or not self.run_id:
            return
        try:
            await self.trace_logger.log_step(
                self.run_id, step_type=step_type, data=data,
                tokens_in=tokens_in, tokens_out=tokens_out,
                duration_ms=duration_ms, error=error,
            )
        except Exception as e:
            logger.warning(f"Failed to log step {step_type}: {e}")
            self._should_log = False

    async def finish(self, status: str, error: Optional[str] = None) -> None:
        """Finish run logging."""
        if not self._should_log or not self.run_id:
            return
        try:
            normalized_status = normalize_run_status_for_storage(status)
            await self.trace_logger.finish_run(self.run_id, status=normalized_status, error=error)
        except Exception as e:
            logger.warning(f"Failed to finish run logging: {e}")
