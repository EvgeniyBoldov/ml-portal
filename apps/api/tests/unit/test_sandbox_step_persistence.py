from app.runtime.events import RuntimeEventType


def test_runtime_event_type_values_fit_sandbox_step_type_column():
    too_long = [event_type.value for event_type in RuntimeEventType if len(event_type.value) > 50]
    assert too_long == []

