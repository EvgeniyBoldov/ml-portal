"""Public, transport-neutral contract for resuming a paused runtime run."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class RuntimeResumeAction(str, Enum):
    INPUT = "input"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class RuntimeResumeRequest(BaseModel):
    """One HITL action for either chat or sandbox resume endpoints."""

    action: RuntimeResumeAction
    input: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_input_action(self) -> "RuntimeResumeRequest":
        if self.action is not RuntimeResumeAction.INPUT and str(self.input or "").strip():
            raise ValueError("input is allowed only for action='input'")
        return self
