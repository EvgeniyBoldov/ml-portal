"""Canonical contracts for the runtime planner/orchestrator boundary.

The planner describes a graph.  The orchestrator is the only component that
executes tasks and mutates their lifecycle.  These contracts deliberately keep
technical execution failures separate from a valid agent result.
"""
from __future__ import annotations

from enum import Enum
import json
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


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_DEPENDENCY = "waiting_dependency"
    WAITING_USER = "waiting_user"
    WAITING_RETRY = "waiting_retry"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    UNFULFILLABLE = "unfulfillable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RequirementStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    WAITING_USER = "waiting_user"
    UNRESOLVABLE = "unresolvable"


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


class PlanNodeKind(str, Enum):
    """Execution role of a persisted plan node."""

    AGENT = "agent"
    PLANNER = "planner"
    SYNTHESIS = "synthesis"


class TaskSuccessAction(str, Enum):
    """What the orchestrator does after a successfully completed task."""

    CONTINUE = "continue"
    REPLAN = "replan"


class FreshnessPolicy(str, Enum):
    """Whether a task may finish from its bounded memory/context alone."""

    ALLOW_MEMORY = "allow_memory"
    REQUIRE_RETRIEVAL = "require_retrieval"


class TaskOutputFulfillment(str, Enum):
    """Evidence class required to satisfy one planned task output."""

    TASK_RESULT = "task_result"
    VERIFIED_RECEIPT = "verified_receipt"
    ARTIFACT = "artifact"


class AgentExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class AgentExecutionCompletion(str, Enum):
    FULFILLED = "fulfilled"
    NEEDS = "needs"
    UNFULFILLABLE = "unfulfillable"


class PlannerDecisionKind(str, Enum):
    """The only terminal decisions a planner may return to the orchestrator."""

    CREATE_PLAN = "create_plan"
    REVISE_PLAN = "revise_plan"
    ASK_USER = "ask_user"
    FAIL_PLAN = "fail_plan"


class NeedSpec(BaseModel):
    ref: str = Field(default="", description="Stable local reference for this need")
    key: str = Field(..., min_length=1)
    kind: Literal["data", "artifact", "decision"] = "data"
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    context: Dict[str, Any] = Field(default_factory=dict)
    resolved_value: Optional[Any] = None
    resolved_by: Optional[str] = None
    resolved_at_iteration: Optional[int] = None

    model_config = {"populate_by_name": True}


class TaskOutputSpec(BaseModel):
    key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    fulfillment: TaskOutputFulfillment = TaskOutputFulfillment.TASK_RESULT

    model_config = {"populate_by_name": True}


class PlannedTask(BaseModel):
    task_id: str = Field(..., min_length=1)
    kind: PlanNodeKind = PlanNodeKind.AGENT
    executor: Optional[str] = Field(default=None, min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    needs: List[NeedSpec] = Field(default_factory=list)
    on_success: TaskSuccessAction = TaskSuccessAction.CONTINUE
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_kind(self) -> "PlannedTask":
        if self.kind == PlanNodeKind.AGENT:
            if not self.executor:
                raise ValueError("agent task requires executor")
            return self
        node_name = "planner checkpoint" if self.kind == PlanNodeKind.PLANNER else "synthesis checkpoint"
        if self.executor:
            raise ValueError(f"{node_name} cannot declare executor")
        if self.inputs:
            raise ValueError(f"{node_name} cannot declare inputs")
        if self.expected_outputs:
            raise ValueError(f"{node_name} cannot declare expected_outputs")
        if self.on_success != TaskSuccessAction.CONTINUE:
            raise ValueError(f"{node_name} cannot declare on_success")
        if self.freshness_policy != FreshnessPolicy.ALLOW_MEMORY:
            raise ValueError(f"{node_name} cannot require retrieval")
        if self.kind == PlanNodeKind.SYNTHESIS:
            if self.depends_on:
                raise ValueError("synthesis checkpoint cannot declare dependencies")
            if self.needs:
                raise ValueError("synthesis checkpoint cannot declare needs")
        return self


class PlanPatch(BaseModel):
    """A complete, validated mutation proposed by the planner."""

    expected_revision: int = Field(..., ge=0)
    decision: PlannerDecisionKind = PlannerDecisionKind.REVISE_PLAN
    goal: Optional[str] = Field(default=None, min_length=1)
    tasks: List[PlannedTask] = Field(default_factory=list)
    remove_task_ids: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    failure_reason: Optional[str] = None
    rationale: str = ""
    trigger: Optional[str] = None

    @model_validator(mode="after")
    def validate_patch(self) -> "PlanPatch":
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("plan patch contains duplicate task ids")
        for task in self.tasks:
            if len(task.depends_on) != len(set(task.depends_on)):
                raise ValueError(f"task {task.task_id} contains duplicate dependencies")
            if task.task_id in task.depends_on:
                raise ValueError(f"task {task.task_id} cannot depend on itself")
        if set(self.remove_task_ids) & set(task_ids):
            raise ValueError("plan patch cannot create and remove the same task")
        if self.decision == PlannerDecisionKind.CREATE_PLAN and self.expected_revision != 0:
            raise ValueError("create_plan is valid only for revision zero")
        if self.decision == PlannerDecisionKind.ASK_USER and not self.question:
            raise ValueError("ask_user requires a question")
        if self.decision == PlannerDecisionKind.FAIL_PLAN and not self.failure_reason:
            raise ValueError("fail_plan requires failure_reason")
        return self


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    available_agents: List[Dict[str, Any]] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    completed_outputs: Dict[str, Any] = Field(default_factory=dict)
    available_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    needs: List[Dict[str, Any]] = Field(default_factory=list)
    last_failure: Optional[Dict[str, Any]] = None
    user_response: Optional[str] = None
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    trigger: Optional[str] = None
    run_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None
    trace_parent_id: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None


class TaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    needs: List[NeedSpec] = Field(default_factory=list)
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: Dict[str, Any] = Field(default_factory=dict)
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY


class TaskOutputValue(BaseModel):
    """One declared, keyed output of a completed agent execution."""

    description: Optional[str] = None
    text: Optional[str] = None
    data: Optional[Any] = None
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)

    # Terminal output values are an executor protocol, not a free-form
    # extension point.  Unknown keys must fail the attempt instead of being
    # silently discarded by Pydantic and later looking like an empty result.
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_content(self) -> "TaskOutputValue":
        if self.text is None and self.data is None and not self.artifacts:
            raise ValueError("task output requires text, data, or artifacts")
        return self


class AgentExecutionResult(BaseModel):
    """Normalized terminal result of one agent executor run.

    It is intentionally distinct from the logical task result.  ``needs`` is
    always present; a completed execution with needs is a successful agent
    execution that did not yet fulfil its task.
    """

    status: AgentExecutionStatus = AgentExecutionStatus.COMPLETED
    completion: AgentExecutionCompletion
    description: str = Field(..., min_length=1)
    outputs: Dict[str, TaskOutputValue] = Field(default_factory=dict)
    needs: List[NeedSpec] = Field(default_factory=list)
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    receipt_refs: List[Dict[str, Any]] = Field(default_factory=list)
    # Assigned by runtime after the agent's JSON has been validated; agents do
    # not get authority to declare this field.
    verified: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_completion(self) -> "AgentExecutionResult":
        if self.status != AgentExecutionStatus.COMPLETED:
            raise ValueError("terminal task completion must use completed execution status")
        if self.completion == AgentExecutionCompletion.NEEDS and not self.needs:
            raise ValueError("needs completion requires at least one need")
        if self.completion == AgentExecutionCompletion.FULFILLED and self.needs:
            raise ValueError("fulfilled completion cannot contain unresolved needs")
        return self


class TaskResult(BaseModel):
    """Runtime-owned result and lifecycle decision for a logical task.

    Technical exceptions, provider timeouts and invalid protocol responses do
    not use this model; they are represented by ``TaskAttemptFailure``.
    """

    outcome: TaskOutcome
    description: str = Field(default="", alias="summary")
    outputs: Dict[str, TaskOutputValue] = Field(default_factory=dict)
    partial_completion: Optional[str] = None
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    needs: List[NeedSpec] = Field(default_factory=list)
    reason_code: Optional[str] = None
    verified: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_outputs(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        outputs = normalized.get("outputs")
        if outputs is None:
            verified = normalized.get("verified")
            if isinstance(verified, dict):
                outputs = verified.get("outputs")
        if isinstance(outputs, dict):
            normalized["outputs"] = {
                str(key): raw if isinstance(raw, TaskOutputValue) or isinstance(raw, dict) and any(
                    field in raw for field in ("text", "data", "artifacts")
                ) else {"data": raw}
                for key, raw in outputs.items()
            }
        return normalized

    @property
    def summary(self) -> str:
        """Compatibility accessor for trace/presentation callers."""
        return self.description

    @model_validator(mode="after")
    def validate_outcome(self) -> "TaskResult":
        if self.outcome == TaskOutcome.COMPLETED and self.needs:
            raise ValueError("completed task cannot contain unresolved needs")
        if self.outcome == TaskOutcome.NEEDS_DEPENDENCY and not self.needs:
            raise ValueError("needs_dependency requires at least one need")
        return self


# Compatibility name for callers during the task-result migration.  The
# executor now returns AgentExecutionResult; this name denotes task state.
AgentTaskResult = TaskResult


class TaskAttemptFailure(BaseModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    retryable: bool = False
    timed_out: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskExecutionError(RuntimeError):
    """Technical task failure which the orchestrator may safely retry.

    A valid ``AgentTaskResult`` represents a completed business decision.  A
    provider outage, timeout, or transport failure is not such a decision and
    must remain on the task-attempt failure path.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = dict(details or {})


class TaskConfirmationRequired(RuntimeError):
    """A task reached an operation gate and must resume from its checkpoint."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = dict(payload or {})
        super().__init__(str(self.payload.get("summary") or self.payload.get("message") or "Operation requires confirmation"))


def parse_agent_execution_result(content: str) -> AgentExecutionResult:
    """Parse the exact JSON protocol; prose and markdown are rejected."""
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


def parse_agent_task_result(content: str) -> TaskResult:
    """Compatibility parser for persisted task-result fixtures only."""
    text = str(content or "").strip()
    if not text:
        raise ValueError("task result is empty")
    return TaskResult.model_validate_json(text)


class PlannerPortProtocol:
    """Documentation-only protocol marker; concrete async ports live in ports.py."""

    pass
