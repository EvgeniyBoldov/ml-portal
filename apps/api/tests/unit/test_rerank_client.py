from types import SimpleNamespace

from app.agents.runtime.rerank_client import RerankScoredIndex, apply_rerank_to_items
from app.agents.runtime.rerank_client import _build_rerank_candidate_urls


def test_apply_rerank_to_items_reorders_and_overrides_score():
    items = [
        {"id": "a", "score": 0.9},
        {"id": "b", "score": 0.8},
        {"id": "c", "score": 0.7},
    ]
    reranked = [
        RerankScoredIndex(index=2, score=1.7),
        RerankScoredIndex(index=0, score=1.2),
    ]

    result = apply_rerank_to_items(items, reranked, score_field="score")

    assert [entry["id"] for entry in result] == ["c", "a", "b"]
    assert result[0]["score"] == 1.7
    assert result[1]["score"] == 1.2
    assert result[2]["score"] == 0.8


def test_apply_rerank_to_items_ignores_invalid_indexes():
    items = [
        {"id": "x", "score": 0.6},
        {"id": "y", "score": 0.5},
    ]
    reranked = [
        RerankScoredIndex(index=42, score=10.0),
        RerankScoredIndex(index=-1, score=9.0),
        RerankScoredIndex(index=1, score=1.1),
    ]

    result = apply_rerank_to_items(items, reranked, score_field="score")

    assert [entry["id"] for entry in result] == ["y", "x"]
    assert result[0]["score"] == 1.1
    assert result[1]["score"] == 0.6


def test_build_rerank_candidate_urls_supports_legacy_service_name():
    model = SimpleNamespace(
        base_url="http://reranker:8002",
        instance=None,
        extra_config=None,
    )

    urls = _build_rerank_candidate_urls(model, "http://rerank:8002")

    assert urls == ["http://reranker:8002", "http://rerank:8002"]
