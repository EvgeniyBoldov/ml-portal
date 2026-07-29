from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.streaming import RoleStreamingCall, StreamError
from app.runtime.events import RuntimeEventType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.services.execution_limits_service import ExecutionLimitsPayload


class _Result(BaseModel):
    value: str


def test_structured_prompt_generates_contract_for_non_synthesizer_roles():
    prompt = StructuredLLMCall._compile_role_prompt(
        {
            "role_type": SystemLLMRoleType.PLANNER.value,
            "identity": "planner",
            "output_requirements": "СТАРЫЙ КОНТРАКТ ИЗ БД",
        },
        None,
        schema=_Result,
    )

    assert "СТАРЫЙ КОНТРАКТ ИЗ БД" not in prompt
    assert "Верни строго валидный JSON" in prompt
    assert '"value"' in prompt


def test_structured_prompt_keeps_database_requirements_for_synthesizer():
    prompt = StructuredLLMCall._compile_role_prompt(
        {
            "role_type": SystemLLMRoleType.SYNTHESIZER.value,
            "output_requirements": "Редакторские требования из БД",
        },
        None,
        schema=None,
    )

    assert "Редакторские требования из БД" in prompt


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


@pytest.mark.asyncio
async def test_structured_call_emits_safe_protocol_retry_for_invalid_schema():
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=[
        {"choices": [{"message": {"content": "{}"}}]},
        {"choices": [{"message": {"content": '{"value": "ok"}'}}]},
    ])
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(
        return_value={"model": "llama-3.1", "max_retries": 1, "timeout_s": 1}
    )
    call.limits_service.get_effective = AsyncMock(return_value=ExecutionLimitsPayload())
    events = []

    async def sink(event):
        events.append(event)

    result = await call.invoke(
        role=SystemLLMRoleType.PLANNER,
        payload={"input": "hello"},
        schema=_Result,
        agent_execution_id=uuid4(),
        event_sink=sink,
    )

    assert result.value.value == "ok"
    retries = [event for event in events if event.type is RuntimeEventType.PROTOCOL_RETRY]
    assert len(retries) == 1
    assert retries[0].data["reason"] == "schema_validation"
    assert "content" not in retries[0].data


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
