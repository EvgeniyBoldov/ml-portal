import json

from app.schemas.chat_events import (
    ChatSSEEventType, DeltaPayload, PausePayload, RuntimeProgressPayload,
    StatusPayload, format_chat_sse,
)


def test_chat_contract_contains_only_public_transport_events():
    assert {event.value for event in ChatSSEEventType} == {
        "user_message", "chat_title", "status", "delta", "pause", "final", "cached", "error",
    }


def test_status_requires_safe_runtime_progress():
    payload = StatusPayload(progress=RuntimeProgressPayload(
        run_id="run-1", phase="execution", kind="tool_call", description="Выполняю задачу",
    ))
    assert payload.model_dump(mode="json")["stage"] == "runtime_progress"


def test_pause_and_delta_use_valid_sse_frames():
    pause = PausePayload(run_id="run-1", reason="waiting_input", contract_version=1)
    frame = format_chat_sse(ChatSSEEventType.PAUSE, pause)
    assert json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))["reason"] == "waiting_input"
    assert format_chat_sse(ChatSSEEventType.DELTA, DeltaPayload(content="one\ntwo")).count("data:") == 2
