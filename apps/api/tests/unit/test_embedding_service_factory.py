from __future__ import annotations

import pytest

from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig


def teardown_function() -> None:
    EmbeddingServiceFactory.clear_cache()


def test_get_service_raises_when_model_is_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        EmbeddingServiceFactory,
        "_load_model_config_sync",
        classmethod(lambda cls, model_alias: None),
    )

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
