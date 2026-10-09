"""Strict contracts for the iterative planner/runtime protocol."""
from __future__ import annotations

import json
import hashlib
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.runtime.task_value_normalization import is_absent


def _normalize_reference_list(value: Any) -> Any:
    if is_absent(value):
        return []
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if is_absent(item):
            continue
        item = item.strip() if isinstance(item, str) else item
        if item not in result:
            result.append(item)
    return result


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
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @field_validator("action", mode="before")
    @classmethod
    def absent_action(cls, value: Any) -> Any:
        return LimitationAction.NONE if is_absent(value) else value


class DiscoveredNeed(BaseModel):
    """A missing agent input. Its lifecycle is never agent-authored."""
    ref: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    kind: Literal["data", "artifact", "decision"] = "data"
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    context: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid", "populate_by_name": True, "str_strip_whitespace": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        for key, default in (("kind", "data"), ("schema", {}), ("required", True), ("context", {})):
            if key in value and is_absent(value[key]):
                value[key] = default
        return value

    @field_validator("json_schema", mode="before")
    @classmethod
    def validate_json_schema(cls, value: Any) -> Dict[str, Any]:
        """Reject a malformed need before it becomes persisted plan state.

        A need is supplied by the agent but is later used as the contract for
        a cross-task binding.  Deferring schema validation until that binding
        is planned makes an invalid agent declaration look like a successful
        ``needs_dependency`` task and fails only in a later iteration.
        """
        if not isinstance(value, dict) and not is_absent(value):
            raise ValueError("need schema must be a JSON Schema object")
        return _normalize_nullable_schema(value) if isinstance(value, dict) else {}



class TaskOutputSpec(BaseModel):
    key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = True
    fulfillment: TaskOutputFulfillment = TaskOutputFulfillment.TASK_RESULT
    receipt_operations: List[str] = Field(default_factory=list)
    require_complete_source: bool = Field(default=False, description="Legacy advisory completeness hint; not an acceptance condition.")
    model_config = {"extra": "forbid", "populate_by_name": True, "str_strip_whitespace": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        for key, default in (("required", True), ("fulfillment", "task_result"), ("receipt_operations", []), ("require_complete_source", False)):
            if key in value and is_absent(value[key]):
                value[key] = default
        return value

    @field_validator("json_schema", mode="before")
    @classmethod
    def normalize_schema_dialect(cls, value: Any) -> Dict[str, Any]:
        """Accept JSON Schema only; normalize the legacy OpenAPI nullable form."""
        if not isinstance(value, dict) and not is_absent(value):
            raise ValueError("output schema must be a JSON Schema object")
        return _normalize_nullable_schema(value) if isinstance(value, dict) else {}



class TaskContractRef(BaseModel):
    """Reference frozen into a planned task after planner compilation."""
    mode: TaskContractMode = TaskContractMode.DYNAMIC
    contract_id: Optional[str] = None
    version: Optional[int] = Field(default=None, ge=1)
    contract_hash: Optional[str] = None
    # Preserve published input guidance with the immutable task.
    # These data schemas guide LLMs and never reject actual inputs.
    input_schema: Optional[Dict[str, Any]] = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_reference(self) -> "TaskContractRef":
        if self.mode == TaskContractMode.REGISTERED and not self.contract_id:
            raise ValueError("registered task contract requires contract_id")
        if self.mode == TaskContractMode.DYNAMIC and self.contract_id is not None:
            raise ValueError("dynamic task contract cannot contain contract_id")
        return self


class ResponseSpec(BaseModel):
    """Requested presentation; only file delivery is mandatory."""
    mode: Literal["any", "text", "structured", "artifact"] = "any"
    description: str = ""
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    model_config = {"extra": "forbid", "populate_by_name": True}


class AgentTaskContract(BaseModel):
    """Published, versioned task contract advertised by an agent version."""
    contract_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    description: str = Field(..., min_length=1)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    response_spec: ResponseSpec = Field(default_factory=ResponseSpec)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentTaskContract":
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
    protocol_version: Literal[2] = 2
    response_spec: ResponseSpec = Field(default_factory=ResponseSpec)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    contract: TaskContractRef = Field(default_factory=TaskContractRef)
    depends_on: List[str] = Field(default_factory=list)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    scope_keys: List[str] = Field(default_factory=list, max_length=60)
    scope_mode: Literal["inherit", "replace"] = "inherit"
    scope_reason: str = Field(default="", max_length=600)
    scope_context: Dict[str, Any] = Field(default_factory=dict, exclude=True)
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
        # A planner terminal schedules more work.  With no new tasks it only
        # creates an empty checkpoint/iteration loop; after all prior work is
        # resolved the only valid terminal is synthesis with a user-facing
        # limitation in its brief.
        if self.terminal == TerminalKind.PLANNER and not self.tasks:
            raise ValueError("planner terminal requires at least one task")
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
    task_brief: Dict[str, Any] = Field(default_factory=dict)
    scope_context: Dict[str, Any] = Field(default_factory=dict)
    planner_search_results: List[Dict[str, Any]] = Field(default_factory=list)
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
    protocol_version: Literal[2] = 2
    response_spec: ResponseSpec = Field(default_factory=ResponseSpec)
    expected_outputs: List[TaskOutputSpec] = Field(default_factory=list)
    contract: TaskContractRef = Field(default_factory=TaskContractRef)
    freshness_policy: FreshnessPolicy = FreshnessPolicy.ALLOW_MEMORY
    scope_context: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def unique_output_keys(self) -> "TaskRequest":
        keys = [spec.key for spec in self.expected_outputs]
        if len(keys) != len(set(keys)):
            raise ValueError("task expected_outputs must contain unique keys")
        return self


class ValueOutputSlot(BaseModel):
    kind: Literal["value"]
    value: Any
    model_config = {"extra": "forbid"}


class EvidenceOutputSlot(BaseModel):
    kind: Literal["evidence"]
    refs: List[str] = Field(..., min_length=1)
    model_config = {"extra": "forbid"}

    @field_validator("refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> Any:
        return _normalize_reference_list(value)


class ArtifactOutputSlot(BaseModel):
    kind: Literal["artifact"]
    refs: List[str] = Field(..., min_length=1)
    model_config = {"extra": "forbid"}

    @field_validator("refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> Any:
        return _normalize_reference_list(value)


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


class OutputCoverageClaim(BaseModel):
    """Runtime-checkable proof that a declared list covers a stored selection."""
    output_key: str = Field(..., min_length=1)
    output_path: str = Field(default="", description="Dot-separated path to an array within the output value")
    result_id: str = Field(..., min_length=1)
    query_call_ids: List[str] = Field(..., min_length=1)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @field_validator("output_path", mode="before")
    @classmethod
    def normalize_root_path(cls, value: Any) -> Any:
        return "" if is_absent(value) else value

    @field_validator("query_call_ids", mode="before")
    @classmethod
    def normalize_calls(cls, value: Any) -> Any:
        return _normalize_reference_list(value)


class TaskCompletionDeclaration(BaseModel):
    """Agent-owned completion with a deterministic legacy journal adapter."""
    completion_claim: AgentExecutionCompletion = Field(..., alias="completion")
    answer: Optional[str] = None
    structured_response: Any = None
    needs: List[DiscoveredNeed] = Field(default_factory=list)
    outputs: Dict[str, OutputSlot] = Field(default_factory=dict, exclude=True)
    coverage: List[OutputCoverageClaim] = Field(default_factory=list, exclude=True)
    limitation: Optional[UserLimitation] = Field(default=None, exclude=True)
    model_config = {"extra": "forbid", "populate_by_name": True}

    @property
    def report(self) -> str:
        return self.answer or self.completion_claim.value

    @model_validator(mode="before")
    @classmethod
    def adapt_legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        report = value.pop("report", None)
        if report is not None and "answer" not in value:
            value["answer"] = report
        if "structured_response" not in value and isinstance(value.get("outputs"), dict):
            value["structured_response"] = {
                key: slot.get("value") for key, slot in value["outputs"].items()
                if isinstance(slot, dict) and slot.get("kind") == "value"
            }
        if "limitation" in value and is_absent(value["limitation"]):
            value["limitation"] = None
        for key in ("needs", "outputs", "coverage"):
            if key in value and is_absent(value[key]):
                value[key] = {} if key == "outputs" else []
        return value

    @model_validator(mode="after")
    def validate_completion(self) -> "TaskCompletionDeclaration":
        if len({need.ref for need in self.needs}) != len(self.needs):
            raise ValueError("needs must contain unique refs")
        if self.completion_claim == AgentExecutionCompletion.NEEDS and not self.needs:
            raise ValueError("needs completion requires at least one need")
        if self.completion_claim != AgentExecutionCompletion.NEEDS and self.needs:
            raise ValueError("only needs completion may contain unresolved needs")
        return self


class TaskExecutionReceipt(BaseModel):
    """Runtime-owned pairing of an agent declaration with observed evidence."""
    declaration: TaskCompletionDeclaration
    verified: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class TaskResult(BaseModel):
    outcome: TaskOutcome
    description: str = Field(..., min_length=1)
    protocol_version: Literal[2] = 2
    completion: Optional[AgentExecutionCompletion] = None
    answer: Optional[str] = None
    structured_response: Any = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
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


# Anchors are required by schema-to-grammar providers. Explicit character
# classes also match newlines without DOTALL flags or lookaround support.
_NONBLANK_STRING_PATTERN = r"^[\s\S]*\S[\s\S]*$"


def task_completion_json_schema(request: TaskRequest, *, provider_compatible: bool = False) -> Dict[str, Any]:
    """Pydantic envelope independent of requested data schemas."""
    schema = TaskCompletionDeclaration.model_json_schema(by_alias=True)
    for key in ("outputs", "coverage", "limitation"):
        schema["properties"].pop(key, None)
    schema["$defs"] = {key: val for key, val in schema.get("$defs", {}).items()
                       if key in {"AgentExecutionCompletion", "DiscoveredNeed"}}
    return _terminal_provider_schema(schema) if provider_compatible else schema


def _terminal_provider_schema(schema: Dict[str, Any] | bool) -> Dict[str, Any] | bool:
    """Project schema keywords without mistaking property names for keywords."""
    if isinstance(schema, bool):
        return schema
    result = dict(schema)
    for keyword in ("pattern", "format", "if", "then", "else"):
        result.pop(keyword, None)
    for keyword in ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas"):
        if isinstance(result.get(keyword), dict):
            result[keyword] = {name: _terminal_provider_schema(child)
                               for name, child in result[keyword].items()}
    for keyword in ("items", "additionalProperties", "contains", "not", "propertyNames"):
        if isinstance(result.get(keyword), dict):
            result[keyword] = _terminal_provider_schema(result[keyword])
    for keyword in ("anyOf", "oneOf", "allOf", "prefixItems"):
        if isinstance(result.get(keyword), list):
            result[keyword] = [_terminal_provider_schema(child) if isinstance(child, dict) else child
                               for child in result[keyword]]
    return result


def _normalize_nullable_schema(value: Dict[str, Any]) -> Dict[str, Any]:
    """Convert OpenAPI's nullable marker before Draft 2020-12 validation."""
    normalized: Dict[str, Any] = {}
    for key, child in value.items():
        if isinstance(child, dict):
            normalized[key] = _normalize_nullable_schema(child)
        elif isinstance(child, list):
            normalized[key] = [
                _normalize_nullable_schema(item) if isinstance(item, dict) else item
                for item in child
            ]
        else:
            normalized[key] = child
    if normalized.pop("nullable", False) is True:
        schema_type = normalized.get("type")
        if isinstance(schema_type, str):
            normalized["type"] = [schema_type, "null"]
        elif isinstance(schema_type, list):
            normalized["type"] = list(dict.fromkeys([*schema_type, "null"]))
        else:
            normalized["anyOf"] = [
                {key: child for key, child in normalized.items()},
                {"type": "null"},
            ]
    return normalized
