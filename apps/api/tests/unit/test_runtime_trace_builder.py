from datetime import datetime, UTC

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

