from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
from app.adapters.interfaces.llm import LLMErrorCode
from app.services.llm_connection_resolver import RegistryLLMConnectionResolver
from app.services.model_resolver import ModelResolver, _cache
from app.services.model_connector_profiles import build_model_auth_headers, get_healthcheck_paths


@pytest.mark.asyncio
async def test_aclose_ignores_event_loop_shutdown_errors():
    client = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("Event loop is closed")))
    llm = object.__new__(OpenAICompatibleLLM)
    llm._client_cache = {("http://example", None): client}

    await OpenAICompatibleLLM.aclose(llm)

    assert llm._client_cache == {}
    assert client.close.await_count == 1


def test_build_model_auth_headers_for_litellm():
    headers = build_model_auth_headers("litellm_http", "secret")
    assert headers == {"x-litellm-api-key": "secret"}


def test_build_model_auth_headers_for_openai():
    headers = build_model_auth_headers("openai_http", "secret")
    assert headers == {"Authorization": "Bearer secret"}


def test_build_model_auth_headers_for_custom_header_api_key():
    headers = build_model_auth_headers(
        "openai_http",
        "secret",
        extra_config={"auth_header_name": "x-litellm-api-key", "auth_scheme": "raw"},
    )
    assert headers == {"x-litellm-api-key": "secret"}


def test_get_healthcheck_paths_for_litellm():
    assert get_healthcheck_paths("litellm_http") == [
        "/health/liveliness",
        "/health",
        "/models",
        "/v1/models",
    ]


def test_get_or_create_client_uses_profiled_auth_headers():
    llm = OpenAICompatibleLLM()
    llm.settings = SimpleNamespace(LLM_TIMEOUT=10.0)
    llm._client_cache = {}

    client = llm._get_or_create_client(
        base_url="http://litellm:4000/v1",
        api_key="secret",
        connector="litellm_http",
        extra_config={},
    )

    assert client.auth_headers == {"x-litellm-api-key": "secret"}
    assert client.max_retries == 0


def test_normalize_error_classifies_timeout_and_context_limit():
    timeout = OpenAICompatibleLLM._normalize_error(TimeoutError("request timeout"))
    oversized = OpenAICompatibleLLM._normalize_error(RuntimeError("maximum context length exceeded"))

    assert timeout.code is LLMErrorCode.TIMEOUT
    assert timeout.retryable is True
    assert oversized.code is LLMErrorCode.REQUEST_TOO_LARGE
    assert oversized.retryable is False


def test_rejection_diagnostics_describe_tool_protocol_without_content():
    shape = OpenAICompatibleLLM._request_shape_for_diagnostics(
        {
            "model": "gemma-provider",
            "messages": [
                {"role": "system", "content": "secret prompt"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {"name": "collection.template.fill", "arguments": "{\"secret\":1}"},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "private result"},
            ],
            "tools": [{"function": {"name": "collection.template.fill"}}],
            "tool_choice": "auto",
            "max_tokens": 1000,
            "temperature": 0.1,
        }
    )

    rendered = str(shape)
    assert "secret prompt" not in rendered
    assert "private result" not in rendered
    assert "secret" not in rendered
    assert shape["messages"][1]["tool_calls"][0]["id_present"] is True
    assert shape["messages"][2]["tool_call_id_present"] is True


def test_provider_detail_diagnostics_is_bounded_and_filtered():
    error = SimpleNamespace(
        body={"error": {"message": "bad request", "code": "invalid", "prompt": "secret"}}
    )

    detail = OpenAICompatibleLLM._provider_detail_for_diagnostics(error)

    assert "bad request" in detail
    assert "invalid" in detail
    assert "secret" not in detail


@pytest.mark.asyncio
async def test_connection_resolver_strips_model_selector(monkeypatch: pytest.MonkeyPatch):

    model = SimpleNamespace(
        provider_model_name="  openai/gemma-test  ",
        alias="gemma-test",
        base_url="http://litellm:4000/v1",
        instance=None,
        instance_id=None,
        connector="litellm_http",
        extra_config={},
    )

    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: model))
    )

    class _SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.core.db.get_session_factory",
        lambda: lambda: _SessionContext(),
    )

    connection = await RegistryLLMConnectionResolver().resolve("  gemma-test  ")

    assert connection.base_url == "http://litellm:4000/v1"
    assert connection.api_key is None
    assert connection.provider_model_name == "openai/gemma-test"
    assert connection.connector == "litellm_http"
    assert connection.extra_config == {}


@pytest.mark.asyncio
async def test_model_resolver_strips_alias_and_provider_name():
    _cache.clear()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: "  provider/model  "),
            ]
        )
    )
    resolver = ModelResolver(session)

    resolved = await resolver.resolve("  alias/model  ")

    assert resolved == "provider/model"
    assert session.execute.await_count == 1
    assert _cache["alias/model"][0] == "provider/model"
