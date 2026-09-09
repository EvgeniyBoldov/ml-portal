from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import TaskCompletionDeclaration, TaskExecutionError, TaskRequest


def _request() -> TaskRequest:
    return TaskRequest(task_id="generate_file", executor="direct_answer", intent="generate", instructions="Generate a file")


@pytest.mark.asyncio
async def test_technical_failure_uses_error_path() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_error(*, ctx, **_kwargs):
        ctx.extra["agent_execution_failure"] = {"code": "llm_rate_limited", "message": "limited", "retryable": True}
        yield RuntimeEvent.error("limited", retryable=True)

    executor.execute = emit_error  # type: ignore[method-assign]
    with pytest.raises(TaskExecutionError, match="limited"):
        await executor.execute_attempt(request=_request(), runtime_state=SimpleNamespace(), messages=[], ctx=SimpleNamespace(extra={}), user_id=AsyncMock(), tenant_id=AsyncMock())


@pytest.mark.asyncio
async def test_agent_declaration_is_paired_with_runtime_evidence() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_result(*, ctx, **_kwargs):
        ctx.extra["agent_execution_result"] = TaskCompletionDeclaration(completion="fulfilled", report="done", outputs={"answer": {"kind": "value", "value": "ok"}})
        ctx.extra["agent_execution_verified"] = {"artifacts": [{"artifact_ref": "artifact-1"}]}
        yield RuntimeEvent.status("done")

    executor.execute = emit_result  # type: ignore[method-assign]
    receipt = await executor.execute_attempt(request=_request(), runtime_state=SimpleNamespace(), messages=[], ctx=SimpleNamespace(extra={}), user_id=AsyncMock(), tenant_id=AsyncMock())
    assert receipt.declaration.outputs["answer"].value == "ok"
    assert receipt.verified["artifacts"][0]["artifact_ref"] == "artifact-1"


@pytest.mark.asyncio
async def test_commit_phase_is_tool_free_and_uses_only_runtime_projection() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())
    executor._tool_runtime.llm.call = AsyncMock(return_value='{"completion":"fulfilled","report":"ready","outputs":{"answer":{"kind":"value","value":"ok"}},"needs":[]}')
    task = TaskRequest(task_id="answer", executor="direct_answer", intent="answer", instructions="Answer", expected_outputs=[{"key": "answer", "description": "Answer"}])

    declaration = await executor._commit_declaration(
        task=task,
        model="test-model",
        observed={"results": [{"result_ref": "result_1", "result_preview": "bounded"}], "artifacts": []},
    )

    assert declaration.outputs["answer"].value == "ok"
    kwargs = executor._tool_runtime.llm.call.await_args.kwargs
    assert "tools" not in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert "bounded" in kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_large_runtime_result_is_externalized() -> None:
    from unittest.mock import patch

    payload = {"body": "x" * 5000}
    with patch("app.runtime.agent_executor.s3_manager.upload_content_sync", new=AsyncMock(return_value=True)) as upload:
        verified = {"result_records": [{"result_ref": "result_1", "payload": payload}]}
        await AgentExecutor._externalize_large_results(verified, "attempt-1")
    assert verified["result_records"][0]["payload"] is None
    assert verified["result_records"][0]["payload_ref"]["key"] == "runtime/results/attempt-1/result_1.json"
    upload.assert_awaited_once()


def test_terminal_schema_rejects_unknown_output_fields() -> None:
    from app.runtime.orchestrator_contracts import parse_task_completion_declaration
    with pytest.raises(ValueError):
        parse_task_completion_declaration('{"completion":"fulfilled","report":"ready","outputs":{},"needs":[],"checkpoint":{}}')
