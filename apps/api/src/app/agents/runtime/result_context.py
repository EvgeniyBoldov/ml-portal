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
    tool: Literal["result.read", "result.describe", "result.aggregate", "result.find"] = "result.read"
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
    input_result_id: str | None = None
    input_revision: int | None = None
    offset: int | None = None
    limit: int | None = None
    page_may_have_more: bool | None = None
    query_complete: bool | None = None
    fields: list[str] | None = None
    read_complete: bool | None = None
    next_offset: int | None = None
    path: str | None = None
    text_offset: int | None = None
    text_limit: int | None = None
    next_text_offset: int | None = None
    child_offset: int | None = None
    child_limit: int | None = None
    next_child_offset: int | None = None
    recovery_reason: str | None = None
    delivery: Literal["direct", "stored"] | None = None
    row_count: int | None = None
    source_total: int | None = None
    snapshot_only: bool | None = None
    imported_from: dict[str, Any] | None = None
    view: Literal["auto", "value", "children"] | None = None


class ResultUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["unavailable"] = "unavailable"
    reason: str
    message: str


class ResultObservation(BaseModel):
    """Bounded receipt describing exactly which stored result page was observed."""

    model_config = ConfigDict(extra="forbid")
    result_id: str | None = None
    revision: int | None = None
    offset: int | None = None
    limit: int | None = None
    fields: list[str] | None = None
    read_complete: bool | None = None
    next_offset: int | None = None
    source_complete: bool | None = None
    source_total: int | None = None
    query_complete: bool | None = None
    input_result_id: str | None = None
    input_revision: int | None = None
    page_may_have_more: bool | None = None
    path: str | None = None
    text_offset: int | None = None
    text_limit: int | None = None
    next_text_offset: int | None = None
    child_offset: int | None = None
    child_limit: int | None = None
    next_child_offset: int | None = None
    recovery_reason: str | None = None
    delivery: Literal["direct", "stored"] | None = None
    row_count: int | None = None
    view: Literal["auto", "value", "children"] | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ResultObservation":
        """Keep only the stable observation contract, preserving explicit unknowns."""
        return cls.model_validate({key: value[key] for key in cls.model_fields if key in value})
