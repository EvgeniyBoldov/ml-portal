from __future__ import annotations

from types import SimpleNamespace

from app.runtime.events import RuntimeEventType
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
            "orchestration_envelope": None,
        }

    def test_returns_none_for_unhandled_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(type=RuntimeEventType.FINAL, data={"content": "done"})

        assert mapper.map_runtime_event(event) is None

    def test_maps_planner_step_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.PLANNER_STEP,
            data={
                "iteration": 3,
                "kind": "call_agent",
                "agent_slug": "netbox",
                "phase_id": "search",
                "phase_title": "Поиск",
                "rationale": "Нужны данные из NetBox",
                "risk": "low",
            },
        )

        result = mapper.map_runtime_event(event)

        assert result is not None
        assert result["type"] == "planner_action"
        assert result["agent_slug"] == "netbox"
        assert result["kind"] == "call_agent"
        assert result["action_type"] == "agent_call"
        assert result["step_type"] == "call_agent"
        assert result["rationale"] == "Нужны данные из NetBox"
        assert result["why"] == "Нужны данные из NetBox"
        assert result["contract_version"] == 1

    def test_maps_error_event_with_code_and_details(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.ERROR,
            data={
                "error": "failed",
                "error_code": "operation_unavailable",
                "retryable": False,
            },
        )
        result = mapper.map_runtime_event(event)
        assert result is not None
        assert result["type"] == "error"
        assert result["code"] == "operation_unavailable"
        assert result["recoverable"] is False
        assert result["details"]["retryable"] is False
