"""
Contract tests for RAG SSE event schemas.

Validates:
- All RAG event types have corresponding payload schemas
- build_rag_event produces backward-compatible doc_id alias
- Payload serialization is correct
- Event type enum is exhaustive
"""
import pytest
from app.schemas.rag_events import (
    RAGSSEEventType,
    RAGStatusUpdatePayload,
    RAGStatusInitializedPayload,
    RAGIngestStartedPayload,
    RAGAggregateUpdatePayload,
    RAGDocumentArchivedPayload,
    EVENT_PAYLOAD_MAP,
    build_rag_event,
)


class TestRAGSSEEventTypeCompleteness:
    """Every enum member must appear in EVENT_PAYLOAD_MAP."""

    def test_all_event_types_mapped(self):
        for et in RAGSSEEventType:
            assert et in EVENT_PAYLOAD_MAP, f"Missing payload mapping for {et.value}"

    def test_no_extra_keys_in_map(self):
        for key in EVENT_PAYLOAD_MAP:
            assert isinstance(key, RAGSSEEventType), f"Unexpected key in map: {key}"


class TestRAGPayloadSerialization:
    """Each RAG payload must produce valid dict with canonical fields."""

    def test_status_update_payload(self):
        p = RAGStatusUpdatePayload(
            document_id="doc-1",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
            stage="extract",
            status="processing",
        )
        d = p.model_dump(mode="json")
        assert d["document_id"] == "doc-1"
        assert d["stage"] == "extract"
        assert d["status"] == "processing"
        assert d["event_type"] == "status_update"

    def test_status_initialized_payload(self):
        p = RAGStatusInitializedPayload(
            document_id="doc-2",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
        )
        d = p.model_dump(mode="json")
        assert d["event_type"] == "status_initialized"

    def test_ingest_started_payload(self):
        p = RAGIngestStartedPayload(
            document_id="doc-3",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
        )
        d = p.model_dump(mode="json")
        assert d["event_type"] == "ingest_started"

    def test_aggregate_update_payload(self):
        p = RAGAggregateUpdatePayload(
            document_id="doc-4",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
            agg_status="ready",
            agg_details={"extract": "completed"},
        )
        d = p.model_dump(mode="json")
        assert d["event_type"] == "aggregate_update"
        assert d["agg_status"] == "ready"

    def test_document_archived_payload(self):
        p = RAGDocumentArchivedPayload(
            document_id="doc-5",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
            event_type="document_archived",
            archived=True,
        )
        d = p.model_dump(mode="json")
        assert d["archived"] is True


class TestBuildRagEvent:
    """build_rag_event must add backward-compatible doc_id alias."""

    def test_doc_id_alias_present(self):
        p = RAGStatusUpdatePayload(
            document_id="doc-99",
            tenant_id="t-1",
            timestamp="2025-01-01T00:00:00Z",
            stage="chunk",
            status="completed",
        )
        event = build_rag_event(p)
        assert event["document_id"] == "doc-99"
        assert event["doc_id"] == "doc-99"

    def test_event_is_json_serializable(self):
        import json
        p = RAGIngestStartedPayload(
            document_id="doc-100",
            tenant_id="t-2",
            timestamp="2025-01-01T00:00:00Z",
        )
        event = build_rag_event(p)
        serialized = json.dumps(event)
        assert "doc-100" in serialized
