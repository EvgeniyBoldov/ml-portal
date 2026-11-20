"""Canonical memory-search arguments shared by agents and root routing."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HippoMemorySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=12)


class HippoMemoryPassage(BaseModel):
    kind: Literal["document_passage"] = "document_passage"
    scope_slug: str
    subject: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_references: list[dict[str, Any]] = Field(default_factory=list)


class HippoMemoryScopeResult(BaseModel):
    scope_slug: str
    status: Literal["completed", "failed"]
    success: bool
    index: str | None = None
    document_count: int = 0
    items: list[HippoMemoryPassage] = Field(default_factory=list)
    count: int = 0
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None


class HippoMemorySearchResult(BaseModel):
    backend: Literal["hipporag"] = "hipporag"
    groups: list[HippoMemoryScopeResult] = Field(default_factory=list)
    group_count: int
    partial: bool

