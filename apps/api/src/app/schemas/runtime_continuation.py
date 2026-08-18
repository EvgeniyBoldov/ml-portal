"""Public, transport-neutral contract for resuming a paused runtime run."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RuntimeResumeAction(str, Enum):
    INPUT = "input"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class RuntimeResumeRequest(BaseModel):
    """One HITL action for either chat or sandbox resume endpoints."""

    action: RuntimeResumeAction
    input: Optional[str] = None
