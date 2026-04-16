"""
Runtime module — ядро выполнения агентов.

Flow:
  RuntimePipeline (triage → route → dispatch)
    ├─ final     → inline triage answer (no runtime needed)
    ├─ clarify   → ask user for more info
    └─ orchestrate → PlannerRuntime (next-step planner)
                       └─ AgentToolRuntime (autonomous agent with tool-call loop)

Modules:
- events.py      — RuntimeEvent, RuntimeEventType
- policy.py      — PolicyLimits, GenerationParams
- session.py     — RunSession (lifecycle logging)
- llm.py         — LLMAdapter (call + stream)
- tools.py       — ToolExecutor
- agent_prompt_renderer.py — AgentPromptRenderer
- base.py        — BaseRuntime (abstract)
- agent.py       — AgentToolRuntime (sub-agent with tool loop, used by planner)
- planner.py     — PlannerRuntime (next-step orchestrator)
- logging.py     — LoggingLevel, LoggingConfig
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest
    from app.core.http.clients import LLMClientProtocol
    from app.services.run_store import RunStore

logger = get_logger(__name__)


class AgentRuntime:
    """Facade that exposes the planner as the single runtime entry point.

    Pipeline calls run_sequential_planner(). The planner internally
    delegates to AgentToolRuntime for each agent sub-call.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self.llm_client = llm_client
        self.run_store = run_store
        self._planner: Optional[PlannerRuntime] = None

    @property
    def planner(self) -> PlannerRuntime:
        if self._planner is None:
            from app.agents.runtime.planner import PlannerRuntime as PlannerRuntimeFactory

            self._planner = PlannerRuntimeFactory(self.llm_client, self.run_store)
        return self._planner

    async def run_sequential_planner(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Run the next-step planner that orchestrates agents."""
        async for event in self.planner.execute(
            exec_request=exec_request,
            messages=messages,
            ctx=ctx,
            model=model,
            enable_logging=enable_logging,
        ):
            yield event


__all__ = [
    # Facade
    "AgentRuntime",
    # Events
    "RuntimeEvent",
    "RuntimeEventType",
    # Policy & Generation
    "PolicyLimits",
    "GenerationParams",
]
