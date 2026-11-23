"""Unit tests for ModelHealthChecker (app/services/model_health_checker.py)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.model_registry import HealthStatus, Model, ModelType
from app.adapters.interfaces.llm import LLMErrorCode, LLMProviderError
from app.services.credential_service import CredentialError, DecryptedCredentials
from app.services.model_health_checker import ModelHealthChecker


def make_model(**overrides) -> MagicMock:
    model = MagicMock(spec=Model)
    model.id = uuid4()
    model.alias = "test-model"
    model.provider_model_name = "provider/test-model"
    model.connector = "openai_http"
    model.type = ModelType.LLM_CHAT
    model.base_url = None
    model.instance_id = None
    model.instance = None
    model.extra_config = None
    for key, value in overrides.items():
        setattr(model, key, value)
    return model


def http_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else {}
    response.text = text
    return response


def patched_http_client(response=None, post_side_effect=None):
    """Return an active patcher for httpx.AsyncClient with a scripted response."""
    client = AsyncMock()
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    else:
        client.post.return_value = response
    patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))
    return patcher, client


class TestResolveBaseUrl:
    def test_explicit_base_url_wins(self):
        checker = ModelHealthChecker()
        instance = MagicMock()
        instance.url = "http://instance:9000"
        model = make_model(
            base_url="http://direct:8080",
            instance=instance,
            extra_config={"base_url": "http://extra:7000"},
        )

        assert checker._resolve_base_url(model) == "http://direct:8080"

    def test_falls_back_to_instance_url(self):
        checker = ModelHealthChecker()
        instance = MagicMock()
        instance.url = "http://instance:9000"
        model = make_model(instance=instance, extra_config={"base_url": "http://extra:7000"})

        assert checker._resolve_base_url(model) == "http://instance:9000"

    def test_falls_back_to_extra_config(self):
        checker = ModelHealthChecker()
        model = make_model(extra_config={"base_url": "http://extra:7000"})

        assert checker._resolve_base_url(model) == "http://extra:7000"

    def test_returns_none_when_nothing_configured(self):
        checker = ModelHealthChecker()

        assert checker._resolve_base_url(make_model()) is None


class TestResolveApiKey:
    @pytest.mark.parametrize(
        "auth_type,payload,expected",
        [
            ("api_key", {"api_key": "sk-1"}, "sk-1"),
            ("litellm_api_key", {"api_key": "sk-2"}, "sk-2"),
            ("token", {"token": "tok"}, "tok"),
            ("basic", {"password": "pw"}, "pw"),
            ("unknown_type", {"api_key": "sk-3"}, None),
        ],
    )
    async def test_resolves_secret_by_auth_type(self, auth_type, payload, expected):
        checker = ModelHealthChecker()
        session = AsyncMock()
        creds = DecryptedCredentials(
            auth_type=auth_type,
            payload=payload,
            credential_id=uuid4(),
            owner_type="platform",
        )
        with patch("app.services.model_health_checker.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials = AsyncMock(return_value=creds)

            assert await checker._resolve_api_key(make_model(instance_id=uuid4()), session) == expected

    async def test_returns_none_on_credential_error(self):
        checker = ModelHealthChecker()
        session = AsyncMock()
        with patch("app.services.model_health_checker.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials.side_effect = CredentialError("boom")

            assert await checker._resolve_api_key(make_model(instance_id=uuid4()), session) is None

    async def test_returns_none_without_session_or_instance(self):
        checker = ModelHealthChecker()

        assert await checker._resolve_api_key(make_model(instance_id=uuid4())) is None
        assert await checker._resolve_api_key(make_model(), AsyncMock()) is None


class TestCheckLLM:
    async def test_healthy_uses_canonical_adapter(self):
        checker = ModelHealthChecker()
        llm = AsyncMock()
        llm.chat.return_value = {"model": "provider/test-model", "usage": {"total_tokens": 5}}

        with patch("app.services.model_health_checker.get_llm_client", return_value=llm):
            result = await checker.check_model(make_model(type=ModelType.LLM_CHAT))

        assert result.status == HealthStatus.HEALTHY
        assert result.error is None
        assert result.details["model"] == "provider/test-model"
        # Probes must pass an explicit timeout so the check cannot hang.
        options = llm.chat.call_args.kwargs["options"]
        assert options.timeout_s == checker.timeout

    async def test_rate_limited_still_confirms_route(self):
        checker = ModelHealthChecker()
        llm = AsyncMock()
        llm.chat.side_effect = LLMProviderError(
            code=LLMErrorCode.RATE_LIMITED,
            safe_message="Too many requests",
            retryable=True,
            status_code=429,
        )

        with patch("app.services.model_health_checker.get_llm_client", return_value=llm):
            result = await checker.check_model(make_model(type=ModelType.LLM_CHAT))

        assert result.status == HealthStatus.HEALTHY
        assert result.details["warning"] == "Too many requests"
        assert result.details["status_code"] == 429

    async def test_provider_error_marks_unavailable(self):
        checker = ModelHealthChecker()
        llm = AsyncMock()
        llm.chat.side_effect = LLMProviderError(
            code=LLMErrorCode.UPSTREAM,
            safe_message="LLM provider is unavailable",
            retryable=True,
        )

        with patch("app.services.model_health_checker.get_llm_client", return_value=llm):
            result = await checker.check_model(make_model(type=ModelType.LLM_CHAT))

        assert result.status == HealthStatus.UNAVAILABLE
        assert result.error == "LLM provider is unavailable"

    async def test_timeout_is_reported(self):
        checker = ModelHealthChecker()
        llm = AsyncMock()
        llm.chat.side_effect = asyncio.TimeoutError()

        with patch("app.services.model_health_checker.get_llm_client", return_value=llm):
            result = await checker.check_model(make_model(type=ModelType.LLM_CHAT))

        assert result.status == HealthStatus.UNAVAILABLE
        assert f"Timeout after {checker.timeout}s" in result.error

    async def test_unexpected_exception_is_contained(self):
        checker = ModelHealthChecker()
        llm = AsyncMock()
        llm.chat.side_effect = RuntimeError("boom")

        with patch("app.services.model_health_checker.get_llm_client", return_value=llm):
            result = await checker.check_model(make_model(type=ModelType.LLM_CHAT))

        assert result.status == HealthStatus.UNAVAILABLE
        assert "boom" in result.error


class TestCheckEmbedding:
    async def test_openai_compatible_success(self):
        checker = ModelHealthChecker()
        response = http_response(
            200,
            {"model": "text-embedding-3-small", "data": [{"embedding": [0.1, 0.2, 0.3]}], "usage": {}},
        )
        patcher, client = patched_http_client(response=response)

        with patcher:
            result = await checker.check_model(make_model(type=ModelType.EMBEDDING, base_url="http://emb:8080/v1"))

        assert result.status == HealthStatus.HEALTHY
        assert result.details["dimensions"] == 3
        url = client.post.call_args.args[0]
        assert url == "http://emb:8080/v1/embeddings"

    async def test_auth_header_attached(self):
        checker = ModelHealthChecker()
        session = AsyncMock()
        creds = DecryptedCredentials(
            auth_type="api_key",
            payload={"api_key": "sk-secret"},
            credential_id=uuid4(),
            owner_type="platform",
        )
        response = http_response(200, {"data": [{"embedding": [0.5]}]})
        patcher, client = patched_http_client(response=response)

        with patcher, patch("app.services.model_health_checker.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials = AsyncMock(return_value=creds)
            await checker.check_model(
                make_model(type=ModelType.EMBEDDING, base_url="http://emb:8080", instance_id=uuid4()),
                session,
            )

        headers = client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-secret"

    async def test_authentication_failure(self):
        checker = ModelHealthChecker()
        patcher, _ = patched_http_client(response=http_response(401))

        with patcher:
            result = await checker.check_model(make_model(type=ModelType.EMBEDDING, base_url="http://emb:8080"))

        assert result.status == HealthStatus.UNAVAILABLE
        assert "Authentication failed" in result.error

    async def test_http_error_with_json_body(self):
        checker = ModelHealthChecker()
        response = http_response(500, {"error": {"message": "model overloaded"}})
        patcher, _ = patched_http_client(response=response)

        with patcher:
            result = await checker.check_model(make_model(type=ModelType.EMBEDDING, base_url="http://emb:8080"))

        assert result.status == HealthStatus.UNAVAILABLE
        assert "HTTP 500" in result.error
        assert "model overloaded" in result.error

    async def test_no_base_url(self):
        checker = ModelHealthChecker()

        result = await checker.check_model(make_model(type=ModelType.EMBEDDING))

        assert result.status == HealthStatus.UNAVAILABLE
        assert "No base URL configured" in result.error

    async def test_local_embedding_service(self):
        checker = ModelHealthChecker()
        response = http_response(200, {"vectors": [[0.1, 0.2]], "dim": 2})
        patcher, client = patched_http_client(response=response)

        with patcher:
            result = await checker.check_model(
                make_model(type=ModelType.EMBEDDING, connector="local_emb_http", base_url="http://local-emb:9100")
            )

        assert result.status == HealthStatus.HEALTHY
        assert result.details["dimensions"] == 2
        url = client.post.call_args.args[0]
        assert url == "http://local-emb:9100/embed"
        payload = client.post.call_args.kwargs["json"]
        assert payload == {"text": "test"}


class TestCheckReranker:
    async def test_success(self):
        checker = ModelHealthChecker()
        patcher, _ = patched_http_client(response=http_response(200, {"results": []}))

        with patcher:
            result = await checker.check_model(make_model(type=ModelType.RERANKER, base_url="http://rerank:8080"))

        assert result.status == HealthStatus.HEALTHY
        assert result.details["endpoint"] == "http://rerank:8080"

    async def test_alias_and_settings_candidates_are_tried(self):
        checker = ModelHealthChecker()
        # Both primary candidates fail; only the settings fallback answers.
        responses = [
            http_response(503),
            http_response(503),
            http_response(200, {"results": []}),
        ]
        patcher, client = patched_http_client(post_side_effect=responses)

        with patcher, patch.object(checker.settings, "RERANK_SERVICE_URL", "http://fallback:9090"):
            result = await checker.check_model(
                make_model(type=ModelType.RERANKER, base_url="http://reranker:8080")
            )

        assert result.status == HealthStatus.HEALTHY
        assert result.details["endpoint"] == "http://fallback:9090"
        attempted = [call.args[0] for call in client.post.call_args_list]
        assert "http://reranker:8080/rerank" in attempted  # primary
        assert "http://rerank:8080/rerank" in attempted  # alias candidate
        assert "http://fallback:9090/rerank" in attempted  # settings candidate

    async def test_all_candidates_fail(self):
        checker = ModelHealthChecker()
        patcher, _ = patched_http_client(post_side_effect=[http_response(500), http_response(503)])

        with patcher, patch.object(checker.settings, "RERANK_SERVICE_URL", "http://fallback:9090"):
            result = await checker.check_model(
                make_model(type=ModelType.RERANKER, base_url="http://rerank:8080")
            )

        assert result.status == HealthStatus.UNAVAILABLE
        assert "HTTP 500" in result.error
        assert "HTTP 503" in result.error

    async def test_no_base_url(self):
        checker = ModelHealthChecker()

        result = await checker.check_model(make_model(type=ModelType.RERANKER))

        assert result.status == HealthStatus.UNAVAILABLE
        assert "No base URL configured" in result.error


class TestCheckHttpEndpoint:
    async def test_healthcheck_path_success(self):
        checker = ModelHealthChecker()
        client = AsyncMock()
        client.get.return_value = http_response(200)
        patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))

        with patcher:
            result = await checker._check_http_endpoint("http://svc:8080", connector="openai_http")

        assert result[0] is True
        assert result[1]["endpoint"] == "http://svc:8080/health"

    async def test_falls_back_to_root(self):
        checker = ModelHealthChecker()
        client = AsyncMock()
        client.get.side_effect = [http_response(404), http_response(404)]
        patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))

        with patcher:
            ok, details = await checker._check_http_endpoint("http://svc:8080", connector="openai_http")

        assert ok is True
        assert details["endpoint"] == "http://svc:8080"

    async def test_server_error_on_root(self):
        checker = ModelHealthChecker()
        client = AsyncMock()
        client.get.side_effect = [http_response(404), http_response(500)]
        patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))

        with patcher:
            ok, details = await checker._check_http_endpoint("http://svc:8080", connector="openai_http")

        assert ok is False
        assert "HTTP 500" in details["error"]

    async def test_connect_error(self):
        import httpx

        checker = ModelHealthChecker()
        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("refused")
        patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))

        with patcher:
            ok, details = await checker._check_http_endpoint("http://svc:8080", connector="openai_http")

        assert ok is False
        assert "Cannot connect" in details["error"]

    async def test_unknown_model_type_uses_http_endpoint(self):
        checker = ModelHealthChecker()
        client = AsyncMock()
        client.get.return_value = http_response(200)
        patcher = patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=client)))

        # Emulate a model type without a dedicated branch (falls through to HTTP check).
        model = make_model(base_url="http://svc:8080")
        model.type = "some_future_type"
        with patcher:
            result = await checker.check_model(model)

        assert result.status == HealthStatus.HEALTHY
        assert result.details["endpoint"] == "http://svc:8080/health"

    async def test_unknown_model_type_without_base_url(self):
        checker = ModelHealthChecker()
        model = make_model()
        model.type = "some_future_type"

        result = await checker.check_model(model)

        assert result.status == HealthStatus.UNAVAILABLE
        assert "No base URL configured" in result.error
