from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import CollectionNotFoundError, NotDocumentCollectionError
from app.models.collection import CollectionType
from app.services.collection_document_ingest_service import CollectionDocumentUploadService


class _FakeCollectionService:
    def __init__(self, session):
        self.session = session

    async def sync_collection_status(self, collection, persist: bool = False):
        return {"status": "uploaded", "details": {"persist": persist}}


@pytest.mark.asyncio
async def test_upload_document_happy_path(monkeypatch):
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()

    collection = SimpleNamespace(
        id=uuid4(),
        tenant_id=repo_factory.tenant_id,
        collection_type=CollectionType.DOCUMENT.value,
        qdrant_collection_name="coll_docs",
        table_name="coll_docs",
        fields=[],
        total_rows=0,
    )

    service = CollectionDocumentUploadService(session=session, repo_factory=repo_factory, event_publisher=None)

    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.CollectionService",
        _FakeCollectionService,
    )
    monkeypatch.setattr(service, "_get_document_collection", AsyncMock(return_value=collection))
    monkeypatch.setattr(service, "_upload_to_s3", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_insert_collection_row", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.get_settings",
        lambda: SimpleNamespace(S3_BUCKET_RAG="rag"),
    )

    result = await service.upload_document(
        collection_id=collection.id,
        file_content=b"hello world",
        filename="doc.txt",
        user_id=uuid4(),
        content_type="text/plain",
        title="Doc",
        source="kb",
        scope="docs",
        tags=["tag-a"],
    )

    assert result["status"] == "uploaded"
    assert result["collection_id"] == str(collection.id)
    assert result["row_id"]
    session.add.assert_called()
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_upload_document_cleans_up_s3_on_failure(monkeypatch):
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()

    collection = SimpleNamespace(
        id=uuid4(),
        tenant_id=repo_factory.tenant_id,
        collection_type=CollectionType.DOCUMENT.value,
        qdrant_collection_name="coll_docs",
        table_name="coll_docs",
        fields=[],
        total_rows=0,
    )

    service = CollectionDocumentUploadService(session=session, repo_factory=repo_factory, event_publisher=None)

    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.CollectionService",
        _FakeCollectionService,
    )
    monkeypatch.setattr(service, "_get_document_collection", AsyncMock(return_value=collection))
    monkeypatch.setattr(service, "_upload_to_s3", AsyncMock(return_value=True))
    monkeypatch.setattr(
        service,
        "_insert_collection_row",
        AsyncMock(side_effect=RuntimeError("db boom")),
    )
    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.get_settings",
        lambda: SimpleNamespace(S3_BUCKET_RAG="rag"),
    )
    delete_object = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.collection_document_ingest_service.s3_manager.delete_object", delete_object)

    with pytest.raises(RuntimeError, match="db boom"):
        await service.upload_document(
            collection_id=collection.id,
            file_content=b"hello world",
            filename="doc.txt",
            user_id=uuid4(),
        )

    delete_object.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_document_collection_rejects_wrong_type(monkeypatch):
    session = MagicMock()
    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()
    service = CollectionDocumentUploadService(session=session, repo_factory=repo_factory)

    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.CollectionService",
        lambda _session: SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(collection_type=CollectionType.TABLE.value))),
    )

    with pytest.raises(NotDocumentCollectionError):
        await service._get_document_collection(uuid4())


@pytest.mark.asyncio
async def test_get_document_collection_missing_raises(monkeypatch):
    session = MagicMock()
    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()
    service = CollectionDocumentUploadService(session=session, repo_factory=repo_factory)

    monkeypatch.setattr(
        "app.services.collection_document_ingest_service.CollectionService",
        lambda _session: SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
    )

    with pytest.raises(CollectionNotFoundError):
        await service._get_document_collection(uuid4())
