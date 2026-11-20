from __future__ import annotations


import pytest

from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig
from app.services.embedding_model_config_service import EmbeddingModelConfigService


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
async def test_discovery_persists_the_same_characteristics_used_by_indexing(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.services import model_metadata_service
    model = SimpleNamespace(alias='discovery-test', provider='local', connector='local_emb_http',
                            provider_model_name='encoder', base_url='http://encoder', instance_id=None,
                            extra_config={}, embedding_dimensions=None, max_input_tokens=None,
                            model_version=None, vector_normalized=None)
    session = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    result = MagicMock()
    result.scalars.return_value.first.return_value = model
    session.execute.return_value = result
    monkeypatch.setattr(model_metadata_service, '_probe_manifest', AsyncMock(return_value=(
        {'alias':'encoder', 'dimensions':1024, 'max_tokens':8192, 'version':'v2', 'normalized':True}, 'healthy')))
    await EmbeddingModelConfigService.ensure_registered(session, model.alias)
    assert model.embedding_dimensions == 1024
    assert model.max_input_tokens == 8192
    assert model.extra_config['manifest']['version'] == 'v2'
    assert model.capabilities_checked_at is not None
    assert EmbeddingServiceFactory.get_service(model.alias).get_model_info().dimensions == 1024
