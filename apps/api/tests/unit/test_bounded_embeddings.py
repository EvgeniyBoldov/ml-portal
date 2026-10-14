from types import SimpleNamespace
import pytest
from app.services.bounded_embeddings import embed_texts_bounded, split_embedding_text


def test_segments_preserve_full_unicode_text_with_byte_limit():
    text = 'Настройка маршрутизатора 🛰️ ' * 40
    segments = split_embedding_text(text, 64)
    assert ''.join(segments) == text
    assert all(len(part.encode('utf-8')) <= 48 for part in segments)


def test_embedding_long_text_does_not_discard_tail_or_change_result_count():
    seen = []
    def embed(texts):
        seen.extend(texts)
        return [[1.0, 0.0] for _ in texts]
    service = SimpleNamespace(get_model_info=lambda: SimpleNamespace(max_tokens=64, dimensions=2), embed_texts=embed)
    texts = ['Кириллица и эмодзи 😀 ' * 30, 'short']
    assert embed_texts_bounded(service, texts) == [[1.0, 0.0], [1.0, 0.0]]
    assert ''.join(seen) == ''.join(texts)


def test_incomplete_embedding_batch_is_rejected():
    service = SimpleNamespace(get_model_info=lambda: SimpleNamespace(max_tokens=64, dimensions=2), embed_texts=lambda _: [])
    with pytest.raises(ValueError, match='expected'):
        embed_texts_bounded(service, ['text'])


def test_service_version_change_requires_verification_before_indexing(httpx_mock):
    from app.adapters.embeddings import LocalEmbeddingServiceProvider
    httpx_mock.add_response(method='POST', url='http://encoder/embed',
                           json={'vectors':[[0.0, 1.0]], 'model_version':'v2'})
    service = LocalEmbeddingServiceProvider('encoder', 'encoder', 'http://encoder', dimensions=2, max_tokens=64, model_version='v1')
    with pytest.raises(ValueError, match='version changed'):
        service.embed_text('text')
