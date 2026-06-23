from datetime import datetime, UTC

from app.runtime.events import RuntimeEventType
from app.services.runtime_trace_builder import RuntimeTraceBuilder, TraceStep


def test_runtime_trace_builder_groups_by_iteration_and_maps_categories():
    trace = RuntimeTraceBuilder().build(
        [
            TraceStep(
                id="1",
                raw_type="user_request",
                data={"content": "hello", "step": 0},
                step_number=0,
                created_at=datetime.now(UTC),
            ),
            TraceStep(
                id="2",
                raw_type="llm_call",
                data={"step": 1, "response_length": 120},
                step_number=1,
                created_at=datetime.now(UTC),
            ),
            TraceStep(
                id="3",
                raw_type="operation_result",
                data={"step": 1, "success": False, "operation_slug": "search"},
                step_number=2,
                created_at=datetime.now(UTC),
            ),
        ]
    )

    assert trace.total_events == 3
    assert len(trace.iterations) == 2
    assert trace.iterations[0].events[0].category == "input"
    assert trace.iterations[1].events[0].category == "llm"
    assert trace.iterations[1].events[1].category == "operation"
    assert trace.iterations[1].events[1].status == "error"


def test_runtime_trace_builder_unknown_event_fallback():
    trace = RuntimeTraceBuilder().build(
        [TraceStep(id="x", raw_type="brand_new_event", data={"a": 1})]
    )
    event = trace.iterations[0].events[0]
    assert event.category == "system"
    assert "brand_new_event" in event.title


def test_runtime_trace_builder_treats_llm_request_as_canonical_event(caplog):
    trace = RuntimeTraceBuilder().build(
        [TraceStep(id="legacy-1", raw_type="llm_request", data={"model": "x"})]
    )

    assert trace.total_events == 1
    assert trace.iterations[0].events[0].category == "llm"
    assert trace.iterations[0].events[0].summary == "{'model': 'x'}"
    assert not any("legacy raw_type=llm_request" in rec.message for rec in caplog.records)


def test_runtime_trace_builder_knows_all_runtime_event_types():
    missing_category = []
    missing_title = []
    for event_type in RuntimeEventType:
        key = event_type.value
        if key not in RuntimeTraceBuilder._CATEGORY_MAP:
            missing_category.append(key)
        if key not in RuntimeTraceBuilder._TITLES:
            missing_title.append(key)

    assert missing_category == []
    assert missing_title == []
