"""Strict contracts for the iterative planner/runtime protocol."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IterationStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_RETRY = "waiting_retry"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    NEEDS_DEPENDENCY = "needs_dependency"
    UNFULFILLABLE = "unfulfillable"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATUSES = frozenset({
    TaskStatus.COMPLETED, TaskStatus.NEEDS_DEPENDENCY, TaskStatus.UNFULFILLABLE,
    TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED,
})


class AttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class TaskOutcome(str, Enum):
    COMPLETED = "completed"
    NEEDS_DEPENDENCY = "needs_dependency"
    UNFULFILLABLE = "unfulfillable"


class TerminalKind(str, Enum):
    PLANNER = "planner"
    SYNTHESIS = "synthesis"


class SchedulerActionKind(str, Enum):
    EXECUTE_TASK = "execute_task"
    WAIT_RETRY = "wait_retry"
    WAIT_INPUT = "wait_input"
    INVOKE_PLANNER = "invoke_planner"
    INVOKE_SYNTHESIS = "invoke_synthesis"
    TERMINAL = "terminal"


class ResolutionAction(str, Enum):
    CONTINUE_WITH_TASKS = "continue_with_tasks"
    ACCEPT_PARTIAL = "accept_partial"
    EXCLUDE_FROM_SCOPE = "exclude_from_scope"
    REPORT_UNRESOLVED = "report_unresolved"


class LimitationAction(str, Enum):
    RECONFIGURE_CREDENTIALS = "reconfigure_credentials"
    GRANT_ACCESS = "grant_access"
    PROVIDE_INPUT = "provide_input"
    RETRY_LATER = "retry_later"
    NONE = "none"


class FreshnessPolicy(str, Enum):
    ALLOW_MEMORY = "allow_memory"
    REQUIRE_RETRIEVAL = "require_retrieval"


class TaskOutputFulfillment(str, Enum):
    TASK_RESULT = "task_result"
    VERIFIED_RECEIPT = "verified_receipt"
    ARTIFACT = "artifact"


class AgentExecutionCompletion(str, Enum):
    FULFILLED = "fulfilled"
    NEEDS = "needs"
    UNFULFILLABLE = "unfulfillable"


class UserLimitation(BaseModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    action: LimitationAction = LimitationAction.NONE
    model_config = {"extra": "forbid"}


class DiscoveredNeed(BaseModel):
    """A missing agent input. Its lifecycle is never agent-authored."""
    ref: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    kind: Literal["data", "artifact", "decision"] = "data"
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    context: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid", "populate_by_name": True}


class TaskOutputSpec(BaseModel):
    key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    fulfillment: TaskOutputFulfillment = TaskOutputFulfillment.TASK_RESULT
    receipt_operations: List[str] = Field(default_factory=list)
    model_config = {"extra": "forbid", "populate_by_name": True}

    @model_validator(mode="after")
    def validate_fulfillment(self) -> "TaskOutputSpec":
        if any(not item or item != item.strip() for item in self.receipt_operations):
            raise ValueError("receipt_operations must contain non-empty canonical names")
        if len(self.receipt_operations) != len(set(self.receipt_operations)):
            raise ValueError("receipt_operations must be unique")
        if self.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT and not self.receipt_operations:
            raise ValueError("verified_receipt output requires receipt_operations")
        if self.fulfillment != TaskOutputFulfillment.VERIFIED_RECEIPT and self.receipt_operations:
            raise ValueError("receipt_operations are allowed only for verified_receipt outputs")
        return self


class PlannedTask(BaseModel):
    """An immutable agent task. Planner and synthesis are not graph nodes."""
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    model_config = {"extra": "forbid"}


class NeedBinding(BaseModel):
    need_task_id: str = Field(..., min_length=1)
    need_ref: str = Field(..., min_length=1)
    producer_task_id: str = Field(..., min_length=1)
    output_key: str = Field(..., min_length=1)
    consumer_task_id: str = Field(..., min_length=1)
    consumer_input_key: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class TaskResolution(BaseModel):
    """Planner's explicit disposition of one prior incomplete task."""
    task_id: str = Field(..., min_length=1)
    action: ResolutionAction
    output_keys: List[str] = Field(default_factory=list)
    replacement_task_ids: List[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_action(self) -> "TaskResolution":
        if self.action == ResolutionAction.ACCEPT_PARTIAL and not self.output_keys:
            raise ValueError("accept_partial requires output_keys")
        if self.action != ResolutionAction.ACCEPT_PARTIAL and self.output_keys:
            raise ValueError("only accept_partial may specify output_keys")
        if self.action == ResolutionAction.CONTINUE_WITH_TASKS and not self.replacement_task_ids:
            raise ValueError("continue_with_tasks requires replacement_task_ids")
        if self.action != ResolutionAction.CONTINUE_WITH_TASKS and self.replacement_task_ids:
            raise ValueError("only continue_with_tasks may specify replacement_task_ids")
        return self


class SynthesisBrief(BaseModel):
    user_question: str = Field(..., min_length=1)
    planned_work: str = Field(..., min_length=1)
    purpose: str = Field(..., min_length=1)
    answer_requirements: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class IterationProposal(BaseModel):
    tasks: List[PlannedTask] = Field(default_factory=list)
    terminal: TerminalKind
    synthesis_brief: Optional[SynthesisBrief] = None
    bindings: List[NeedBinding] = Field(default_factory=list)
    resolutions: List[TaskResolution] = Field(default_factory=list)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_iteration(self) -> "IterationProposal":
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("iteration contains duplicate task ids")
        if self.terminal == TerminalKind.SYNTHESIS and self.synthesis_brief is None:
            raise ValueError("synthesis terminal requires synthesis_brief")
        if self.terminal == TerminalKind.PLANNER and self.synthesis_brief is not None:
            raise ValueError("planner terminal cannot include synthesis_brief")
        known = set(ids)
        for task in self.tasks:
            output_keys = [output.key for output in task.expected_outputs]
            if len(output_keys) != len(set(output_keys)):
                raise ValueError(f"task {task.task_id} contains duplicate expected output keys")
            # Artifact identifiers are issued by the runtime, not by the
            # agent.  One artifact output gives that runtime-issued set one
            # unambiguous owner; allowing several would make every output
            # falsely claim the same artifacts.
            artifact_outputs = sum(
                output.fulfillment == TaskOutputFulfillment.ARTIFACT
                for output in task.expected_outputs
            )
            if artifact_outputs > 1:
                raise ValueError(f"task {task.task_id} may declare at most one artifact output")
            if len(task.depends_on) != len(set(task.depends_on)):
                raise ValueError(f"task {task.task_id} contains duplicate dependencies")
            if task.task_id in task.depends_on:
                raise ValueError(f"task {task.task_id} cannot depend on itself")
            if unknown := set(task.depends_on) - known:
                raise ValueError(f"task {task.task_id} has unknown dependencies: {sorted(unknown)}")
        if len({item.task_id for item in self.resolutions}) != len(self.resolutions):
            raise ValueError("iteration contains duplicate task resolutions")
        for resolution in self.resolutions:
            unknown = set(resolution.replacement_task_ids) - known
            if unknown:
                raise ValueError(f"resolution references unknown replacement tasks: {sorted(unknown)}")
        return self


class PlannerContext(BaseModel):
    goal: str
    trigger: str
    execution_ledger: Dict[str, Any]
    available_agents: List[Dict[str, Any]] = Field(default_factory=list)
    available_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class PlanRequest(BaseModel):
    context: PlannerContext
    run_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None
    trace_parent_id: Optional[str] = None
    model_config = {"extra": "forbid"}


class SchedulerDecision(BaseModel):
    kind: SchedulerActionKind
    task_id: Optional[str] = None
    iteration_id: Optional[str] = None
    retry_at: Optional[str] = None
    reason: Optional[str] = None
    model_config = {"extra": "forbid"}


class TaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: Dict[str, Any] = Field(default_factory=dict)
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    model_config = {"extra": "forbid"}


class TaskOutputValue(BaseModel):
    description: Optional[str] = None
    text: Optional[str] = None
    data: Optional[Any] = None
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_content(self) -> "TaskOutputValue":
        if self.text is None and self.data is None and not self.artifacts:
            raise ValueError("task output requires text, data, or artifacts")
        return self


class AgentExecutionResult(BaseModel):
    completion: AgentExecutionCompletion
    description: str = Field(..., min_length=1)
    outputs: Dict[str, TaskOutputValue] = Field(default_factory=dict)
    needs: List[DiscoveredNeed] = Field(default_factory=list)
    receipt_refs: List[Dict[str, Any]] = Field(default_factory=list)
    limitation: Optional[UserLimitation] = None
    verified: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_completion(self) -> "AgentExecutionResult":
        if self.completion == AgentExecutionCompletion.NEEDS and not self.needs:
            raise ValueError("needs completion requires at least one need")
        if self.completion == AgentExecutionCompletion.FULFILLED and self.needs:
            raise ValueError("fulfilled completion cannot contain unresolved needs")
        if self.completion != AgentExecutionCompletion.NEEDS and self.needs:
            raise ValueError("only needs completion may contain unresolved needs")
        if self.completion == AgentExecutionCompletion.UNFULFILLABLE and self.limitation is None:
            raise ValueError("unfulfillable completion requires a limitation")
        if self.completion != AgentExecutionCompletion.UNFULFILLABLE and self.limitation is not None:
            raise ValueError("only unfulfillable completion may contain a limitation")
        return self


class TaskResult(BaseModel):
    outcome: TaskOutcome
    description: str = Field(..., min_length=1)
    outputs: Dict[str, TaskOutputValue] = Field(default_factory=dict)
    needs: List[DiscoveredNeed] = Field(default_factory=list)
    reason_code: Optional[str] = None
    limitation: Optional[UserLimitation] = None
    verified: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class TaskAttemptFailure(BaseModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    retryable: bool = False
    timed_out: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class TaskExecutionError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code, self.retryable, self.details = code, retryable, dict(details or {})


class TaskConfirmationRequired(RuntimeError):
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = dict(payload or {})
        super().__init__(str(self.payload.get("summary") or self.payload.get("message") or "Operation requires confirmation"))


def parse_agent_execution_result(content: str) -> AgentExecutionResult:
    text = str(content or "").strip()
    if not text:
        raise ValueError("agent returned an empty task result")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("agent task result must be strict JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("agent task result must be a JSON object")
    return AgentExecutionResult.model_validate(payload)
