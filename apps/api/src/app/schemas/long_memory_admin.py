"""Compact admin projections for the native LongMemory corpus."""
from datetime import datetime

from pydantic import BaseModel, Field


class LongMemoryAdminDocument(BaseModel):
    document_id: str
    title: str
    filename: str
    status: str
    action: str | None = None
    scope_keys: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    updated_at: datetime | None = None


class LongMemoryAdminDocumentPage(BaseModel):
    items: list[LongMemoryAdminDocument]
    total: int
    limit: int
    offset: int


class LongMemoryAdminGraph(BaseModel):
    scope_key: str
    status: str


class LongMemoryAdminDocumentDetail(LongMemoryAdminDocument):
    operation_id: str | None = None
    generation: int | None = None
    graphs: list[LongMemoryAdminGraph] = Field(default_factory=list)
    triples_count: int = 0


class LongMemoryTriple(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    source_start: int | None = None
    source_end: int | None = None


class LongMemoryTriplePage(BaseModel):
    document_id: str
    items: list[LongMemoryTriple] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class LongMemorySearchPreviewRequest(BaseModel):
    scope_key: str = Field(min_length=1, max_length=180, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)


class LongMemorySearchPreviewHit(BaseModel):
    text: str
    score: float
    document_id: str | None = None
    title: str | None = None
    filename: str | None = None
    start: int | None = None
    end: int | None = None


class LongMemorySearchPreviewResponse(BaseModel):
    scope_key: str
    success: bool
    error: str | None = None
    hits: list[LongMemorySearchPreviewHit] = Field(default_factory=list)
