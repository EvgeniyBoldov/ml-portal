from __future__ import annotations

from types import SimpleNamespace

from app.agents import RuntimeEventType
from app.services.chat_event_mapper import ChatEventMapper


class TestChatEventMapper:
    def test_maps_tool_call_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.TOOL_CALL,
            data={"tool": "rag.search", "call_id": "1", "arguments": {"q": "hi"}},
        )

        result = mapper.map_runtime_event(event)

        assert result == {
            "type": "tool_call",
            "tool": "rag.search",
            "call_id": "1",
            "arguments": {"q": "hi"},
        }

    def test_returns_none_for_unhandled_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(type=RuntimeEventType.FINAL, data={"content": "done"})

        assert mapper.map_runtime_event(event) is None
