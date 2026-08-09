from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.streaming import RoleStreamingCall, StreamError
from app.runtime.events import RuntimeEventType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.adapters.interfaces.llm import LLMErrorCode, LLMProviderError
from app.services.model_call_config_service import ModelCallConfig


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
    assert "Планер не формирует пользовательский ответ" in prompt
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


def test_structured_retry_delay_uses_backoff_and_provider_hint():
    assert StructuredLLMCall._retry_delay_ms(attempt=0, retry_after_ms=None) == 500
    assert StructuredLLMCall._retry_delay_ms(attempt=2, retry_after_ms=3_000) == 3_000
    assert StructuredLLMCall._retry_delay_ms(attempt=0, retry_after_ms=60_000) == 30_000


@pytest.mark.asyncio
async def test_structured_call_preserves_upstream_exception_and_traceback():
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=ConnectionError("LiteLLM upstream reset"))
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(
        return_value={"model": "llama-3.1", "max_retries": 0, "timeout_s": 1}
    )
    call.model_call_config_service.resolve = AsyncMock(
        return_value=ModelCallConfig(max_output_tokens=None, request_timeout_s=1, max_retries=0)
    )

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
    call.model_call_config_service.resolve = AsyncMock(
        return_value=ModelCallConfig(max_output_tokens=None, request_timeout_s=1, max_retries=1)
    )
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
    requests = [event for event in events if event.type is RuntimeEventType.LLM_REQUEST]
    assert len(requests) == 2
    assert len({event.data["llm_call_id"] for event in requests}) == 1
    responses = [event for event in events if event.type is RuntimeEventType.LLM_RESPONSE]
    # One raw response is recorded before schema validation, then the
    # validated terminal response closes the same logical call.
    assert len(responses) == 3
    assert {event.data["llm_call_id"] for event in responses} == {requests[0].data["llm_call_id"]}
    assert responses[-1].data["status"] == "completed"
    logical_call_ids = {event.data["logical_llm_call_id"] for event in requests}
    assert len(logical_call_ids) == 1
    assert retries[0].data["logical_llm_call_id"] in logical_call_ids


@pytest.mark.asyncio
async def test_structured_call_preserves_normalized_error_code_in_trace():
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=LLMProviderError(
        code=LLMErrorCode.REQUEST_TOO_LARGE,
        safe_message="LLM request exceeds provider limits",
        retryable=False,
        status_code=413,
    ))
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(
        return_value={"model": "qwen", "max_retries": 1, "timeout_s": 20}
    )
    call.model_call_config_service.resolve = AsyncMock(
        return_value=ModelCallConfig(max_output_tokens=None, request_timeout_s=20, max_retries=0)
    )
    events = []

    async def sink(event):
        events.append(event)

    with pytest.raises(StructuredCallError):
        await call.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload={"input": "hello"}, schema=_Result,
            agent_execution_id=uuid4(), event_sink=sink,
        )

    responses = [event for event in events if event.type is RuntimeEventType.LLM_RESPONSE]
    assert len(responses) == 1
    assert responses[0].data["error_code"] == "llm_request_too_large"
    assert responses[0].data["retryable"] is False
    assert client.chat.await_count == 1


@pytest.mark.asyncio
async def test_structured_planner_uses_resolved_retry_limit():
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=ConnectionError("provider unavailable"))
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(
        return_value={"model": "qwen", "max_retries": 0, "timeout_s": 1}
    )
    call.model_call_config_service.resolve = AsyncMock(
        return_value=ModelCallConfig(max_output_tokens=None, request_timeout_s=1, max_retries=1)
    )

    with pytest.raises(StructuredCallError):
        await call.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload={"input": "hello"},
            schema=_Result,
        )

    assert client.chat.await_count == 2


async def _failed_stream():
    raise ConnectionError("LiteLLM stream reset")
    yield "unreachable"


@pytest.mark.asyncio
async def test_streaming_error_preserves_exception_type_and_traceback():
    client = AsyncMock()
    client.chat_stream = lambda *args, **kwargs: _failed_stream()
    call = RoleStreamingCall(session=AsyncMock(), llm_client=client)
    call._model_call_config_service.resolve = AsyncMock(
        return_value=ModelCallConfig(max_output_tokens=None, request_timeout_s=1, max_retries=0)
    )

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
    assert events[0].message == "LLM stream failed"
    assert "ConnectionError" in (events[0].debug or {}).get("traceback", "")
