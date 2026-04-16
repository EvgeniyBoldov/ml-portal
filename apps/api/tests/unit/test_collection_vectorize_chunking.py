from app.workers.tasks_collection_vectorize import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    _chunk_text_for_embedding,
    _needs_revectorization_for_model,
    _resolve_chunk_config,
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
