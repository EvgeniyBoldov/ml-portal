"""Canonical, safety-oriented content contracts for semantic memory."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


MAX_CONTENT_CHARS = 12_000
MAX_LIST_ITEMS = 32
MAX_PROCEDURE_STEPS = 20
MAX_TEXT_CHARS = 500
NORMATIVE_ITEM_TYPES = frozenset({"rule", "constraint", "procedure", "decision"})


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _texts(values: list[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _text(value)
        if len(cleaned) > MAX_TEXT_CHARS:
            raise ValueError("list item exceeds maximum length")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


class _ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> Any:
        return _text(value) if isinstance(value, str) else value


class ProcedureStep(_ContentModel):
    instruction: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    expected_result: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    confirmation_required: bool


class ProcedureRollback(_ContentModel):
    mode: Literal["steps", "not_applicable"]
    steps: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    reason: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)

    @field_validator("steps")
    @classmethod
    def _normalize_steps(cls, value: list[object]) -> list[str]:
        return _texts(value)

    @model_validator(mode="after")
    def _validate_mode(self) -> "ProcedureRollback":
        if self.mode == "steps" and not self.steps:
            raise ValueError("rollback.steps is required when mode=steps")
        if self.mode == "not_applicable" and not self.reason:
            raise ValueError("rollback.reason is required when mode=not_applicable")
        return self


class ProcedureContent(_ContentModel):
    goal: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    applicability_conditions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    required_approvals: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    prechecks: list[str] = Field(min_length=1, max_length=MAX_LIST_ITEMS)
    steps: list[ProcedureStep] = Field(min_length=1, max_length=MAX_PROCEDURE_STEPS)
    verification: list[str] = Field(min_length=1, max_length=MAX_LIST_ITEMS)
    rollback: ProcedureRollback
    exceptions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @field_validator("applicability_conditions", "required_approvals", "prechecks", "verification", "exceptions")
    @classmethod
    def _normalize_lists(cls, value: list[object]) -> list[str]:
        return _texts(value)

    @model_validator(mode="after")
    def _nonempty_required_lists(self) -> "ProcedureContent":
        if not self.prechecks or not self.verification:
            raise ValueError("procedure prechecks and verification must be non-empty")
        return self

    def canonical(self) -> dict[str, Any]:
        result = self.model_dump(mode="json")
        result["steps"] = [
            {"order": index, **step}
            for index, step in enumerate(result["steps"], start=1)
        ]
        return result


class RuleContent(_ContentModel):
    statement: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    effect: Literal["require", "forbid", "allow"]
    conditions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    required_approvals: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    required_checks: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    exceptions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    consequences: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @field_validator("conditions", "required_approvals", "required_checks", "exceptions", "consequences")
    @classmethod
    def _normalize_lists(cls, value: list[object]) -> list[str]:
        return _texts(value)


class ConstraintContent(_ContentModel):
    statement: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    conditions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    limits: list[str] = Field(min_length=1, max_length=MAX_LIST_ITEMS)
    exceptions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    consequences: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @field_validator("conditions", "limits", "exceptions", "consequences")
    @classmethod
    def _normalize_lists(cls, value: list[object]) -> list[str]:
        return _texts(value)

    @model_validator(mode="after")
    def _nonempty_limits(self) -> "ConstraintContent":
        if not self.limits:
            raise ValueError("constraint limits must be non-empty")
        return self


class DecisionContent(_ContentModel):
    decision: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    conditions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    rationale: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    consequences: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @field_validator("conditions", "rationale", "consequences")
    @classmethod
    def _normalize_lists(cls, value: list[object]) -> list[str]:
        return _texts(value)


class TermContent(_ContentModel):
    definition: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class DescriptionContent(_ContentModel):
    summary: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    details: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @field_validator("details")
    @classmethod
    def _normalize_lists(cls, value: list[object]) -> list[str]:
        return _texts(value)


class RelationshipContent(_ContentModel):
    summary: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


_MODELS: dict[str, type[_ContentModel]] = {
    "term": TermContent,
    "description": DescriptionContent,
    "relationship": RelationshipContent,
    "rule": RuleContent,
    "constraint": ConstraintContent,
    "procedure": ProcedureContent,
    "decision": DecisionContent,
}


def normalize_memory_content(item_type: str, content: object) -> dict[str, Any]:
    """Validate and canonicalize normative content; pass other types through."""
    kind = str(item_type or "").strip().lower()
    if not isinstance(content, dict):
        raise ValueError("memory content must be an object")
    model = _MODELS.get(kind)
    if model is None:
        return dict(content)
    try:
        parsed = model.model_validate(content)
    except ValidationError as exc:
        raise ValueError(exc.errors(include_url=False)[0]["msg"]) from exc
    result = parsed.canonical() if isinstance(parsed, ProcedureContent) else parsed.model_dump(mode="json")
    if len(json.dumps(result, ensure_ascii=False, sort_keys=True)) > MAX_CONTENT_CHARS:
        raise ValueError("memory content exceeds maximum size")
    return result


def content_contract_error(item_type: str, content: object) -> str | None:
    try:
        normalize_memory_content(item_type, content)
    except ValueError as exc:
        return str(exc)
    return None
