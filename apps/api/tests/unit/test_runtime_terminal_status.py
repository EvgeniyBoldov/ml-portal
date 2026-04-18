from __future__ import annotations

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.services.runtime_terminal_status import (
    ContinuationApiStatus,
    ContinuationTerminalStatus,
    continuation_api_status_from_terminal,
    continuation_terminal_from_event,
    RunTerminalStatus,
    normalize_run_status_for_storage,
    planner_terminal_from_event,
)


def test_normalize_run_status_for_storage_passthrough_and_terminal():
    assert normalize_run_status_for_storage("running") == "running"
    assert normalize_run_status_for_storage("resumed") == "resumed"
    assert normalize_run_status_for_storage("cancelled") == "cancelled"
    assert normalize_run_status_for_storage("waiting_input") == "waiting_input"
    assert normalize_run_status_for_storage("waiting_confirmation") == "waiting_confirmation"
    assert normalize_run_status_for_storage("failed") == "failed"
    assert normalize_run_status_for_storage("completed") == "completed"
    assert normalize_run_status_for_storage("max_iters") == "stopped"


def test_planner_terminal_from_event_maps_stop_and_error():
    stop = RuntimeEvent(RuntimeEventType.STOP, {"reason": "waiting_input", "question": "q"})
    status, err = planner_terminal_from_event(stop) or (None, None)
    assert status == RunTerminalStatus.WAITING_INPUT
    assert err == "q"

    fail = RuntimeEvent(RuntimeEventType.ERROR, {"error": "boom"})
    status, err = planner_terminal_from_event(fail) or (None, None)
    assert status == RunTerminalStatus.FAILED
    assert err == "boom"


def test_continuation_terminal_and_api_status_mapping():
    paused, paused_err = continuation_terminal_from_event({"type": "run_paused", "reason": "waiting_input"}) or (None, None)
    assert paused == ContinuationTerminalStatus.PAUSED
    assert paused_err == "waiting_input"
    assert continuation_api_status_from_terminal(paused) == ContinuationApiStatus.RESUMED_PAUSED_AGAIN

    failed, failed_err = continuation_terminal_from_event({"type": "error", "error": "boom"}) or (None, None)
    assert failed == ContinuationTerminalStatus.ERROR
    assert failed_err == "boom"
    assert continuation_api_status_from_terminal(failed) == ContinuationApiStatus.RESUMED_WITH_ERROR

    completed, completed_err = continuation_terminal_from_event({"type": "final", "message_id": "m1"}) or (None, None)
    assert completed == ContinuationTerminalStatus.COMPLETED
    assert completed_err is None
    assert continuation_api_status_from_terminal(completed) == ContinuationApiStatus.RESUMED_COMPLETED
