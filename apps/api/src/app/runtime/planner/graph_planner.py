"""LLM-backed graph planner.

This is deliberately a small decision engine: it proposes a complete graph
mutation, while the orchestrator validates and executes that mutation.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import (
    PlanPatch,
    PlanRequest,
    PlannedTask,
    PlannerDecisionKind,
    PlanNodeKind,
    TaskOutputSpec,
    TaskSuccessAction,
    FreshnessPolicy,
)
from app.runtime.input_builders import PlannerInputBuilder


class PlannerPlannedTask(BaseModel):
    """Planner-facing task contract.

    Runtime needs are produced by executors when they discover a genuine
    missing dependency.  A planner may resolve pending needs by adding
    producer tasks, but must never manufacture new needs itself.
    """

    task_id: str = Field(..., min_length=1)
    kind: PlanNodeKind = PlanNodeKind.AGENT
    executor: Optional[str] = Field(default=None, min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    on_success: TaskSuccessAction = TaskSuccessAction.CONTINUE
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_kind(self) -> "PlannerPlannedTask":
        PlannedTask(
            task_id=self.task_id,
            kind=self.kind,
            executor=self.executor,
            intent=self.intent,
            instructions=self.instructions,
            inputs=self.inputs,
            expected_outputs=self.expected_outputs,
            depends_on=self.depends_on,
            needs=[],
            on_success=self.on_success,
            freshness_policy=self.freshness_policy,
        )
        return self

    def to_runtime_task(self) -> PlannedTask:
        return PlannedTask(
            task_id=self.task_id,
            kind=self.kind,
            executor=self.executor,
            intent=self.intent,
            instructions=self.instructions,
            inputs=self.inputs,
            expected_outputs=self.expected_outputs,
            depends_on=self.depends_on,
            needs=[],
            on_success=self.on_success,
            freshness_policy=self.freshness_policy,
        )


class PlannerGraphOutput(BaseModel):
    """Semantic planner output exposed to the LLM.

    The model has no authority over optimistic locking, persistence lifecycle
    or runtime triggers.  Those values are attached by ``GraphPlanner`` after
    the response has passed semantic validation.
    """

    action: Literal["apply_graph", "ask_user", "fail"]
    tasks: List[PlannerPlannedTask] = Field(default_factory=list)
    remove_task_ids: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    failure_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_semantic_output(self) -> "PlannerGraphOutput":
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("planner output contains duplicate task ids")
        for task in self.tasks:
            if len(task.depends_on) != len(set(task.depends_on)):
                raise ValueError(f"task {task.task_id} contains duplicate dependencies")
            if task.task_id in task.depends_on:
                raise ValueError(f"task {task.task_id} cannot depend on itself")
        if set(self.remove_task_ids) & set(task_ids):
            raise ValueError("planner output cannot create and remove the same task")
        if self.action == "ask_user" and not self.question:
            raise ValueError("ask_user requires a question")
        if self.action == "fail" and not self.failure_reason:
            raise ValueError("fail requires failure_reason")
        if self.action != "apply_graph" and (self.tasks or self.remove_task_ids):
            raise ValueError(f"{self.action} cannot mutate tasks")
        return self

    def to_plan_patch(self, *, plan: Dict[str, Any]) -> PlanPatch:
        """Attach runtime-owned lifecycle values to a validated mutation."""
        revision = int(plan.get("revision") or 0)
        has_existing_graph = bool(plan.get("tasks")) or revision > 0
        decision = {
            "apply_graph": (
                PlannerDecisionKind.REVISE_PLAN
                if has_existing_graph
                else PlannerDecisionKind.CREATE_PLAN
            ),
            "ask_user": PlannerDecisionKind.ASK_USER,
            "fail": PlannerDecisionKind.FAIL_PLAN,
        }[self.action]
        return PlanPatch(
            expected_revision=revision,
            decision=decision,
            tasks=[task.to_runtime_task() for task in self.tasks],
            remove_task_ids=self.remove_task_ids,
            question=self.question,
            failure_reason=self.failure_reason,
        )


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
        return result.value.to_plan_patch(plan=request.plan)

    async def create_or_revise(self, *, request: PlanRequest) -> PlanPatch:
        return await self.plan(request=request)
