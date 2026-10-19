"""Public document LongMemory inspection and command receipt."""
from typing import Any

from pydantic import BaseModel, Field


class LongMemoryDocumentInspection(BaseModel):
    document_id: str
    operation_id: str | None = None
    status: str
    action: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    worker: dict[str, Any] = Field(default_factory=dict)


class LongMemoryDocumentReceipt(BaseModel):
    document_id: str
    operation_id: str
    status: str
