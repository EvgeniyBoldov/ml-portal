"""
BaseRuntime — абстрактный базовый класс для всех runtime-режимов.

Предоставляет общую инфраструктуру:
- LLMAdapter для вызовов LLM
- ExecutionConfigResolver для конфигурации
- RuntimeTraceLogger для run/session logging
- RuntimeLoggingResolver для уровня логирования
- RuntimeSandboxResolver для sandbox overlay helpers
- OperationExecutor для выполнения operations
- AgentPromptRenderer для базового agent prompt
- RunSession factory для логирования
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.runtime.events import RuntimeEvent
from app.agents.runtime.llm import LLMAdapter
from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer
from app.agents.execution_config_resolver import ExecutionConfigResolver
from app.agents.runtime_logging_resolver import RuntimeLoggingResolver
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.agents.runtime_trace_logger import RuntimeTraceLogger
from app.agents.runtime.prompt_assembler import PromptAssembler
from app.agents.runtime.tools import OperationExecutionFacade
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest
    from app.core.http.clients import LLMClientProtocol
    from app.services.run_store import RunStore

logger = get_logger(__name__)


class BaseRuntime(ABC):
    """Abstract base for all runtime execution modes.

    Subclasses implement `execute()` with their specific execution logic.
    All shared infrastructure is available via self.llm, self.config_resolver, etc.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self.llm = LLMAdapter(llm_client)
        self.trace_logger = RuntimeTraceLogger(run_store=run_store)
        self.logging_resolver = RuntimeLoggingResolver()
        self.sandbox_resolver = RuntimeSandboxResolver()
        self.config_resolver = ExecutionConfigResolver()
        self.tools = OperationExecutionFacade()
        self.prompts = AgentPromptRenderer()
        self.prompt_assembler = PromptAssembler(self.prompts)
        self.run_store = run_store

    @abstractmethod
    async def execute(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Execute the runtime and yield events."""
        ...  # pragma: no cover
        # AsyncGenerator requires at least one yield for type-checking
        if False:  # noqa: SIM223
            yield  # type: ignore[misc]

    def _create_run_session(
        self,
        ctx: ToolContext,
        agent_slug: str,
        mode: str,
        logging_level: str = "brief",
        context_snapshot: Optional[Dict[str, Any]] = None,
        enable_logging: bool = True,
    ):
        """Factory method for creating a RunSession."""
        return self.trace_logger.make_run_session(
            ctx=ctx,
            agent_slug=agent_slug,
            mode=mode,
            logging_level=logging_level,
            context_snapshot=context_snapshot,
            enable_logging=enable_logging,
        )

    @staticmethod
    def _build_conversation_summary(
        msgs: List[Dict[str, Any]], max_messages: int = 5,
    ) -> Optional[str]:
        """Build a brief summary of recent conversation for planner context."""
        relevant = [m for m in msgs if m.get("role") != "system"][-max_messages:]
        if not relevant:
            return None
        parts = []
        for m in relevant:
            role = m.get("role", "unknown")
            content = m.get("content", "")[:200]
            parts.append(f"{role}: {content}")
        return "\n".join(parts)
