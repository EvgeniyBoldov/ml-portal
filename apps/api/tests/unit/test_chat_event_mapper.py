from types import SimpleNamespace

from app.runtime.events import RuntimeEventType
from app.services.chat_event_mapper import ChatEventMapper


def test_runtime_mapper_drops_raw_tool_events():
    result = ChatEventMapper().map_runtime_event(SimpleNamespace(
        type=RuntimeEventType.TOOL_CALL, data={"arguments": {"secret": 1}},
    ))
    assert result is None


def test_runtime_mapper_maps_progress_and_safe_error():
    mapper = ChatEventMapper()
    progress = {
        "run_id": "run-1", "phase": "planner", "kind": "plan_created",
        "description": "Планирую", "chat_stage": "planning",
        "action": "plan_created", "outcome": None,
    }
    assert mapper.map_runtime_event(SimpleNamespace(type=RuntimeEventType.PLAN_CREATED, data={"_progress": progress})) == {
        "type": "stage", "activity": progress,
    }
    error = mapper.map_runtime_event(SimpleNamespace(type=RuntimeEventType.ERROR, data={"error_code": "operation_unavailable", "retryable": False}))
    assert error is not None and error["type"] == "error" and "error_code" not in error
