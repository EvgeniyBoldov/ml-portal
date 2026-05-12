from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapters.impl.qdrant import QdrantVectorStore


@pytest.mark.asyncio
async def test_search_uses_query_points_and_maps_scored_points() -> None:
    store = QdrantVectorStore(url="http://qdrant:6333")

    fake_points = [
        SimpleNamespace(id="p1", score=0.91, payload={"text": "alpha"}),
        SimpleNamespace(id="p2", score=0.75, payload={"text": "beta"}),
    ]

    class FakeClient:
        async def query_points(self, **kwargs):  # noqa: ANN003
            assert kwargs["collection_name"] == "coll_a"
            assert kwargs["query"] == [0.1, 0.2]
            assert kwargs["limit"] == 3
            assert kwargs["with_payload"] is True
            return SimpleNamespace(points=fake_points)

    store._client = FakeClient()  # noqa: SLF001
    result = await store.search("coll_a", [0.1, 0.2], top_k=3)

    assert result == [
        {"id": "p1", "score": 0.91, "payload": {"text": "alpha"}},
        {"id": "p2", "score": 0.75, "payload": {"text": "beta"}},
    ]


@pytest.mark.asyncio
async def test_search_returns_empty_list_on_404_not_found() -> None:
    store = QdrantVectorStore(url="http://qdrant:6333")

    class FakeClient:
        async def query_points(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("404 Not Found")

    store._client = FakeClient()  # noqa: SLF001
    result = await store.search("missing_collection", [0.1, 0.2], top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_search_propagates_non_404_errors() -> None:
    store = QdrantVectorStore(url="http://qdrant:6333")

    class FakeClient:
        async def query_points(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("connection refused")

    store._client = FakeClient()  # noqa: SLF001

    with pytest.raises(RuntimeError, match="connection refused"):
        await store.search("coll_a", [0.1], top_k=1)


@pytest.mark.asyncio
async def test_search_fallbacks_to_legacy_search_when_query_points_endpoint_missing() -> None:
    store = QdrantVectorStore(url="http://qdrant:6333")

    class FakeClient:
        async def query_points(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("404 Not Found for /collections/coll_a/points/query")

        async def search(self, **kwargs):  # noqa: ANN003
            assert kwargs["collection_name"] == "coll_a"
            assert kwargs["query_vector"] == [0.1, 0.2]
            assert kwargs["limit"] == 2
            assert kwargs["with_payload"] is True
            return [
                SimpleNamespace(id="p3", score=0.66, payload={"text": "gamma"}),
            ]

    store._client = FakeClient()  # noqa: SLF001
    result = await store.search("coll_a", [0.1, 0.2], top_k=2)

    assert result == [
        {"id": "p3", "score": 0.66, "payload": {"text": "gamma"}},
    ]
