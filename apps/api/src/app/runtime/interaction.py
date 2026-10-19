"""Runtime-owned user interactions and requester-local continuation checkpoints."""
from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, model_validator


class InteractionQuestion(BaseModel):
    """The model may ask a question; identity and routing belong to runtime."""
    question: str = Field(min_length=1, max_length=4000)
    response_type: Literal["text", "boolean"] = "text"
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class InteractionRequester(BaseModel):
    stage: Literal["turn_preflight", "planner", "agent"]
    entity_id: str = Field(min_length=1)
    plan_id: str | None = None
    task_id: str | None = None
    agent_slug: str | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_owner(self) -> "InteractionRequester":
        if self.stage == "agent" and not self.task_id:
            raise ValueError("agent interaction requires its task identity")
        if self.stage != "agent" and self.task_id is not None:
            raise ValueError("only an agent interaction may target a task")
        return self


class RuntimeInteraction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    question: str = Field(min_length=1)
    response_schema: dict[str, Any]
    requester: InteractionRequester
    # Private execution state is persisted but never sent to the chat client.
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    operation: dict[str, Any] | None = None
    model_config = {"extra": "forbid"}

    @classmethod
    def create(cls, question: InteractionQuestion, requester: InteractionRequester,
               *, checkpoint: dict[str, Any] | None = None,
               operation: dict[str, Any] | None = None) -> "RuntimeInteraction":
        schema = ({"type": "boolean"} if question.response_type == "boolean"
                  else {"type": "string", "minLength": 1, "maxLength": 4000, "pattern": r"\S"})
        return cls(question=question.question, response_schema=schema, requester=requester,
                   checkpoint=checkpoint or {}, operation=operation)

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"checkpoint", "operation"})

    def validate_response(self, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
        if not Draft202012Validator(self.response_schema).is_valid(value):
            raise ValueError("Ответ не соответствует формату текущего вопроса")
        return value

    @property
    def reason(self) -> str:
        return "waiting_confirmation" if self.response_schema.get("type") == "boolean" else "waiting_input"


class InteractionRequired(RuntimeError):
    def __init__(self, interaction: RuntimeInteraction) -> None:
        self.interaction = interaction
        super().__init__(interaction.question)


def interaction_from_context(context: Any) -> RuntimeInteraction | None:
    value = context.get("interaction") if isinstance(context, dict) else None
    return RuntimeInteraction.model_validate(value) if isinstance(value, dict) else None


def interaction_history(pauses: list[dict[str, Any]], *, stage: str,
                        task_id: str | None = None) -> list[dict[str, Any]]:
    result = []
    for pause in pauses:
        payload = pause.get("payload") or {}
        raw = payload.get("interaction")
        if not isinstance(raw, dict) or "response" not in payload:
            continue
        interaction = RuntimeInteraction.model_validate(raw)
        if interaction.requester.stage == stage and interaction.requester.task_id == task_id:
            result.append({"interaction": interaction.model_dump(mode="json"), "response": payload["response"]})
    return result


def require_interaction_allowed(ctx: Any, stage: str, agent_slug: str | None = None) -> None:
    policy = (getattr(ctx, "extra", {}) or {}).get("interaction_policy") or {}
    allowed = policy.get(stage, True)
    if isinstance(allowed, dict):
        allowed = allowed.get(agent_slug, allowed.get("default", True))
    if allowed is False or (getattr(ctx, "extra", {}) or {}).get("shadow_execution"):
        raise ValueError(f"User interactions are disabled for {stage}")
