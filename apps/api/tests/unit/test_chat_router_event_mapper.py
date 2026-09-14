import json

from app.services.chat_router_event_mapper import map_service_event_to_sse


def _payload(frame: str) -> dict:
    return json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))


def test_progress_exposes_only_safe_projection():
    frame = map_service_event_to_sse({"type": "status", "stage": "runtime_progress", "progress": {
        "run_id": "run-1", "phase": "execution", "kind": "tool_call", "description": "Выполняю", "arguments": {"secret": 1},
    }})
    assert frame is not None
    assert _payload(frame)["progress"] == {"run_id": "run-1", "phase": "execution", "kind": "tool_call", "description": "Выполняю", "status": None}


def test_legacy_observability_events_do_not_cross_chat_boundary():
    assert map_service_event_to_sse({"type": "tool_call", "arguments": {"secret": 1}}) is None
    assert map_service_event_to_sse({"type": "planner_action"}) is None


def test_stop_is_normalized_to_single_pause_event():
    frame = map_service_event_to_sse({"type": "stop", "run_id": "run-1", "reason": "waiting_input", "question": "Какая сеть?"})
    assert frame is not None and frame.startswith("event: pause\n")
    assert _payload(frame)["action"]["kind"] == "input"


def test_confirmation_pause_keeps_question_for_chat_header():
    frame = map_service_event_to_sse({
        "type": "stop",
        "run_id": "run-1",
        "reason": "waiting_confirmation",
        "message": "Подтвердить публикацию изменений?",
        "action": {"operation_fingerprint": "fingerprint-1", "risk_level": "write"},
    })
    assert frame is not None
    payload = _payload(frame)
    assert payload["action"]["kind"] == "confirm"
    assert payload["action"]["message"] == "Подтвердить публикацию изменений?"
    assert payload["context"]["message"] == "Подтвердить публикацию изменений?"


def test_failed_stop_is_not_exposed_as_a_resumable_pause():
    frame = map_service_event_to_sse({
        "type": "stop",
        "run_id": "run-1",
        "reason": "failed",
        "message": "TurnPreflight unavailable; planner was not invoked",
    })

    assert frame is None
