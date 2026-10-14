from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.embeddings import ModelConfig, EmbeddingServiceFactory, validate_embedding_batch
from app.services.model_capabilities import ModelCapabilities, embedding_fingerprint, normalize_capability_payload
from app.services.vector_index_service import VectorIndexService, VectorIndexTarget, physical_index_name


def model(**overrides):
    return SimpleNamespace(id=uuid4(), alias="encoder", provider_model_name="bge-m3", model_version="v1",
                           embedding_dimensions=1024, max_input_tokens=8192, vector_normalized=True, extra_config={}, **overrides)


def test_unknown_dimension_is_an_error_not_384():
    m = model()
    m.embedding_dimensions = None
    with pytest.raises(ValueError, match="unknown"):
        embedding_fingerprint(m)


def test_vector_identity_is_independent_of_health_default_and_model_order():
    m = model()
    before = embedding_fingerprint(m)
    m.default_for_type = True
    m.health_latency_ms = 42
    m.extra_config = {"manifest": {"_health": {"latency_ms": 99}}}
    assert embedding_fingerprint(m) == before
    m.embedding_dimensions = 384
    assert embedding_fingerprint(m) != before
    m.embedding_dimensions = 1024
    m.model_version = "v2"
    assert embedding_fingerprint(m) != before


def test_same_dimension_different_models_have_separate_spaces():
    a, b = model(), model()
    assert physical_index_name("coll_test", embedding_fingerprint(a)) != physical_index_name("coll_test", embedding_fingerprint(b))


def test_legacy_config_is_translated_to_typed_capabilities():
    data = normalize_capability_payload({"type": "embedding", "extra_config": {"vector_dim": 1024, "max_tokens": 8192, "transport": "http"}})
    assert data["embedding_dimensions"] == 1024
    assert data["max_input_tokens"] == 8192
    assert data["extra_config"] == {"transport": "http"}
    data = normalize_capability_payload({"type": "embedding", "embedding_dimensions": 384, "extra_config": {"vector_dim": 1024}})
    assert data["embedding_dimensions"] == 384


def test_reranker_does_not_get_a_zero_dimension_vector():
    caps = ModelCapabilities.from_manifest({"dimensions": 0, "max_tokens": 1024, "version": "v1"}, embedding=False)
    assert caps.embedding_dimensions is None
    assert caps.max_input_tokens == 1024


@pytest.mark.parametrize("vectors,count,dim", [([[0.0]*384], 1, 1024), ([], 1, 384), ([[float('nan')]], 1, 1)])
def test_embedding_response_is_validated_before_indexing(vectors, count, dim):
    with pytest.raises(ValueError):
        validate_embedding_batch(vectors, count, dim)


def test_configuration_cache_refreshes_on_semantic_change_only():
    config = ModelConfig(alias="test-cache", provider="local", provider_model_name="encoder", base_url="http://encoder", dimensions=384, max_tokens=256)
    EmbeddingServiceFactory.register_model(config)
    first = EmbeddingServiceFactory.get_service(config.alias)
    EmbeddingServiceFactory.register_model(config)
    assert EmbeddingServiceFactory.get_service(config.alias) is first
    config2 = ModelConfig(alias=config.alias, provider="local", provider_model_name="encoder", base_url="http://encoder", dimensions=1024, max_tokens=8192)
    EmbeddingServiceFactory.register_model(config2)
    assert EmbeddingServiceFactory.get_service(config.alias) is not first


@pytest.mark.asyncio
async def test_legacy_search_requires_matching_dimension_alias_and_version():
    target = VectorIndexTarget("bge", "canonical", 1024, "identity", "v1", "identity")
    store = SimpleNamespace(collection_exists=AsyncMock(return_value=True), vector_dimension=AsyncMock(side_effect=[384, 1024]))
    candidates = await VectorIndexService(MagicMock()).search_targets("coll_test", target, store)
    assert candidates == [("canonical", None), ("coll_test__bge", {"must": [("embed_model_alias", "bge"), ("version", "v1")]})]
    store.vector_dimension.reset_mock()
    target = VectorIndexTarget("bge", "canonical", 1024, "identity", "")
    assert await VectorIndexService(MagicMock()).search_targets("coll_test", target, store) == [("canonical", None)]
    store.vector_dimension.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_target_does_not_depend_on_primary_encoder(monkeypatch):
    m = model()
    session = SimpleNamespace(scalar=AsyncMock(return_value=m))
    from app.services.embedding_model_config_service import EmbeddingModelConfigService
    monkeypatch.setattr(EmbeddingModelConfigService, "ensure_registered", AsyncMock())
    monkeypatch.setattr(EmbeddingServiceFactory, "get_service", lambda _: SimpleNamespace(get_model_info=lambda: SimpleNamespace(dimensions=1024, version="v1")))
    resolver = VectorIndexService(session)
    target = await resolver.resolve("coll_test", m.alias)
    m.default_for_type = True
    assert await resolver.resolve("coll_test", m.alias) == target
    assert target.dimensions == 1024


def test_rank_fusion_does_not_let_one_encoders_score_scale_dominate():
    from app.services.vector_rank_fusion import fuse_vector_hits
    hits = [
        {"id":"a", "score":0.01, "payload":{"chunk_id":"a", "embed_model_alias":"encoder-a"}},
        {"id":"common", "score":0.009, "payload":{"chunk_id":"common", "embed_model_alias":"encoder-a"}},
        {"id":"b", "score":0.99, "payload":{"chunk_id":"b", "embed_model_alias":"encoder-b"}},
        {"id":"common", "score":0.98, "payload":{"chunk_id":"common", "embed_model_alias":"encoder-b"}},
    ]
    ranked = fuse_vector_hits(hits)
    assert ranked[0]["id"] == "common"
    assert ranked[1]["score"] == ranked[2]["score"]
    # The same encoder in both canonical and legacy indexes has only one vote.
    assert fuse_vector_hits(hits + hits) == ranked


def test_status_marks_a_dimension_change_stale_even_when_version_string_is_unchanged():
    from app.services.rag_status_manager import RAGStatusManager
    details = {"policy":"all_index_ready"}
    node = SimpleNamespace(node_key="encoder", model_version="v1", metrics_json={"embedding_fingerprint":"old"})
    RAGStatusManager._annotate_stale_models(details, [node], {"encoder":"v1"}, ["encoder"], {"encoder":"new"})
    assert details["stale_models"] == ["encoder"]
    assert details["policy"] == "index_ready_but_stale"


@pytest.mark.asyncio
async def test_cached_index_is_rebuilt_when_physical_points_are_missing():
    target = VectorIndexTarget('encoder', 'physical', 384, 'current', 'v1')
    cached = {'embedding_fingerprint':'current', 'embeddings_key':'artifact', 'indexed_count':5}
    store = SimpleNamespace(collection_exists=AsyncMock(return_value=False), count_by_filter=AsyncMock(return_value=3))
    assert not await VectorIndexService.cache_is_current(target, cached, 'artifact', store, 'source', 'tenant')
    store.count_by_filter.assert_not_awaited()
    store.collection_exists.return_value = True
    assert not await VectorIndexService.cache_is_current(target, cached, 'artifact', store, 'source', 'tenant')
    store.count_by_filter.return_value = 5
    assert await VectorIndexService.cache_is_current(target, cached, 'artifact', store, 'source', 'tenant')
    assert not await VectorIndexService.cache_is_current(target, cached, 'different-input', store, 'source', 'tenant')
