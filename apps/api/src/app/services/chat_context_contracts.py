"""Strict, bounded contracts for chat-local working context.

These models deliberately form a small application boundary. LLM output and
ORM JSON never cross it as arbitrary dictionaries.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


ChatContextKind = Literal["scope", "goal", "term_binding", "artifact_ref", "open_loop", "decision", "recent_anchor", "task_result_ref"]
ChatContextAction = Literal["add", "update", "supersede", "close", "expire", "touch"]


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trust_class: Literal["application_verified", "runtime_normalized", "user_explicit", "model_inferred"] = "runtime_normalized"


class ScopePayload(_Payload):
    project_keys: list[str] = Field(default_factory=list, max_length=20)
    project_keys_trust_class: Literal["application_verified", "runtime_normalized", "user_explicit", "model_inferred"] = "application_verified"
    topic: str = Field(default="", max_length=600)
    topic_trust_class: Literal["application_verified", "runtime_normalized", "user_explicit", "model_inferred"] = "runtime_normalized"
    entity_refs: list[str] = Field(default_factory=list, max_length=20)
    entity_refs_trust_class: Literal["application_verified", "runtime_normalized", "user_explicit", "model_inferred"] = "application_verified"
    source: Literal["explicit", "inferred"] = "explicit"


class TopicScopePayload(BaseModel):
    """The compactor may infer a topic, never a project or entity identity."""
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=600)
    topic_trust_class: Literal["model_inferred"] = "model_inferred"
    source: Literal["inferred"] = "inferred"


class GoalPayload(_Payload):
    text: str = Field(min_length=1, max_length=1200)
    status: Literal["active", "completed"] = "active"


class TermBindingPayload(_Payload):
    glossary_entry_id: str = Field(min_length=1, max_length=255)
    term: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=10)


class ArtifactPayload(_Payload):
    artifact_id: str = Field(min_length=1, max_length=255)
    role: str = Field(default="referenced", max_length=64)
    file_name: str = Field(default="", max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)


class OpenLoopPayload(_Payload):
    status: Literal["waiting", "blocked"]
    reason_code: str = Field(default="", max_length=128)
    user_message: str = Field(default="", max_length=600)


class DecisionPayload(_Payload):
    text: str = Field(min_length=1, max_length=600)
    constraint: str = Field(default="", max_length=600)


class RecentAnchorPayload(_Payload):
    user_intent: str = Field(default="", max_length=1200)
    assistant_outcome: str = Field(default="", max_length=1200)
    terminal_state: Literal["completed", "waiting_input", "waiting_confirmation", "failed"]


class TaskResultPayload(_Payload):
    plan_id: str = Field(min_length=1, max_length=255)
    task_entity_id: str = Field(min_length=1, max_length=255)
    outcome: Literal["completed", "unfulfillable", "blocked", "failed"]
    safe_summary: str = Field(default="", max_length=600)
    artifact_ids: list[str] = Field(default_factory=list, max_length=10)
    source_run_id: str = Field(default="", max_length=255)


_PAYLOAD_MODELS: dict[str, type[_Payload]] = {
    "scope": ScopePayload, "goal": GoalPayload, "term_binding": TermBindingPayload,
    "artifact_ref": ArtifactPayload, "open_loop": OpenLoopPayload,
    "decision": DecisionPayload, "recent_anchor": RecentAnchorPayload,
    "task_result_ref": TaskResultPayload,
}


class ChatContextOperation(BaseModel):
    action: ChatContextAction
    kind: ChatContextKind
    item_key: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list, max_length=4)
    expected_revision: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)
    expires_at: Optional[datetime] = None

    @field_validator("source_ids")
    @classmethod
    def _unique_sources(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(":" not in item or len(item) > 300 for item in cleaned):
            raise ValueError("source_ids must be bounded typed references")
        return cleaned

    def validated_payload(self) -> dict[str, Any]:
        if not self.source_ids:
            raise ValueError("context mutation requires provenance")
        if self.action in {"close", "expire", "supersede"}:
            if self.payload:
                raise ValueError(f"{self.action} operation must not contain a payload")
            return {}
        return _PAYLOAD_MODELS[self.kind].model_validate(self.payload).model_dump(mode="json")


class ChatContextSnapshot(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    chat_id: str
    sandbox_branch_id: Optional[str] = None
    revision: int = 0
    updated_through_turn_id: Optional[str] = None
    focus: Optional[ScopePayload] = None
    active_goal: Optional[GoalPayload] = None
    term_bindings: list[TermBindingPayload] = Field(default_factory=list)
    artifacts: list[ArtifactPayload] = Field(default_factory=list)
    open_loops: list[OpenLoopPayload] = Field(default_factory=list)
    decisions: list[DecisionPayload] = Field(default_factory=list)
    recent_anchor: Optional[RecentAnchorPayload] = None
    task_result_refs: list[TaskResultPayload] = Field(default_factory=list)
    uncertainties: list[dict[str, str]] = Field(default_factory=list, max_length=5)


class ChatContextApplyReceipt(BaseModel):
    revision: int
    applied_count: int = 0
    skipped_count: int = 0
    degradation_codes: list[str] = Field(default_factory=list)
