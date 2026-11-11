"""Typed model-facing result receipts for runtime tool replies."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    complete: bool | None
    total: int | None
    stored_count: int


class ResultNextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["result.read", "result.describe"] = "result.read"
    arguments: dict[str, Any]
    message: str


class ModelResultView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "already_completed"] = "ready"
    result_id: str
    revision: int
    source_coverage: SourceCoverage
    records: Any | None = None
    next_action: ResultNextAction | None = None


class ResultUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["unavailable"] = "unavailable"
    reason: str
    message: str
