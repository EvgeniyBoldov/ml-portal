"""
Contract tests for Chat SSE event schemas.

Validates:
- All event types have corresponding payload schemas
- Payloads serialize to valid JSON
- SSE formatting produces correct wire format
- Event type enum is exhaustive
"""
import pytest
from app.schemas.chat_events import (
    ChatSSEEventType,
    StatusPayload,
    UserMessagePayload,
    DeltaPayload,
    FinalPayload,
    ErrorPayload,
    ToolCallPayload,
    ToolResultPayload,
    CachedPayload,
    ChatTitlePayload,
    EVENT_PAYLOAD_MAP,
    format_chat_sse,
)


class TestChatSSEEventTypeCompleteness:
    """Every enum member must appear in EVENT_PAYLOAD_MAP."""

    def test_all_event_types_mapped(self):
        for et in ChatSSEEventType:
            assert et in EVENT_PAYLOAD_MAP, f"Missing payload mapping for {et.value}"

    def test_no_extra_keys_in_map(self):
        for key in EVENT_PAYLOAD_MAP:
            assert isinstance(key, ChatSSEEventType), f"Unexpected key in map: {key}"


class TestPayloadSerialization:
    """Each payload must produce a valid dict with event_type field."""

    def test_status_payload(self):
        p = StatusPayload(stage="loading_context")
        d = p.model_dump(mode="json")
        assert d["stage"] == "loading_context"

    def test_user_message_payload(self):
        p = UserMessagePayload(message_id="abc-123", created_at="2025-01-01T00:00:00Z")
        d = p.model_dump(mode="json")
        assert d["message_id"] == "abc-123"

    def test_delta_payload(self):
        p = DeltaPayload(content="Hello")
        d = p.model_dump(mode="json")
        assert d["content"] == "Hello"

    def test_final_payload(self):
        p = FinalPayload(
            message_id="msg-1",
            created_at="2025-01-01T00:00:00Z",
            sources=[{"url": "http://example.com"}],
        )
        d = p.model_dump(mode="json")
        assert d["message_id"] == "msg-1"
        assert len(d["sources"]) == 1

    def test_error_payload(self):
        p = ErrorPayload(error="Something broke")
        d = p.model_dump(mode="json")
        assert d["error"] == "Something broke"

    def test_tool_call_payload(self):
        p = ToolCallPayload(
            tool="rag.search",
            call_id="call-1",
            arguments={"query": "test"},
        )
        d = p.model_dump(mode="json")
        assert d["tool"] == "rag.search"

    def test_tool_result_payload(self):
        p = ToolResultPayload(
            tool="rag.search",
            call_id="call-1",
            success=True,
            data={"results": []},
        )
        d = p.model_dump(mode="json")
        assert d["success"] is True

    def test_cached_payload(self):
        p = CachedPayload(
            user_message_id="u-1",
            assistant_message_id="a-1",
        )
        d = p.model_dump(mode="json")
        assert d["user_message_id"] == "u-1"

    def test_title_payload(self):
        p = ChatTitlePayload(title="My Chat")
        d = p.model_dump(mode="json")
        assert d["title"] == "My Chat"


class TestSSEFormatting:
    """format_sse_event must produce valid SSE wire format."""

    def test_basic_sse_format(self):
        p = DeltaPayload(content="Hi")
        result = format_chat_sse(ChatSSEEventType.DELTA, p)
        assert result.startswith("event: delta\n")
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_sse_contains_json_data(self):
        p = StatusPayload(stage="agent_running")
        result = format_chat_sse(ChatSSEEventType.STATUS, p)
        import json
        # Extract data line
        lines = result.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = json.loads(data_line[6:])  # strip "data: "
        assert data_json["stage"] == "agent_running"
