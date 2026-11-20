from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.collection_service import CollectionService


@pytest.mark.asyncio
async def test_provision_qdrant_collection_uses_configured_model_dimensions(monkeypatch):
    service = CollectionService(session=MagicMock())

    monkeypatch.setattr(
        service.vector,
        "resolve_target_vector_models",
        AsyncMock(return_value=["emb-default"]),
    )
    from app.services.vector_index_service import VectorIndexService, VectorIndexTarget
    monkeypatch.setattr(VectorIndexService, "resolve_many", AsyncMock(return_value=[
        VectorIndexTarget("emb-default", "vi_test_identity", 1024, "identity", "v1")]))

    ensure_collection = AsyncMock()

    class FakeQdrantVectorStore:
        async def ensure_collection(self, name: str, dim: int) -> None:
            await ensure_collection(name, dim)

    monkeypatch.setattr("app.adapters.impl.qdrant.QdrantVectorStore", FakeQdrantVectorStore)

    await service._provision_qdrant_collection(uuid4(), "coll_test_vector")

    ensure_collection.assert_awaited_once_with("vi_test_identity", 1024)


@pytest.mark.asyncio
async def test_provision_qdrant_collection_requires_configured_model(monkeypatch):
    service = CollectionService(session=MagicMock())

    monkeypatch.setattr(
        service.vector,
        "resolve_target_vector_models",
        AsyncMock(return_value=None),
    )

    ensure_collection = AsyncMock()

    class FakeQdrantVectorStore:
        async def ensure_collection(self, name: str, dim: int) -> None:
            await ensure_collection(name, dim)

    monkeypatch.setattr("app.adapters.impl.qdrant.QdrantVectorStore", FakeQdrantVectorStore)

    with pytest.raises(RuntimeError, match="No embedding target models resolved"):
        await service._provision_qdrant_collection(uuid4(), "coll_test_vector")

    ensure_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_collection_deletes_db_row_before_best_effort_cleanup(monkeypatch):
    session = MagicMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    service = CollectionService(session=session)
    tenant_id = uuid4()
    collection = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        slug="docs",
        collection_type="table",
        table_name="coll_test_docs",
        qdrant_collection_name="coll_test_docs",
        vector_config={},
    )

    monkeypatch.setattr(service, "get_by_slug", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        "app.adapters.impl.qdrant.QdrantVectorStore",
        lambda: SimpleNamespace(
            collection_exists=AsyncMock(return_value=True),
            delete_collection=AsyncMock(),
        ),
    )

    result = await service.delete_collection("docs")

    assert result is True
    session.delete.assert_awaited_once_with(collection)
    session.flush.assert_awaited_once()
    assert any(
        "DROP TABLE IF EXISTS coll_test_docs CASCADE" in str(item.args[0])
        for item in session.execute.await_args_list
    )
