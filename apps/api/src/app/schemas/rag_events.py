"""
RAG SSE Event Contract — единый источник правды для SSE событий RAG pipeline.

Canonical event types:
  - status_update        — stage-level status change (extract/normalize/chunk/embed/index)
  - status_initialized   — document statuses initialized (after upload)
  - ingest_started       — ingest pipeline started
  - aggregate_update     — aggregate status recalculated
  - document_archived    — document archived
  - document_unarchived  — document unarchived

All events use `document_id` as the canonical document identifier.
The legacy `doc_id` alias is kept for backward compatibility but should not
be used in new code.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RAGSSEEventType(str, Enum):
    """Canonical RAG SSE event types."""
    STATUS_UPDATE = "status_update"
    STATUS_INITIALIZED = "status_initialized"
    INGEST_STARTED = "ingest_started"
    AGGREGATE_UPDATE = "aggregate_update"
    DOCUMENT_ARCHIVED = "document_archived"
    DOCUMENT_UNARCHIVED = "document_unarchived"


# ── Payload schemas ────────────────────────────────────────────────

class RAGBasePayload(BaseModel):
    """Common fields for all RAG SSE events."""
    document_id: str
    tenant_id: str
    timestamp: str


class RAGStatusUpdatePayload(RAGBasePayload):
    """Stage-level status change."""
    event_type: str = RAGSSEEventType.STATUS_UPDATE.value
    stage: str
    status: str
    error: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None


class RAGStatusInitializedPayload(RAGBasePayload):
    """Document statuses initialized (after upload)."""
    event_type: str = RAGSSEEventType.STATUS_INITIALIZED.value
    user_id: Optional[str] = None


class RAGIngestStartedPayload(RAGBasePayload):
    """Ingest pipeline started."""
    event_type: str = RAGSSEEventType.INGEST_STARTED.value
    user_id: Optional[str] = None


class RAGAggregateUpdatePayload(RAGBasePayload):
    """Aggregate status recalculated."""
    event_type: str = RAGSSEEventType.AGGREGATE_UPDATE.value
    agg_status: str
    agg_details: Dict[str, Any] = Field(default_factory=dict)


class RAGDocumentArchivedPayload(RAGBasePayload):
    """Document archived or unarchived."""
    event_type: str  # document_archived or document_unarchived
    archived: bool


# ── Payload type mapping ───────────────────────────────────────────

EVENT_PAYLOAD_MAP = {
    RAGSSEEventType.STATUS_UPDATE: RAGStatusUpdatePayload,
    RAGSSEEventType.STATUS_INITIALIZED: RAGStatusInitializedPayload,
    RAGSSEEventType.INGEST_STARTED: RAGIngestStartedPayload,
    RAGSSEEventType.AGGREGATE_UPDATE: RAGAggregateUpdatePayload,
    RAGSSEEventType.DOCUMENT_ARCHIVED: RAGDocumentArchivedPayload,
    RAGSSEEventType.DOCUMENT_UNARCHIVED: RAGDocumentArchivedPayload,
}


def build_rag_event(payload: RAGBasePayload) -> Dict[str, Any]:
    """Serialize RAG event payload to transport dict.

    Adds backward-compatible `doc_id` alias for `document_id`.
    """
    data = payload.model_dump(mode="json")
    # Legacy alias for frontend compatibility
    data["doc_id"] = data["document_id"]
    return data
