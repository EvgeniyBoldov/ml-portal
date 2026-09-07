"""LLM planner adapter for immutable runtime iterations."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import IterationProposal, PlanRequest


class GraphPlanner:
    """The model proposes data only; compilation belongs to the runtime."""

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol) -> None:
        self._llm = StructuredLLMCall(session=session, llm_client=llm_client)
        self._input_builder = PlannerInputBuilder()

    async def plan(
        self,
        *,
        request: PlanRequest,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        budget_registry: Optional[Any] = None,
        planner_budget_entity_id: Optional[str] = None,
        planner_iteration_trace_id: Optional[str] = None,
        **_: Any,
    ) -> IterationProposal:
        result = await self._llm.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload=self._input_builder.build_graph_request(request),
            schema=IterationProposal,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_execution_id=None,
            trace_parent_entity_type="planner_iteration",
            trace_parent_entity_id=planner_iteration_trace_id,
            event_sink=event_sink,
            sandbox_overrides=sandbox_overrides,
            budget_registry=budget_registry,
            budget_entity_id=planner_budget_entity_id,
        )
        return result.value
