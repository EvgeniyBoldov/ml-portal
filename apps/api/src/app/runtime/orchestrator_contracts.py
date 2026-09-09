"""Strict contracts for the iterative planner/runtime protocol."""
from __future__ import annotations

import json
import hashlib
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
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
    COMPLETED = "completed"
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


class TaskContractMode(str, Enum):
    """Who owns a task contract.

    Registered contracts are published by an agent version.  Dynamic contracts
    are intentionally explicit: they remain available for general-purpose
    agents, but are compiled and validated before an attempt starts.
    """
    REGISTERED = "registered"
    DYNAMIC = "dynamic"


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
        try:
            import jsonschema
            jsonschema.Draft202012Validator.check_schema(self.json_schema)
        except Exception as exc:
            raise ValueError(f"output schema is invalid: {exc}") from exc
        if self._contains_forbidden_transport_field(self.json_schema):
            raise ValueError("output schema must not request raw tool payload fields")
        if any(not item or item != item.strip() for item in self.receipt_operations):
            raise ValueError("receipt_operations must contain non-empty canonical names")
        if len(self.receipt_operations) != len(set(self.receipt_operations)):
            raise ValueError("receipt_operations must be unique")
        if self.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT and not self.receipt_operations:
            raise ValueError("verified_receipt output requires receipt_operations")
        if self.fulfillment != TaskOutputFulfillment.VERIFIED_RECEIPT and self.receipt_operations:
            raise ValueError("receipt_operations are allowed only for verified_receipt outputs")
        return self

    @staticmethod
    def _contains_forbidden_transport_field(value: Any) -> bool:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict) and "raw_content" in properties:
                return True
            return any(TaskOutputSpec._contains_forbidden_transport_field(item) for item in value.values())
        if isinstance(value, list):
            return any(TaskOutputSpec._contains_forbidden_transport_field(item) for item in value)
        return False


class TaskContractRef(BaseModel):
    """Reference frozen into a planned task after planner compilation."""
    mode: TaskContractMode = TaskContractMode.DYNAMIC
    contract_id: Optional[str] = None
    version: Optional[int] = Field(default=None, ge=1)
    contract_hash: Optional[str] = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_reference(self) -> "TaskContractRef":
        if self.mode == TaskContractMode.REGISTERED and not self.contract_id:
            raise ValueError("registered task contract requires contract_id")
        if self.mode == TaskContractMode.DYNAMIC and self.contract_id is not None:
            raise ValueError("dynamic task contract cannot contain contract_id")
        return self


class AgentTaskContract(BaseModel):
    """Published, versioned task contract advertised by an agent version."""
    contract_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    description: str = Field(..., min_length=1)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentTaskContract":
        try:
            import jsonschema
            jsonschema.Draft202012Validator.check_schema(self.input_schema)
        except Exception as exc:
            raise ValueError(f"input schema is invalid: {exc}") from exc
        keys = [item.key for item in self.expected_outputs]
        if len(keys) != len(set(keys)):
            raise ValueError("task contract contains duplicate output keys")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class PlannedTask(BaseModel):
    """An immutable agent task. Planner and synthesis are not graph nodes."""
    task_id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    contract: TaskContractRef = Field(default_factory=TaskContractRef)
    depends_on: List[str] = Field(default_factory=list)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_contract_shape(self) -> "PlannedTask":
        if self.contract.mode == TaskContractMode.REGISTERED and self.expected_outputs:
            raise ValueError("registered task contract must be resolved by runtime, not planner expected_outputs")
        return self


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

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Expose terminal conditionality to the model as well as Pydantic.

        Pydantic's optional field schema cannot express this cross-field rule
        by itself; without this projection a provider can emit a syntactically
        valid synthesis proposal that the runtime must later reject.
        """
        schema = super().model_json_schema(*args, **kwargs)
        schema.setdefault("allOf", []).extend([
            {
                "if": {"properties": {"terminal": {"const": TerminalKind.SYNTHESIS.value}}, "required": ["terminal"]},
                "then": {"required": ["synthesis_brief"]},
            },
            {
                "if": {"properties": {"terminal": {"const": TerminalKind.PLANNER.value}}, "required": ["terminal"]},
                "then": {"properties": {"synthesis_brief": {"type": "null"}}},
            },
        ])
        return schema


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
    contract: TaskContractRef = Field(default_factory=TaskContractRef)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    model_config = {"extra": "forbid"}


class ValueOutputSlot(BaseModel):
    kind: Literal["value"]
    value: Any
    model_config = {"extra": "forbid"}


class EvidenceOutputSlot(BaseModel):
    kind: Literal["evidence"]
    refs: List[str] = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class ArtifactOutputSlot(BaseModel):
    kind: Literal["artifact"]
    refs: List[str] = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


OutputSlot = Annotated[
    Union[ValueOutputSlot, EvidenceOutputSlot, ArtifactOutputSlot],
    Field(discriminator="kind"),
]


class EvidenceSelection(BaseModel):
    """Runtime projection retained for synthesis and audit compatibility."""
    result_ref: str = Field(..., min_length=1)
    output_keys: List[str] = Field(default_factory=list)
    description: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class ArtifactSelection(BaseModel):
    """Runtime projection retained for synthesis and audit compatibility."""
    artifact_ref: str = Field(..., min_length=1)
    output_key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class TaskCompletionDeclaration(BaseModel):
    """Agent-authored claim. Runtime alone verifies it and computes TaskResult."""
    completion_claim: AgentExecutionCompletion = Field(..., alias="completion")
    report: str = Field(..., min_length=1)
    outputs: Dict[str, OutputSlot] = Field(default_factory=dict)
    needs: List[DiscoveredNeed] = Field(default_factory=list)
    limitation: Optional[UserLimitation] = None
    model_config = {"extra": "forbid", "populate_by_name": True}

    @model_validator(mode="after")
    def validate_completion(self) -> "TaskCompletionDeclaration":
        if self.completion_claim == AgentExecutionCompletion.NEEDS and not self.needs:
            raise ValueError("needs completion requires at least one need")
        if self.completion_claim == AgentExecutionCompletion.FULFILLED and self.needs:
            raise ValueError("fulfilled completion cannot contain unresolved needs")
        if self.completion_claim != AgentExecutionCompletion.NEEDS and self.needs:
            raise ValueError("only needs completion may contain unresolved needs")
        if self.completion_claim == AgentExecutionCompletion.UNFULFILLABLE and self.limitation is None:
            raise ValueError("unfulfillable completion requires a limitation")
        if self.completion_claim != AgentExecutionCompletion.UNFULFILLABLE and self.limitation is not None:
            raise ValueError("only unfulfillable completion may contain a limitation")
        return self


class TaskExecutionReceipt(BaseModel):
    """Runtime-owned pairing of an agent declaration with observed evidence."""
    declaration: TaskCompletionDeclaration
    verified: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class TaskResult(BaseModel):
    outcome: TaskOutcome
    description: str = Field(..., min_length=1)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    output_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    needs: List[DiscoveredNeed] = Field(default_factory=list)
    reason_code: Optional[str] = None
    limitation: Optional[UserLimitation] = None
    verified: Dict[str, Any] = Field(default_factory=dict)
    evidence_selections: List[EvidenceSelection] = Field(default_factory=list)
    artifact_selections: List[ArtifactSelection] = Field(default_factory=list)
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


def parse_task_completion_declaration(content: str) -> TaskCompletionDeclaration:
    text = str(content or "").strip()
    if not text:
        raise ValueError("agent returned an empty task result")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("agent task result must be strict JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("agent task result must be a JSON object")
    return TaskCompletionDeclaration.model_validate(payload)


def task_completion_json_schema(request: TaskRequest) -> Dict[str, Any]:
    """Build the sole terminal declaration schema from the compiled contract."""
    def slot_schema(spec: TaskOutputSpec) -> Dict[str, Any]:
        if spec.fulfillment == TaskOutputFulfillment.TASK_RESULT:
            return {
                "type": "object", "additionalProperties": False,
                "properties": {"kind": {"const": "value"}, "value": spec.json_schema},
                "required": ["kind", "value"],
            }
        kind = "evidence" if spec.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT else "artifact"
        return {
            "type": "object", "additionalProperties": False,
            "properties": {"kind": {"const": kind}, "refs": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}},
            "required": ["kind", "refs"],
        }

    output_properties = {item.key: slot_schema(item) for item in request.expected_outputs}
    required_outputs = [item.key for item in request.expected_outputs if item.required]
    schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "completion": {"enum": [item.value for item in AgentExecutionCompletion]},
            "report": {"type": "string", "minLength": 1},
            "outputs": {
                "type": "object", "additionalProperties": False,
                "properties": output_properties,
            },
            "needs": {"type": "array", "items": {"type": "object"}},
            "limitation": {"type": "object"},
        },
        "required": ["completion", "report", "outputs", "needs"],
    }
    schema["allOf"] = [
        {
            "if": {"properties": {"completion": {"const": AgentExecutionCompletion.FULFILLED.value}}, "required": ["completion"]},
            "then": {"properties": {"outputs": {"required": required_outputs}}, "not": {"required": ["limitation"]}},
        },
        {
            "if": {"properties": {"completion": {"const": AgentExecutionCompletion.NEEDS.value}}, "required": ["completion"]},
            "then": {"properties": {"needs": {"minItems": 1}}, "not": {"required": ["limitation"]}},
        },
        {
            "if": {"properties": {"completion": {"const": AgentExecutionCompletion.UNFULFILLABLE.value}}, "required": ["completion"]},
            "then": {"required": ["limitation"]},
        },
    ]
    return schema
