from __future__ import annotations

from types import SimpleNamespace

from app.agents import RuntimeEventType
from app.services.chat_event_mapper import ChatEventMapper


class TestChatEventMapper:
    def test_maps_tool_call_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.OPERATION_CALL,
            data={"operation": "rag.search", "call_id": "1", "arguments": {"q": "hi"}},
        )

        result = mapper.map_runtime_event(event)

        assert result == {
            "type": "operation_call",
            "operation": "rag.search",
            "call_id": "1",
            "arguments": {"q": "hi"},
        }

    def test_returns_none_for_unhandled_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(type=RuntimeEventType.FINAL, data={"content": "done"})

        assert mapper.map_runtime_event(event) is None

    def test_maps_planner_action_with_modern_and_legacy_fields(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.PLANNER_ACTION,
            data={
                "iteration": 3,
                "action_type": "agent_call",
                "step_type": "call_agent",
                "agent_slug": "netbox",
                "phase_id": "search",
                "phase_title": "Поиск",
                "why": "Нужны данные из NetBox",
            },
        )

        result = mapper.map_runtime_event(event)

        assert result is not None
        assert result["type"] == "planner_action"
        assert result["agent_slug"] == "netbox"
        assert result["step_type"] == "call_agent"
        assert result["tool_slug"] == "netbox"
        assert result["op"] == "call_agent"
