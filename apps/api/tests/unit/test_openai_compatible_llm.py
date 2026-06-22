from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
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
