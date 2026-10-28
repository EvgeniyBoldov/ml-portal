import json

from app.services.chat_router_event_mapper import map_service_event_to_sse


def _payload(frame: str) -> dict:
    return json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))


def test_stage_exposes_only_safe_projection():
    frame = map_service_event_to_sse({"type": "stage", "activity": {
        "run_id": "run-1", "stage": "executing", "action": "tool_call",
        "description": "Выполняю", "outcome": None, "arguments": {"secret": 1},
    }})
    assert frame is not None
    assert _payload(frame)["activity"] == {
        "run_id": "run-1", "stage": "executing", "action": "tool_call",
        "description": "Выполняю", "outcome": None,
    }


def test_attach_snapshot_is_state_not_a_new_run_started_event():
    frame = map_service_event_to_sse({
        "type": "state", "run_id": "run-1", "status": "running", "stage": "planning",
    })
    assert frame is not None and frame.startswith("event: state\n")
    assert _payload(frame)["status"] == "running"


def test_legacy_observability_events_do_not_cross_chat_boundary():
    assert map_service_event_to_sse({"type": "tool_call", "arguments": {"secret": 1}}) is None
    assert map_service_event_to_sse({"type": "planner_action"}) is None


def test_stop_is_normalized_to_single_pause_event():
    frame = map_service_event_to_sse({"type": "stop", "run_id": "run-1", "reason": "waiting_input", "question": "Какая сеть?"})
    assert frame is not None and frame.startswith("event: pause\n")
    assert _payload(frame)["action"]["kind"] == "input"
    assert _payload(frame)["status"] == "waiting_input"


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
