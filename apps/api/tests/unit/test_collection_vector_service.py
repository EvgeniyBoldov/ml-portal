from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.collection_vector_service import CollectionVectorService


class _FakeQdrantClient:
    def __init__(self, collections=None, search_results=None):
        self._collections = collections or []
        self._search_results = search_results or []
        self.create_collection_calls = []
        self.delete_collection_calls = []
        self.upsert_calls = []

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in self._collections])

    def create_collection(self, collection_name, vectors_config):
        self.create_collection_calls.append((collection_name, vectors_config))

    def delete_collection(self, collection_name):
        self.delete_collection_calls.append(collection_name)

    def upsert(self, collection_name, points):
        self.upsert_calls.append((collection_name, points))

    def search(self, collection_name, query_vector, query_filter, limit):
        return self._search_results


@pytest.mark.asyncio
async def test_create_qdrant_collection_when_missing():
    client = _FakeQdrantClient(collections=[])
    service = CollectionVectorService(session=MagicMock(), qdrant_client=client)
    collection = SimpleNamespace(qdrant_collection_name="coll_docs")

    await service.create_qdrant_collection(collection, vector_size=768)

    assert len(client.create_collection_calls) == 1
    assert client.create_collection_calls[0][0] == "coll_docs"


@pytest.mark.asyncio
async def test_index_row_upserts_points_for_vector_fields():
    client = _FakeQdrantClient()
    service = CollectionVectorService(session=MagicMock(), qdrant_client=client)
    collection = SimpleNamespace(
        qdrant_collection_name="coll_docs",
        vector_fields=[{"name": "body"}],
    )

    chunk_count = await service.index_row(
        collection=collection,
        row_id="row-1",
        row_data={"body": "hello", "vendor": "acme"},
        embeddings={"body": [[0.1, 0.2, 0.3]]},
    )

    assert chunk_count == 1
    assert len(client.upsert_calls) == 1
    collection_name, points = client.upsert_calls[0]
    assert collection_name == "coll_docs"
    assert points[0].payload["row_id"] == "row-1"
    assert points[0].payload["field_name"] == "body"
    assert points[0].payload["text"] == "hello"
    assert points[0].payload["vendor"] == "acme"


@pytest.mark.asyncio
async def test_search_similar_groups_hits_by_row_id():
    hit_a = SimpleNamespace(
        score=0.91,
        payload={"row_id": "row-1", "field_name": "body", "chunk_idx": 0, "text": "alpha", "vendor": "acme"},
    )
    hit_b = SimpleNamespace(
        score=0.95,
        payload={"row_id": "row-1", "field_name": "body", "chunk_idx": 1, "text": "beta", "vendor": "acme"},
    )
    hit_c = SimpleNamespace(
        score=0.88,
        payload={"row_id": "row-2", "field_name": "body", "chunk_idx": 0, "text": "gamma", "vendor": "beta"},
    )
    client = _FakeQdrantClient(search_results=[hit_a, hit_b, hit_c])
    service = CollectionVectorService(session=MagicMock(), qdrant_client=client)
    collection = SimpleNamespace(qdrant_collection_name="coll_docs")

    results = await service.search_similar(
        collection=collection,
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
    )

    assert [item["row_id"] for item in results] == ["row-1", "row-2"]
    assert results[0]["score"] == 0.95
    assert results[0]["payload"]["vendor"] == "acme"
