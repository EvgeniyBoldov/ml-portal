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

    def test_maps_planner_decision_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.PLANNER_DECISION,
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
        assert result["type"] == "planner_decision"
        assert result["agent_slug"] == "netbox"
        assert result["kind"] == "call_agent"
        assert result["rationale"] == "Нужны данные из NetBox"
        assert result["contract_version"] == 1

    def test_maps_error_event_with_code_and_details(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.ERROR,
            data={
                "error": "Sub-agent net.enginer failed: traceback ...",
                "error_code": "operation_unavailable",
                "retryable": False,
            },
        )
        result = mapper.map_runtime_event(event)
        assert result is not None
        assert result["type"] == "error"
        assert result["code"] == "operation_unavailable"
        assert result["recoverable"] is False
        assert result["error"] == "Во время выполнения запроса возникли проблемы. Сообщите ран-администратору."
        assert result["details"]["retryable"] is False

    def test_llm_mapping_uses_whitelist_only(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.LLM_TURN,
            data={
                "llm_call_id": "c1",
                "model": "gpt-test",
                "messages": [{"role": "system", "content": "hidden"}],
                "system_prompt": "secret",
                "response_length": 10,
            },
        )
        result = mapper.map_runtime_event(event)
        assert result is not None
        assert result["type"] == "llm_turn"
        assert result["llm_call_id"] == "c1"
        assert result["model"] == "gpt-test"
        assert result["response_length"] == 10
        assert "messages" not in result
        assert "system_prompt" not in result

    def test_legacy_llm_event_is_not_mapped(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type="llm_request",
            data={"llm_call_id": "legacy-1", "model": "gpt-test"},
        )
        assert mapper.map_runtime_event(event) is None

    def test_maps_llm_turn_event(self):
        mapper = ChatEventMapper()
        event = SimpleNamespace(
            type=RuntimeEventType.LLM_TURN,
            data={
                "llm_call_id": "turn-1",
                "model": "gpt-test",
                "tokens_in": 100,
                "tokens_out": 50,
                "tokens_total": 150,
                "duration_ms": 320,
                "actor_type": "planner",
                "actor_entity_id": "planner-1",
                "messages": [{"role": "system", "content": "hidden"}],
            },
        )
        result = mapper.map_runtime_event(event)
        assert result is not None
        assert result["type"] == "llm_turn"
        assert result["llm_call_id"] == "turn-1"
        assert result["tokens_total"] == 150
        assert result["actor_type"] == "planner"
        assert result["actor_entity_id"] == "planner-1"
        assert "messages" not in result
