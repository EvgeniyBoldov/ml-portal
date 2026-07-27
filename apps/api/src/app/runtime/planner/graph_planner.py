"""LLM-backed graph planner.

This is deliberately a small decision engine: it proposes a complete graph
mutation, while the orchestrator validates and executes that mutation.  It
never invokes an agent or a tool itself.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import PlanPatch, PlanRequest, PlannedTask
from app.runtime.input_builders import PlannerInputBuilder


class PlannerGraphOutput(BaseModel):
    """Strict wire format returned by the planner role."""

    decision: Literal["create_plan", "revise_plan", "ask_user", "complete_plan", "fail_plan"]
    expected_revision: int = Field(..., ge=0)
    rationale: str = ""
    goal: Optional[str] = None
    tasks: List[PlannedTask] = Field(default_factory=list)
    remove_task_ids: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    answer_brief: Optional[str] = None
    failure_reason: Optional[str] = None
    trigger: Optional[str] = None


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
        try:
            return PlanPatch.model_validate(result.value.model_dump(mode="json"))
        except Exception as exc:  # validation is a planner protocol failure
            raise StructuredCallError(
                f"planner returned an invalid graph patch: {exc}",
                original_exception=exc,
            ) from exc

    async def create_or_revise(self, *, request: PlanRequest) -> PlanPatch:
        return await self.plan(request=request)
