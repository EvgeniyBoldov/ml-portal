from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig
from app.models.model_registry import ModelType
from app.services.embedding_model_config_service import EmbeddingModelConfigService


def teardown_function() -> None:
    EmbeddingServiceFactory.clear_cache()


def test_get_service_raises_when_model_is_not_registered() -> None:
    with pytest.raises(RuntimeError, match="not configured or could not be resolved"):
        EmbeddingServiceFactory.get_service("missing-embedding-model")


def test_get_service_raises_for_unsupported_connector() -> None:
    EmbeddingServiceFactory.register_model(
        ModelConfig(
            alias="broken-embedding",
            provider="mystery",
            provider_model_name="broken-embedding",
            base_url="http://emb.local",
            connector="unknown_connector",
        )
    )

    with pytest.raises(RuntimeError, match="Unsupported embedding connector/provider"):
        EmbeddingServiceFactory.get_service("broken-embedding")


@pytest.mark.asyncio
async def test_config_service_registers_model_with_resolved_credentials() -> None:
    model = SimpleNamespace(
        alias="embed.default",
        type=ModelType.EMBEDDING,
        provider="openai",
        provider_model_name="text-embedding-3-small",
        connector="openai_http",
        base_url=None,
        instance=SimpleNamespace(url="https://embedding.example"),
        extra_config={"vector_dim": 1536},
        instance_id="instance-id",
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = model
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    credentials = SimpleNamespace(
        auth_type="api_key",
        payload={"api_key": "secret"},
    )

    with patch.object(EmbeddingServiceFactory, "list_available_models", return_value=[]), \
         patch.object(EmbeddingServiceFactory, "register_model") as register_model, \
         patch("app.services.embedding_model_config_service.CredentialService") as credential_service:
        credential_service.return_value.resolve_credentials = AsyncMock(return_value=credentials)

        await EmbeddingModelConfigService.ensure_registered(session, model.alias)

    config = register_model.call_args.args[0]
    assert config.alias == model.alias
    assert config.base_url == "https://embedding.example"
    assert config.api_key == "secret"
    assert config.dimensions == 1536
    credential_service.return_value.resolve_credentials.assert_awaited_once_with(
        instance_id="instance-id",
        strategy="PLATFORM_FIRST",
    )


@pytest.mark.asyncio
async def test_config_service_rejects_unknown_model() -> None:
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    with patch.object(EmbeddingServiceFactory, "list_available_models", return_value=[]), \
         pytest.raises(RuntimeError, match="Embedding model 'missing' is not configured"):
        await EmbeddingModelConfigService.ensure_registered(session, "missing")
