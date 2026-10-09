from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.llm_context import allocate_context
from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
from app.adapters.interfaces.llm import LLMCallOptions, LLMErrorCode, LLMProviderError


def request(**extra):
    return {"model": "unknown-model", "messages": [{"role": "user", "content": "Привет <|endoftext|>"}], **extra}


def test_allocation_includes_tools_and_response_schema():
    plain = allocate_context(request(), 16384)
    full = allocate_context(request(tools=[{"function": {"description": "definition " * 100}}], response_format={"type": "json_schema", "json_schema": {"description": "schema " * 100}}), 16384)
    assert full.estimated_input_tokens > plain.estimated_input_tokens
    assert full.reserved_input_tokens >= full.estimated_input_tokens * 1.1
    assert full.max_output_tokens + full.reserved_input_tokens == 16384
    assert full.minimum_output_tokens == 1639


def test_no_space_for_minimum_output():
    with pytest.raises(LLMProviderError) as caught:
        allocate_context(request(messages=[{"role": "user", "content": "word " * 2000}]), 1024)
    assert caught.value.code == LLMErrorCode.CONTEXT_WINDOW_EXCEEDED
    assert not caught.value.retryable


def provider_error(available, status=400):
    error = RuntimeError("provider bound")
    error.status_code = status
    error.body = {"error": {"available_output_tokens": available}}
    return error


def connector_client(side_effect=None):
    create = AsyncMock(side_effect=side_effect, return_value="response")
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_connector_owns_output_allocation(stream):
    client, create = connector_client()
    payload = request(max_tokens=1, max_completion_tokens=2, stream=stream)
    expected = allocate_context(payload, 16384).max_output_tokens
    result = await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, payload, 16384, 30)
    assert result == "response"
    assert create.call_args.kwargs["max_tokens"] == expected
    assert "max_completion_tokens" not in create.call_args.kwargs
    assert create.call_args.kwargs["stream"] is stream


@pytest.mark.asyncio
async def test_corrective_request_debits_budget_once():
    client, create = connector_client([provider_error(2048), "corrected"])
    debit = AsyncMock()
    result = await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, request(), 16384, 30, LLMCallOptions(on_transport_retry=debit))
    assert result == "corrected"
    assert create.await_count == 2
    assert create.call_args.kwargs["max_tokens"] == 2048
    assert 0 < create.call_args.kwargs["timeout"] <= 30
    debit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [0, 1000, 16384])
async def test_unusable_provider_bound_never_retries(available):
    client, create = connector_client(provider_error(available))
    with pytest.raises(LLMProviderError) as caught:
        await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, request(), 16384, 30)
    assert caught.value.code == LLMErrorCode.CONTEXT_WINDOW_EXCEEDED
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_is_not_context_correction():
    error = provider_error(2048, status=429)
    client, create = connector_client(error)
    with pytest.raises(RuntimeError) as caught:
        await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, request(), 16384, 30)
    assert caught.value is error
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_context_correction_stops_after_one_retry():
    client, create = connector_client([provider_error(2048), provider_error(1800)])
    with pytest.raises(LLMProviderError):
        await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, request(), 16384, 30)
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_exhausted_budget_prevents_corrective_network_request():
    client, create = connector_client(provider_error(2048))
    error = LLMProviderError(code=LLMErrorCode.CALL_LIMIT_EXCEEDED, safe_message="budget exhausted", retryable=False)
    with pytest.raises(LLMProviderError) as caught:
        await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client, request(), 16384, 30, LLMCallOptions(on_transport_retry=AsyncMock(side_effect=error)))
    assert caught.value is error
    assert create.await_count == 1


def test_explicit_context_error_parsing():
    error = RuntimeError("maximum context length is 16384 tokens; request has 14000 tokens")
    assert OpenAICompatibleLLM._available_output_tokens(error) == 2384


def test_planner_surfaces_connector_context_failure():
    from app.adapters.impl.llm_context import context_exhausted
    from app.runtime.llm.structured import StructuredCallError
    from app.runtime.orchestrator import _context_failure_event
    event = _context_failure_event(StructuredCallError("request failed", original_exception=context_exhausted()))
    assert event.data["error_code"] == "llm_context_window_exceeded"
    assert event.data["retryable"] is False
    assert "контекстного окна" in event.data["user_message"]
    assert _context_failure_event(ValueError("invalid proposal")) is None


def test_model_update_rejects_null_or_zero_context_window():
    from app.schemas.model_registry import ModelUpdate
    from pydantic import ValidationError
    for value in (None, 0):
        with pytest.raises(ValidationError):
            ModelUpdate(context_window_tokens=value)
    assert ModelUpdate().model_dump(exclude_unset=True) == {}
    assert ModelUpdate(context_window_tokens=32768).context_window_tokens == 32768
