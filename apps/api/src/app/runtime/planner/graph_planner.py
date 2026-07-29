"""LLM-backed graph planner.

This is deliberately a small decision engine: it proposes a complete graph
mutation, while the orchestrator validates and executes that mutation.  It
never invokes an agent or a tool itself.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Literal, Optional
from uuid import UUID

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import PlanPatch, PlanRequest
from app.runtime.input_builders import PlannerInputBuilder


class PlannerGraphOutput(PlanPatch):
    """Planner wire format with the canonical graph-patch invariants.

    Keeping this as a distinct exported type preserves the role-contract
    surface, while its base class makes semantic errors retryable structured
    output errors rather than failures after the LLM call has completed.
    """

    # Keep the public JSON Schema backward compatible: the prompt editor and
    # its tests consume this enum inline rather than through a $ref.
    decision: Literal["create_plan", "revise_plan", "ask_user", "complete_plan", "fail_plan"]


class GraphPlanner:
    """Planner adapter backed by ``StructuredLLMCall``."""

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
        agent_execution_id: Optional[UUID] = None,
        event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> PlanPatch:
        payload = self._input_builder.build_graph_request(request)
        result = await self._llm.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload=payload,
            schema=PlannerGraphOutput,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_execution_id=agent_execution_id,
            event_sink=event_sink,
            sandbox_overrides=sandbox_overrides,
        )
        return result.value

    async def create_or_revise(self, *, request: PlanRequest) -> PlanPatch:
        return await self.plan(request=request)
