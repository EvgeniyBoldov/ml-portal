from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.runtime.agent import AgentToolRuntime
from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion,
    AgentExecutionResult,
    TaskExecutionError,
    TaskRequest,
)


def _request() -> TaskRequest:
    return TaskRequest(
        task_id="generate_file",
        executor="direct_answer",
        intent="generate",
        instructions="Generate a file",
    )


@pytest.mark.asyncio
async def test_retryable_agent_error_uses_technical_task_failure_path() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_retryable_error(*, ctx, **_kwargs):
        ctx.extra["agent_execution_failure"] = {
            "code": "llm_rate_limited", "message": "Agent LLM call failed: llm_rate_limited",
            "retryable": True, "retry_after_ms": 2_000,
        }
        yield RuntimeEvent.error(
            "Agent LLM call failed: llm_rate_limited",
            retryable=True,
            retry_after_ms=2_000,
        )

    executor.execute = emit_retryable_error  # type: ignore[method-assign]
    state = SimpleNamespace()

    with pytest.raises(TaskExecutionError) as raised:
        await executor.execute_attempt(
            request=_request(),
            runtime_state=state,
            messages=[],
            ctx=SimpleNamespace(extra={}),
            user_id=AsyncMock(),
            tenant_id=AsyncMock(),
        )

    assert raised.value.code == "llm_rate_limited"
    assert raised.value.retryable is True
    assert raised.value.details == {"retry_after_ms": 2_000}


@pytest.mark.asyncio
async def test_business_unfulfillable_is_a_normal_execution_result() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_non_retryable_error(*, ctx, **_kwargs):
        ctx.extra["agent_execution_result"] = AgentExecutionResult(
            completion=AgentExecutionCompletion.UNFULFILLABLE,
            description="Agent request exceeds provider limits",
        )
        yield RuntimeEvent.status("done")

    executor.execute = emit_non_retryable_error  # type: ignore[method-assign]
    state = SimpleNamespace()

    result = await executor.execute_attempt(
        request=_request(),
        runtime_state=state,
        messages=[],
        ctx=SimpleNamespace(extra={}),
        user_id=AsyncMock(),
        tenant_id=AsyncMock(),
    )

    assert result.completion is AgentExecutionCompletion.UNFULFILLABLE


def test_agent_retry_delay_respects_provider_hint() -> None:
    assert AgentToolRuntime._retry_delay_ms(retry_count=0, retry_after_ms=None) == 500
    assert AgentToolRuntime._retry_delay_ms(retry_count=2, retry_after_ms=2_000) == 2_000
    assert AgentToolRuntime._retry_delay_ms(retry_count=0, retry_after_ms=60_000) == 30_000


def test_artifact_producing_operation_names_are_recognized_canonically() -> None:
    assert AgentExecutor._creates_downloadable_artifact("file.generate")
    assert AgentExecutor._creates_downloadable_artifact("instance.local-system-tools.file.generate")
    assert AgentExecutor._creates_downloadable_artifact(
        "instance.local-template-tools.collection.template.fill"
    )
    assert not AgentExecutor._creates_downloadable_artifact("file.read")


def test_artifact_only_response_detects_unencoded_file_names() -> None:
    assert AgentExecutor._is_url_only_response(
        "https://storage.cloud.local/artifacts/artifact-1/filled_Заявка на сетевую связность (6).xlsx"
    )


@pytest.mark.asyncio
async def test_agent_execution_keeps_runtime_verified_artifacts() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_success(*, ctx, **_kwargs):
        ctx.extra["agent_execution_result"] = AgentExecutionResult(
            completion=AgentExecutionCompletion.FULFILLED,
            description="form filled",
            verified={"artifacts": [{"artifact_id": "artifact-1", "file_name": "request.xlsx"}]},
        )
        yield RuntimeEvent.status("done")

    executor.execute = emit_success  # type: ignore[method-assign]
    state = SimpleNamespace()
    result = await executor.execute_attempt(
        request=_request(),
        runtime_state=state,
        messages=[],
        ctx=SimpleNamespace(extra={}),
        user_id=AsyncMock(),
        tenant_id=AsyncMock(),
    )

    assert result.verified["artifacts"][0]["artifact_id"] == "artifact-1"


@pytest.mark.asyncio
async def test_agent_execution_keeps_declared_data_output() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_success(*, ctx, **_kwargs):
        ctx.extra["agent_execution_result"] = AgentExecutionResult(
            completion=AgentExecutionCompletion.FULFILLED,
            description="i121-mgmt-sw05: active, 172.25.253.18/25",
            outputs={"device_info": {"text": "i121-mgmt-sw05: active, 172.25.253.18/25"}},
        )
        yield RuntimeEvent.status("done")

    executor.execute = emit_success  # type: ignore[method-assign]
    state = SimpleNamespace()
    result = await executor.execute_attempt(
        request=_request(),
        runtime_state=state,
        messages=[],
        ctx=SimpleNamespace(extra={}),
        user_id=AsyncMock(),
        tenant_id=AsyncMock(),
    )

    assert result.outputs["device_info"].text == result.description
