import json

from app.schemas.chat_events import (
    ChatExecutionStage, ChatLifecycleState, ChatSSEEventType, ChatStatePayload,
    DeltaPayload, PausePayload, RuntimeProgressPayload, StagePayload, format_chat_sse,
)


def test_chat_contract_contains_only_public_transport_events():
    assert {event.value for event in ChatSSEEventType} == {
        "state", "stage", "run_started", "cancelled", "user_message",
        "delta", "pause", "final", "cached", "error",
    }


def test_lifecycle_state_is_separate_from_stage_activity():
    state = ChatStatePayload(run_id="run-1", status=ChatLifecycleState.RUNNING, stage=ChatExecutionStage.EXECUTING)
    activity = StagePayload(activity=RuntimeProgressPayload(
        run_id="run-1", stage=ChatExecutionStage.EXECUTING,
        action="tool_call", description="Выполняю задачу",
    ))
    assert state.model_dump(mode="json")["status"] == "running"
    assert activity.model_dump(mode="json")["activity"]["stage"] == "executing"


def test_pause_and_delta_use_valid_sse_frames():
    pause = PausePayload(
        run_id="run-1", reason="waiting_input",
        status=ChatLifecycleState.WAITING_INPUT, contract_version=1,
    )
    frame = format_chat_sse(ChatSSEEventType.PAUSE, pause)
    assert json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))["reason"] == "waiting_input"
    assert format_chat_sse(ChatSSEEventType.DELTA, DeltaPayload(content="one\ntwo")).count("data:") == 2
