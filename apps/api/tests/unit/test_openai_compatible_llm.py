from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
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


@pytest.mark.asyncio
async def test_resolve_model_connection_strips_model_selector(monkeypatch: pytest.MonkeyPatch):
    llm = OpenAICompatibleLLM()

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

    base_url, api_key, resolved_model_name, connector, extra_config = await llm._resolve_model_connection(
        "  gemma-test  "
    )

    assert base_url == "http://litellm:4000/v1"
    assert api_key is None
    assert resolved_model_name == "openai/gemma-test"
    assert connector == "litellm_http"
    assert extra_config == {}


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
