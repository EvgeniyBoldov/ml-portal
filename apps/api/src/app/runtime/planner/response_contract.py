"""LLM-facing planner declarations and lossless envelope compatibility."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, GetJsonSchemaHandler, ValidationInfo, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from app.runtime.orchestrator_contracts import IterationProposal, PlannedTask, SynthesisBrief, TaskContractRef
from app.runtime.interaction import InteractionQuestion
from app.runtime.memory.role_tools import MemoryToolCall


class PlannerContractInput(TaskContractRef):
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(super().__get_pydantic_json_schema__(core_schema, handler))
        for key in ("contract_hash", "input_schema"):
            schema["properties"].pop(key, None)
        return schema


class PlannerTaskInput(PlannedTask):
    contract: PlannerContractInput = Field(default_factory=PlannerContractInput)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(super().__get_pydantic_json_schema__(core_schema, handler))
        for key in ("scope_context", "protocol_version"):
            schema["properties"].pop(key, None)
        return schema


class PlannerBriefInput(SynthesisBrief):
    # Preserve a legacy explicit question for the immutable-goal check.
    user_question: str | None = Field(default=None, min_length=1)


class PlannerProposalInput(IterationProposal):
    tasks: list[PlannerTaskInput] = Field(default_factory=list)
    synthesis_brief: PlannerBriefInput | None = None


PlannerMemoryToolCall = MemoryToolCall


class PlannerWaitUntil(BaseModel):
    """A requested durable wake time; authorization and bounds are runtime-owned."""
    wake_at: datetime
    reason: str = Field(..., min_length=1, max_length=500)
    next_check: str | None = Field(default=None, max_length=1_000)
    user_update: str | None = Field(default=None, max_length=2_000)
    model_config = {"extra": "forbid"}

    @field_validator("wake_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("wake_at must include a timezone")
        return value.astimezone(timezone.utc)


class PlannerStep(BaseModel):
    """One direct planner decision: contextual read or persisted proposal."""
    kind: Literal["tool_call", "proposal", "interaction", "wait_until"]
    tool_call: PlannerMemoryToolCall | None = None
    proposal: PlannerProposalInput | None = None
    interaction: InteractionQuestion | None = None
    wait_until: PlannerWaitUntil | None = None
    model_config = {"extra": "forbid"}

    @field_validator("proposal", mode="before")
    @classmethod
    def accept_runtime_proposal(cls, value: Any) -> Any:
        # Internal callers may already hold a canonical persisted iteration.
        return value.model_dump(mode="json", by_alias=True) if isinstance(value, IterationProposal) else value

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Publish the same payload selection enforced by validate_shape."""
        schema = handler.resolve_ref_schema(super().__get_pydantic_json_schema__(core_schema, handler))
        schema["oneOf"] = [
            {
                "properties": {
                    "kind": {"const": kind},
                    payload: {"type": "object"},
                    **{
                        other: {"type": "null"}
                        for other in ("tool_call", "proposal", "interaction", "wait_until") if other != payload
                    },
                },
                "required": [payload],
            }
            for kind, payload in (("tool_call", "tool_call"), ("proposal", "proposal"),
                                  ("interaction", "interaction"), ("wait_until", "wait_until"))
        ]
        return schema

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_proposal(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict) or "kind" in value:
            return value
        adapted = value
        operation = None
        # Accept one extra envelope only; never search inside arbitrary data.
        single_payload = next(
            (key for key in ("tool_call", "interaction", "wait_until") if set(value) == {key}),
            None,
        )
        if single_payload is not None:
            # Some models emit the payload object without its discriminator.
            # A single root payload identifies the step unambiguously, so
            # recover the kind instead of failing the whole decision.
            adapted = {"kind": single_payload, single_payload: value[single_payload]}
            operation = "infer_kind_from_payload"
        elif set(value) == {"proposal"} and isinstance(value["proposal"], dict):
            inner = value["proposal"]
            if inner.get("kind") == "proposal" and "proposal" in inner:
                adapted, operation = dict(inner), "unwrap_proposal_envelope"
            elif inner.get("kind") == "proposal" and "terminal" in inner:
                adapted = {"kind": "proposal", "proposal": {k: v for k, v in inner.items() if k != "kind"}}
                operation = "move_proposal_kind_to_root"
            elif "kind" not in inner and "terminal" in inner:
                adapted, operation = {"kind": "proposal", "proposal": inner}, "infer_proposal_kind"
        elif "terminal" in value:
            adapted, operation = {"kind": "proposal", "proposal": value}, "wrap_legacy_proposal"
        if operation and info.context is not None:
            info.context.setdefault("response_normalizations", []).append({"path": "$", "operation": operation})
        return adapted

    @model_validator(mode="before")
    @classmethod
    def discard_completed_resolution_noops(cls, value: Any, info: ValidationInfo) -> Any:
        """Use caller-owned ledger state, never status claims from model JSON."""
        ledger = (info.context or {}).get("planner_execution_ledger")
        if not isinstance(value, dict) or not isinstance(ledger, dict):
            return value
        completed = {item.get("task_id") for item in ledger.get("tasks", [])
                     if isinstance(item, dict) and isinstance(item.get("task_id"), str)
                     and item.get("status") == "completed"}
        if not completed:
            return value
        proposal = value.get("proposal", value)
        if not isinstance(proposal, dict) or not isinstance(proposal.get("resolutions"), list):
            return value
        retained = []
        for index, item in enumerate(proposal["resolutions"]):
            # A completed task has no disposition left to apply. Never drop
            # a resolution that carries replacement/binding intent.
            if (isinstance(item, dict) and isinstance(item.get("task_id"), str)
                    and item["task_id"] in completed
                    and not item.get("replacement_task_ids") and not item.get("output_keys")
                    and item.get("action", item.get("resolution")) == "completed"
                    and set(item) <= {"task_id", "action", "resolution", "reason", "attempts"}):
                if info.context is not None:
                    info.context.setdefault("response_normalizations", []).append({
                        "path": f"$.proposal.resolutions[{index}]",
                        "operation": "drop_completed_task_status_marker",
                    })
                continue
            retained.append(item)
        if len(retained) == len(proposal["resolutions"]):
            return value
        updated = {**proposal, "resolutions": retained}
        return {**value, "proposal": updated} if "proposal" in value else updated

    def to_runtime_proposal(self, *, goal: str) -> IterationProposal:
        if self.proposal is None:
            raise ValueError("only a proposal step can compile to an iteration")
        data = self.proposal.model_dump(mode="json", by_alias=True)
        brief = data.get("synthesis_brief")
        if brief is not None and brief.get("user_question") is None:
            brief["user_question"] = goal
        return IterationProposal.model_validate(data)

    @model_validator(mode="after")
    def validate_shape(self) -> "PlannerStep":
        if self.kind == "interaction":
            if self.interaction is None or any((self.tool_call is not None, self.proposal is not None, self.wait_until is not None)):
                raise ValueError("interaction step requires only an interaction question")
            return self
        if self.kind == "wait_until":
            if self.wait_until is None or any((self.tool_call is not None, self.proposal is not None, self.interaction is not None)):
                raise ValueError("wait_until step requires only a wait_until payload")
            return self
        if self.interaction is not None:
            raise ValueError("interaction question requires kind=interaction")
        if self.wait_until is not None:
            raise ValueError("wait_until payload requires kind=wait_until")
        if self.kind == "tool_call" and self.tool_call is None:
            raise ValueError("tool_call step requires tool_call")
        if self.kind == "proposal" and self.proposal is None:
            raise ValueError("proposal step requires proposal")
        if self.kind == "tool_call" and self.proposal is not None:
            raise ValueError("tool_call step cannot contain proposal")
        if self.kind == "proposal" and self.tool_call is not None:
            raise ValueError("proposal step cannot contain tool_call")
        return self

