from __future__ import annotations

from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.services.runtime_terminal_status import (
    RunTerminalStatus,
    planner_terminal_from_event,
)


def test_planner_terminal_from_event_maps_stop_and_error():
    stop = RuntimeEvent(RuntimeEventType.STOP, {"reason": "waiting_input", "question": "q"})
    status, err = planner_terminal_from_event(stop) or (None, None)
    assert status == RunTerminalStatus.WAITING_INPUT
    assert err == "q"

    fail = RuntimeEvent(RuntimeEventType.ERROR, {"error": "boom"})
    status, err = planner_terminal_from_event(fail) or (None, None)
    assert status == RunTerminalStatus.FAILED
    assert err == "boom"

    failed_final = RuntimeEvent(RuntimeEventType.FINAL, {"content": "partial", "stop_reason": "failed"})
    status, err = planner_terminal_from_event(failed_final) or (None, None)
    assert status == RunTerminalStatus.FAILED
    assert err is None

