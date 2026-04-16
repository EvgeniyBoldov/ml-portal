from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.runtime_trace_pack_service import RuntimeTracePackService


def _step(step_number: int, step_type: str, data: dict | None = None, error: str | None = None):
    return SimpleNamespace(
        step_number=step_number,
        step_type=step_type,
        data=data or {},
        error=error,
        duration_ms=10,
        created_at=datetime.now(timezone.utc),
    )


def test_trace_pack_collects_operations_prompts_and_tool_io():
    run = SimpleNamespace(
        id=uuid4(),
        agent_slug="test-agent",
        status="completed",
        logging_level="full",
        context_snapshot={"mode": "pipeline"},
        error=None,
        steps=[
            _step(0, "budget_policy", {"max_steps": 10, "max_tool_calls_total": 50}),
            _step(0, "llm_request", {"model": "gpt-test", "system_prompt": "You are...", "messages": [{"role": "user"}]}),
            _step(1, "operation_call", {"operation_slug": "collection.document.search", "input": {"query": "vpn"}}),
            _step(2, "operation_result", {"operation_slug": "collection.document.search", "output": {"hits": 3}}),
            _step(3, "final_response", {"content": "done"}),
        ],
    )

    pack = RuntimeTracePackService().build_trace_pack(run)

    assert pack["agent_slug"] == "test-agent"
    assert "collection.document.search" in pack["operations"]
    assert len(pack["prompt_surfaces"]) == 1
    assert len(pack["tool_io"]) == 2
    assert pack["total_steps"] == 5
    assert any(item["step_type"] == "budget_policy" for item in pack["timeline"])


def test_trace_pack_collects_run_and_step_errors():
    run = SimpleNamespace(
        id=uuid4(),
        agent_slug="test-agent",
        status="failed",
        logging_level="full",
        context_snapshot={},
        error="run failed",
        steps=[
            _step(0, "operation_call", {"operation_slug": "sql.execute_sql"}),
            _step(1, "error", {"stage": "runtime"}, error="step failed"),
        ],
    )

    pack = RuntimeTracePackService().build_trace_pack(run)

    assert len(pack["errors"]) == 2
    assert any(item["scope"] == "run" for item in pack["errors"])
    assert any(item["scope"] == "step" for item in pack["errors"])
