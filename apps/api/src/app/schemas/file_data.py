"""Pydantic contracts for document-local data operations."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FileDataInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    artifact_id: UUID


class FileDataReadInput(FileDataInput):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10000, ge=1, le=100000)
    representation_id: UUID | None = None


class FileDataPrepareInput(FileDataInput):
    backend: Literal["vector", "longmemory"] = "vector"


class FileDataSearchInput(FileDataInput):
    query: str = Field(min_length=1, max_length=4000)
    backend: Literal["auto", "vector", "longmemory"] = "auto"
    limit: int = Field(default=5, ge=1, le=20)


class FileDataReadOutput(BaseModel):
    artifact_id: str
    representation_id: str
    source_fingerprint: str
    source_complete: bool
    content: str
    offset: int
    next_offset: int | None
    total_chars: int
    read_complete: bool
    status: str
    warnings: list[str] = Field(default_factory=list)


class FileDataPrepareOutput(BaseModel):
    artifact_id: str
    representation_id: str
    source_fingerprint: str
    backend: Literal["vector", "longmemory"]
    status: Literal["ready"] = "ready"
    chunk_count: int = Field(ge=1)
    expires_at: int
    reused: bool


class FileDataHit(BaseModel):
    artifact_id: str
    representation_id: str
    chunk_id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    score: float
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileDataSearchOutput(BaseModel):
    artifact_id: str
    representation_id: str
    source_fingerprint: str
    source_complete: bool
    backend: Literal["vector", "longmemory"]
    status: Literal["ready"] = "ready"
    indexed_chunks: int = Field(ge=1)
    hits: list[FileDataHit]
    returned_count: int
    response_truncated: bool = False
