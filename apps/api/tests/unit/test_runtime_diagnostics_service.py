from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.runtime_diagnostics_service import RuntimeDiagnosticsService


def _step(step_number: int, step_type: str, data: dict | None = None, error: str | None = None):
    return SimpleNamespace(
        step_number=step_number,
        step_type=step_type,
        data=data or {},
        error=error,
        duration_ms=10,
        created_at=datetime.now(timezone.utc),
    )


def test_runtime_diagnostics_summary_includes_eval_and_memory_sections():
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        status="completed",
        agent_slug="assistant",
        context_snapshot={"db_dsn": "postgresql://user:secret@localhost:5432/app"},
        steps=[
            _step(
                0,
                "llm_request",
                {"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            ),
            _step(1, "operation_call", {"operation_slug": "collection.document.search", "input": {"query": "doc"}}),
            _step(2, "operation_result", {"operation_slug": "collection.document.search", "output": {"hits": 1}}),
            _step(
                3,
                "status",
                {
                    "memory_bundle": {
                        "sections": [
                            {"name": "facts", "selection_reason": "selected", "items": [{"text": "project alpha"}]}
                        ]
                    }
                },
            ),
            _step(4, "final", {"content": "document answer"}),
        ],
    )

    summary = RuntimeDiagnosticsService().build_summary(run)

    assert summary["run_id"] == run_id
    assert "collection.document.search" in summary["operations"]
    assert summary["memory_sections"][0]["name"] == "facts"
    assert summary["eval_summary"]
