from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.runtime.agent import AgentToolRuntime
from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator_contracts import (
    TaskExecutionError,
    TaskOutcome,
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

    async def emit_retryable_error(*, runtime_state, **_kwargs):
        runtime_state.agent_results.append(
            {
                "success": False,
                "summary": "Agent LLM call failed: llm_rate_limited",
                "error_code": "llm_rate_limited",
                "retryable": True,
                "retry_after_ms": 2_000,
            }
        )
        yield RuntimeEvent.error(
            "Agent LLM call failed: llm_rate_limited",
            retryable=True,
            retry_after_ms=2_000,
        )

    executor.execute = emit_retryable_error  # type: ignore[method-assign]
    state = SimpleNamespace(agent_results=[])

    with pytest.raises(TaskExecutionError) as raised:
        await executor.execute_task(
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
async def test_non_retryable_agent_error_remains_unfulfillable() -> None:
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())

    async def emit_non_retryable_error(*, runtime_state, **_kwargs):
        runtime_state.agent_results.append(
            {
                "success": False,
                "summary": "Agent request exceeds provider limits",
                "error_code": "llm_request_too_large",
                "retryable": False,
            }
        )
        yield RuntimeEvent.error("Agent request exceeds provider limits", retryable=False)

    executor.execute = emit_non_retryable_error  # type: ignore[method-assign]
    state = SimpleNamespace(agent_results=[])

    result = await executor.execute_task(
        request=_request(),
        runtime_state=state,
        messages=[],
        ctx=SimpleNamespace(extra={}),
        user_id=AsyncMock(),
        tenant_id=AsyncMock(),
    )

    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "llm_request_too_large"


def test_agent_retry_delay_respects_provider_hint() -> None:
    assert AgentToolRuntime._retry_delay_ms(retry_count=0, retry_after_ms=None) == 500
    assert AgentToolRuntime._retry_delay_ms(retry_count=2, retry_after_ms=2_000) == 2_000
    assert AgentToolRuntime._retry_delay_ms(retry_count=0, retry_after_ms=60_000) == 30_000
