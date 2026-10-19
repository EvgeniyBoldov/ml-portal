"""Public, transport-neutral contract for resuming a paused runtime run."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class RuntimeResumeAction(str, Enum):
    ANSWER = "answer"
    INPUT = "input"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class RuntimeResumeRequest(BaseModel):
    """One HITL action for either chat or sandbox resume endpoints."""

    action: RuntimeResumeAction
    input: Optional[str] = Field(default=None, max_length=4000)
    pause_id: Optional[str] = Field(default=None, max_length=64)
    response: Any = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_input_action(self) -> "RuntimeResumeRequest":
        if self.action is RuntimeResumeAction.ANSWER and "response" not in self.model_fields_set:
            raise ValueError("response is required for action='answer'")
        if self.action is not RuntimeResumeAction.INPUT and str(self.input or "").strip():
            raise ValueError("input is allowed only for action='input'")
        return self
