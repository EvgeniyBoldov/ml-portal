from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.routers.collections import documents as documents_router
from app.api.v1.routers.collections import stream_lifecycle as lifecycle_router


def _scalar_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


@pytest.mark.asyncio
async def test_stop_pipeline_revokes_all_active_tasks(monkeypatch):
    collection_id = uuid4()
    doc_id = str(uuid4())
    doc_uuid = uuid4()
    tenant_id = uuid4()

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=tenant_id,
        collection_type="document",
        qdrant_collection_name="coll_docs_qdrant",
    )
    fake_document = SimpleNamespace(id=doc_uuid, tenant_id=tenant_id)
    fake_repo_factory = MagicMock()

    monkeypatch.setattr(
        lifecycle_router,
        "_resolve_collection_and_doc",
        AsyncMock(return_value=(fake_collection, fake_document, doc_uuid, fake_repo_factory)),
    )
    monkeypatch.setattr(lifecycle_router, "_ensure_worker_ready", AsyncMock())

    fake_status_manager = MagicMock()
    fake_status_manager.get_ingest_policy = AsyncMock(
        return_value={
            "controls": [
                {"stage": "extract", "node_type": "pipeline", "can_stop": True},
                {"stage": "embed.emb.mini.l6", "node_type": "embedding", "can_stop": True},
            ]
        }
    )
    fake_status_manager.stop_ingest = AsyncMock(
        return_value={
            "stopped_stages": ["extract", "embed.emb.mini.l6"],
            "task_ids": ["task-1", "task-2"],
        }
    )
    monkeypatch.setattr(lifecycle_router, "RAGStatusManager", lambda *args, **kwargs: fake_status_manager)

    revoke_mock = MagicMock()
    fake_celery_app = SimpleNamespace(control=SimpleNamespace(revoke=revoke_mock))
    monkeypatch.setattr("app.celery_app.app", fake_celery_app)

    result = await lifecycle_router.stop_collection_ingest(
        collection_id=collection_id,
        doc_id=doc_id,
        stage="pipeline",
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), role="admin"),
        redis=MagicMock(),
    )

    assert result["status"] == "success"
    assert result["stage"] == "pipeline"
    assert result["stopped_stages"] == ["extract", "embed.emb.mini.l6"]
    assert revoke_mock.call_count == 2
    revoke_mock.assert_any_call("task-1", terminate=True, signal="SIGTERM")
    revoke_mock.assert_any_call("task-2", terminate=True, signal="SIGTERM")


@pytest.mark.asyncio
async def test_delete_documents_stops_ingest_before_delete(monkeypatch):
    collection_id = uuid4()
    tenant_id = uuid4()
    doc_id = uuid4()
    row_id = "row-1"

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=tenant_id,
        collection_type="document",
        table_name="coll_docs",
        qdrant_collection_name="coll_docs_qdrant",
        total_rows=5,
        is_remote=False,
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_collection",
        AsyncMock(return_value=fake_collection),
    )

    fake_source = SimpleNamespace(
        source_id=doc_id,
        meta={
            "collection": {"id": str(collection_id), "row_id": row_id},
            "artifacts": {"original": {"key": "t/doc/original.txt"}},
        },
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_document_membership",
        AsyncMock(return_value=SimpleNamespace(source=fake_source, in_tenant=True, in_collection=True)),
    )
    fake_doc = SimpleNamespace(id=doc_id)

    execute_results = [
        SimpleNamespace(),  # delete table row
        SimpleNamespace(),  # delete rag status
        SimpleNamespace(),  # delete membership row
        _scalar_result(fake_doc),  # doc_q
    ]
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(side_effect=execute_results)

    fake_status_manager = MagicMock()
    fake_status_manager.stop_ingest = AsyncMock(
        return_value={"stopped_stages": ["extract"], "task_ids": ["task-del-1"]}
    )
    monkeypatch.setattr(documents_router, "RAGStatusManager", lambda *args, **kwargs: fake_status_manager)

    revoke_mock = MagicMock()
    fake_celery_app = SimpleNamespace(control=SimpleNamespace(revoke=revoke_mock))
    monkeypatch.setattr("app.celery_app.app", fake_celery_app)

    monkeypatch.setattr(documents_router.s3_manager, "delete_object", AsyncMock())
    monkeypatch.setattr(documents_router.s3_manager, "delete_folder", AsyncMock())
    monkeypatch.setattr(documents_router, "_cleanup_document_vectors", AsyncMock())

    fake_collection_service = MagicMock()
    fake_collection_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(documents_router, "CollectionService", lambda _session: fake_collection_service)

    result = await documents_router.delete_collection_documents(
        collection_id=collection_id,
        doc_ids=[str(doc_id)],
        session=fake_session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    assert result["deleted"] == 1
    fake_status_manager.stop_ingest.assert_awaited_once_with(doc_id)
    revoke_mock.assert_called_once_with("task-del-1", terminate=True, signal="SIGTERM")
    documents_router._cleanup_document_vectors.assert_awaited_once_with(fake_collection.qdrant_collection_name, doc_id)
    assert result["skipped_foreign"] == []
    assert result["failed"] == []


@pytest.mark.asyncio
async def test_delete_documents_skips_foreign_collection_document(monkeypatch):
    collection_id = uuid4()
    tenant_id = uuid4()
    doc_id = uuid4()
    other_collection_id = uuid4()

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=tenant_id,
        collection_type="document",
        table_name="coll_docs",
        qdrant_collection_name="coll_docs_qdrant",
        total_rows=5,
        is_remote=False,
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_collection",
        AsyncMock(return_value=fake_collection),
    )

    foreign_source = SimpleNamespace(
        source_id=doc_id,
        meta={"collection": {"id": str(other_collection_id)}},
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_document_membership",
        AsyncMock(return_value=SimpleNamespace(source=foreign_source, in_tenant=True, in_collection=False)),
    )

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()

    fake_status_manager = MagicMock()
    fake_status_manager.stop_ingest = AsyncMock(return_value={"stopped_stages": [], "task_ids": []})
    monkeypatch.setattr(documents_router, "RAGStatusManager", lambda *args, **kwargs: fake_status_manager)

    result = await documents_router.delete_collection_documents(
        collection_id=collection_id,
        doc_ids=[str(doc_id)],
        session=fake_session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    assert result["deleted"] == 0
    assert result["skipped_foreign"] == [str(doc_id)]
    fake_status_manager.stop_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_delete_documents_deletes_orphan_without_source(monkeypatch):
    collection_id = uuid4()
    tenant_id = uuid4()
    doc_id = uuid4()

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=tenant_id,
        collection_type="document",
        table_name="coll_docs",
        qdrant_collection_name="coll_docs_qdrant",
        total_rows=5,
        is_remote=False,
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_collection",
        AsyncMock(return_value=fake_collection),
    )
    monkeypatch.setattr(
        documents_router,
        "_resolve_document_membership",
        AsyncMock(return_value=SimpleNamespace(source=None, in_tenant=False, in_collection=False)),
    )

    doc_row = SimpleNamespace(id=doc_id, tenant_id=tenant_id)
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(side_effect=[
        _scalar_result(doc_row),  # orphan fallback by tenant+id
        SimpleNamespace(),  # delete rag status
        SimpleNamespace(),  # delete membership row
        _scalar_result(doc_row),  # doc_q
    ])

    fake_status_manager = MagicMock()
    fake_status_manager.stop_ingest = AsyncMock(return_value={"stopped_stages": [], "task_ids": []})
    monkeypatch.setattr(documents_router, "RAGStatusManager", lambda *args, **kwargs: fake_status_manager)
    monkeypatch.setattr(documents_router.s3_manager, "delete_folder", AsyncMock(return_value=True))
    fake_collection_service = MagicMock()
    fake_collection_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(documents_router, "CollectionService", lambda _session: fake_collection_service)

    result = await documents_router.delete_collection_documents(
        collection_id=collection_id,
        doc_ids=[str(doc_id)],
        session=fake_session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    assert result["deleted"] == 1
    assert result["not_found"] == []
