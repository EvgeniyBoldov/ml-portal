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
    NEEDS_USER_INPUT = "needs_user_input"
    UNFULFILLABLE = "unfulfillable"


class PlannerDecisionKind(str, Enum):
    """The only terminal decisions a planner may return to the orchestrator."""

    CREATE_PLAN = "create_plan"
    REVISE_PLAN = "revise_plan"
    ASK_USER = "ask_user"
    COMPLETE_PLAN = "complete_plan"
    FAIL_PLAN = "fail_plan"


class NeedSpec(BaseModel):
    key: str = Field(..., min_length=1)
    kind: Literal["data", "artifact", "decision"] = "data"
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True

    model_config = {"populate_by_name": True}


class TaskOutputSpec(BaseModel):
    key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")

    model_config = {"populate_by_name": True}


class PlannedTask(BaseModel):
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    needs: List[NeedSpec] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class PlanPatch(BaseModel):
    """A complete, validated mutation proposed by the planner."""

    expected_revision: int = Field(..., ge=0)
    decision: PlannerDecisionKind = PlannerDecisionKind.REVISE_PLAN
    goal: Optional[str] = Field(default=None, min_length=1)
    tasks: List[PlannedTask] = Field(default_factory=list)
    remove_task_ids: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    answer_brief: Optional[str] = None
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
        if self.decision == PlannerDecisionKind.COMPLETE_PLAN and self.tasks:
            raise ValueError("complete_plan cannot add tasks")
        return self


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    available_agents: List[Dict[str, Any]] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    completed_outputs: Dict[str, Any] = Field(default_factory=dict)
    needs: List[Dict[str, Any]] = Field(default_factory=list)
    last_failure: Optional[Dict[str, Any]] = None
    trigger: Optional[str] = None
    run_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None
    trace_parent_id: Optional[str] = None


class TaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    needs: List[NeedSpec] = Field(default_factory=list)
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: Dict[str, Any] = Field(default_factory=dict)


class AgentTaskResult(BaseModel):
    """Valid output of an agent execution attempt.

    Technical exceptions, provider timeouts and invalid protocol responses do
    not use this model; they are represented by ``TaskAttemptFailure``.
    """

    outcome: TaskOutcome
    summary: str = ""
    outputs: Dict[str, Any] = Field(default_factory=dict)
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    needs: List[NeedSpec] = Field(default_factory=list)
    question: Optional[str] = None
    reason_code: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_outcome(self) -> "AgentTaskResult":
        if self.outcome == TaskOutcome.COMPLETED and self.needs:
            raise ValueError("completed task cannot contain unresolved needs")
        if self.outcome == TaskOutcome.NEEDS_DEPENDENCY and not self.needs:
            raise ValueError("needs_dependency requires at least one need")
        if self.outcome == TaskOutcome.NEEDS_USER_INPUT and not self.question:
            raise ValueError("needs_user_input requires a question")
        return self


class TaskAttemptFailure(BaseModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    retryable: bool = False
    timed_out: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


def parse_agent_task_result(content: str) -> AgentTaskResult:
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
    return AgentTaskResult.model_validate(payload)


class PlannerPortProtocol:
    """Documentation-only protocol marker; concrete async ports live in ports.py."""

    pass
