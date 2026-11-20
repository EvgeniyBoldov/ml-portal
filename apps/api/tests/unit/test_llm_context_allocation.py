from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
from app.adapters.interfaces.llm import LLMCallOptions, LLMErrorCode, LLMProviderError


def request(**extra):
    return {"model": "unknown-model", "messages": [{"role": "user", "content": "Привет <|endoftext|>"}], **extra}


def provider_error(available, status=400):
    error = RuntimeError("provider bound")
    error.status_code = status
    error.body = {"error": {"available_output_tokens": available}}
    return error


def connector_client(side_effect=None):
    create = AsyncMock(side_effect=side_effect, return_value="response")
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


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
