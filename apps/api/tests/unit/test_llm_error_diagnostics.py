from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.streaming import RoleStreamingCall, StreamError
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.services.execution_limits_service import ExecutionLimitsPayload


class _Result(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_structured_call_preserves_upstream_exception_and_traceback():
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=ConnectionError("LiteLLM upstream reset"))
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(
        return_value={"model": "llama-3.1", "max_retries": 0, "timeout_s": 1}
    )
    call.limits_service.get_effective = AsyncMock(return_value=ExecutionLimitsPayload())

    with pytest.raises(StructuredCallError) as raised:
        await call.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload={"input": "hello"},
            schema=_Result,
        )

    error = raised.value
    assert error.error_type == "ConnectionError"
    assert "LiteLLM upstream reset" in str(error)
    assert "ConnectionError" in (error.debug_payload() or {}).get("traceback", "")


async def _failed_stream():
    raise ConnectionError("LiteLLM stream reset")
    yield "unreachable"


@pytest.mark.asyncio
async def test_streaming_error_preserves_exception_type_and_traceback():
    client = AsyncMock()
    client.chat_stream = lambda *args, **kwargs: _failed_stream()
    call = RoleStreamingCall(session=AsyncMock(), llm_client=client)
    call._limits_service.get_effective = AsyncMock(return_value=ExecutionLimitsPayload())

    events = [
        event
        async for event in call.invoke_stream(
            role=SystemLLMRoleType.SYNTHESIZER,
            messages=[{"role": "user", "content": "hello"}],
            llm_call_id="run:synthesis-llm:1",
            role_config={"model": "llama-3.1", "timeout_s": 1},
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], StreamError)
    assert events[0].error_type == "ConnectionError"
    assert "LiteLLM stream reset" in events[0].message
    assert "ConnectionError" in (events[0].debug or {}).get("traceback", "")
