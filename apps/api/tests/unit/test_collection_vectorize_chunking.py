from app.workers.tasks_collection_vectorize import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    _chunk_text_for_embedding,
    _needs_revectorization_for_model,
    _needs_revectorization_for_models,
    _resolve_chunk_config,
)
from app.services.collection.vector_lifecycle import (
    build_model_scoped_qdrant_collections,
    get_vector_config_model_aliases,
)


def test_resolve_chunk_config_defaults_for_non_dict():
    size, overlap = _resolve_chunk_config(None)
    assert size == DEFAULT_CHUNK_SIZE
    assert overlap == DEFAULT_CHUNK_OVERLAP


def test_resolve_chunk_config_clamps_values():
    size, overlap = _resolve_chunk_config({"chunk_size": 50, "overlap": 9999})
    assert size >= 200
    assert overlap == size - 1


def test_chunk_text_for_embedding_single_chunk_when_short():
    chunks = _chunk_text_for_embedding("hello world", chunk_size=100, overlap=10)
    assert chunks == ["hello world"]


def test_chunk_text_for_embedding_produces_overlapping_chunks():
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = _chunk_text_for_embedding(text, chunk_size=10, overlap=2)
    assert chunks == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]


def test_needs_revectorization_for_model_when_alias_changed():
    assert _needs_revectorization_for_model({"embed_model_alias": "a"}, "b") is True
    assert _needs_revectorization_for_model({"embed_model_alias": "a"}, "a") is False
    assert _needs_revectorization_for_model(None, "a") is True


def test_needs_revectorization_for_models_uses_multi_model_contract():
    assert _needs_revectorization_for_models(
        {"embed_model_aliases": ["emb-default", "emb-tenant"]},
        ["emb-default", "emb-tenant"],
    ) is False
    assert _needs_revectorization_for_models(
        {"embed_model_aliases": ["emb-default"]},
        ["emb-default", "emb-tenant"],
    ) is True


def test_get_vector_config_model_aliases_reads_legacy_and_new_fields():
    assert get_vector_config_model_aliases({"embed_model_aliases": ["a", "b", "a"]}) == ["a", "b"]
    assert get_vector_config_model_aliases({"embed_model_alias": "legacy"}) == ["legacy"]
    assert get_vector_config_model_aliases(None) == []


def test_build_model_scoped_qdrant_collections_keeps_primary_unsuffixed():
    assert build_model_scoped_qdrant_collections("coll_test", ["emb-default", "emb-tenant"]) == [
        ("emb-default", "coll_test"),
        ("emb-tenant", "coll_test__emb-tenant"),
    ]
