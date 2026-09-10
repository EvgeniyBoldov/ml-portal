from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import (
    TaskCompletionDeclaration,
    TaskExecutionError,
    TaskRequest,
    parse_task_completion_declaration,
)


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
async def test_missing_terminal_declaration_is_not_retryable() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_nothing(*, ctx, **_kwargs):
        yield RuntimeEvent.status("agent_finished_without_terminal_contract")

    executor.execute = emit_nothing  # type: ignore[method-assign]
    with pytest.raises(TaskExecutionError) as error:
        await executor.execute_attempt(
            request=_request(), runtime_state=SimpleNamespace(), messages=[],
            ctx=SimpleNamespace(extra={}), user_id=AsyncMock(), tenant_id=AsyncMock(),
        )

    assert error.value.code == "agent_task_completion_missing"
    assert error.value.retryable is False
    assert error.value.details["validation_stage"] == "agent_terminal_response"


def test_terminal_schema_rejects_unknown_output_fields() -> None:
    with pytest.raises(ValueError):
        parse_task_completion_declaration('{"completion":"fulfilled","report":"ready","outputs":{},"needs":[],"checkpoint":{}}')


def test_terminal_declaration_accepts_a_standalone_json_fence() -> None:
    raw = """```json
{"completion":"fulfilled","report":"ready","outputs":{},"needs":[]}
```"""

    declaration = parse_task_completion_declaration(
        AgentExecutor._unwrap_terminal_json_fence(raw)
    )

    assert declaration.completion_claim == "fulfilled"


def test_terminal_declaration_does_not_accept_prose_around_json_fence() -> None:
    raw = """Here is the result:
```json
{"completion":"fulfilled","report":"ready","outputs":{},"needs":[]}
```"""

    with pytest.raises(ValueError):
        parse_task_completion_declaration(AgentExecutor._unwrap_terminal_json_fence(raw))


def test_terminal_prompt_can_build_task_schema() -> None:
    task = TaskRequest(
        task_id="answer", executor="direct_answer", intent="answer",
        instructions="Answer", expected_outputs=[{"key": "answer", "description": "Answer"}],
    )
    prompt = AgentExecutor._with_terminal_contract_prompt("agent prompt", task)
    assert "RUNTIME TASK COMPLETION DECLARATION" in prompt
    assert '"answer"' in prompt


def test_provider_terminal_schema_matches_need_and_limitation_contract() -> None:
    import jsonschema

    from app.runtime.orchestrator_contracts import task_completion_json_schema

    schema = task_completion_json_schema(_request())
    malformed = {
        "completion": "unfulfillable",
        "report": "failed",
        "outputs": {},
        "needs": [{"ref": "x"}],
        "limitation": {"reason": "missing runtime result"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(malformed)
