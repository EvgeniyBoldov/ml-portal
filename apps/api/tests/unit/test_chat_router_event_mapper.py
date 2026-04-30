from __future__ import annotations

import json

from app.services.chat_router_event_mapper import map_service_event_to_sse


def _extract_payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line[len("data: "):])


def test_planner_action_payload_contains_modern_and_legacy_fields():
    frame = map_service_event_to_sse(
        {
            "type": "planner_action",
            "iteration": 2,
            "kind": "call_agent",
            "rationale": "Нужно получить устройства",
            "risk": "low",
            "agent_slug": "netbox",
            "phase_id": "collect",
            "phase_title": "Сбор данных",
        }
    )
    assert frame is not None
    assert "event: planner_action" in frame
    payload = _extract_payload(frame)

    assert payload["iteration"] == 2
    assert payload["action_type"] == "agent_call"
    assert payload["kind"] == "call_agent"
    assert payload["rationale"] == "Нужно получить устройства"
    assert payload["risk"] == "low"
    assert payload["contract_version"] == 1
    assert payload["step_type"] == "call_agent"
    assert payload["agent_slug"] == "netbox"
    assert payload["phase_id"] == "collect"
    assert payload["phase_title"] == "Сбор данных"
    assert payload["why"] == "Нужно получить устройства"
    assert payload["tool_slug"] == "netbox"
    assert payload["op"] == "call_agent"
