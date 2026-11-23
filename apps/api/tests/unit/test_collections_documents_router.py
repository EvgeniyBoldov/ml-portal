"""Unit tests for collections documents router (collections/documents.py)."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.collections import documents as documents_router
from app.schemas.common import Step

MODULE = "app.api.v1.routers.collections.documents"
COLLECTION_ID = uuid4()
DOC_ID = uuid4()
OTHER_DOC_ID = uuid4()
TENANT_ID = uuid4()
USER_ID = uuid4()
OPERATION_ID = uuid4()
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
USER = SimpleNamespace(id=USER_ID)


def make_collection(**overrides):
    base = dict(
        id=COLLECTION_ID,
        tenant_id=TENANT_ID,
        collection_type="document",
        memory_enabled=True,
        table_name=None,
        fields=None,
        qdrant_collection_name=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_doc(**overrides):
    base = dict(
        id=DOC_ID,
        name="Doc",
        filename="doc.pdf",
        status="ready",
        agg_status="ready",
        scope="company",
        tags=["t"],
        size_bytes=100,
        size=90,
        content_type="application/pdf",
        created_at=NOW,
        updated_at=NOW,
        title="Title",
        tenant_id=TENANT_ID,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_membership(**overrides):
    base = dict(
        in_collection=True,
        in_tenant=True,
        source=SimpleNamespace(
            meta={"artifacts": {"original": {"key": "orig"}}, "collection": {"row_id": None}}
        ),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_file(content=b"12345", filename="f.txt", content_type="text/plain"):
    return SimpleNamespace(
        read=AsyncMock(return_value=content), filename=filename, content_type=content_type
    )


def settings_mock():
    return MagicMock(
        return_value=SimpleNamespace(UPLOAD_MAX_BYTES=10, S3_BUCKET_RAG="rag-bucket")
    )


def s3_mock():
    s3 = MagicMock()
    s3.delete_object = AsyncMock()
    s3.delete_folder = AsyncMock()
    return s3


def apply_patches(targets: dict) -> ExitStack:
    """Patch MODULE-qualified names (or absolute dotted paths) on one stack."""
    stack = ExitStack()
    for target, replacement in targets.items():
        full = target if target.startswith("app.") else f"{MODULE}.{target}"
        stack.enter_context(patch(full, replacement))
    return stack


def long_memory_service(enqueue=None, inspection=None):
    service = MagicMock()
    if enqueue is not None:
        service.return_value.enqueue = enqueue
    if inspection is not None:
        service.return_value.inspection = inspection
    return service


class TestMemoryDocumentHelper:
    async def test_returns_collection_when_doc_in_collection(self):
        collection = make_collection()
        with apply_patches(
            {
                "_resolve_collection": AsyncMock(return_value=collection),
                "_resolve_document_membership": AsyncMock(return_value=make_membership()),
            }
        ):
            result = await documents_router._memory_document(
                COLLECTION_ID, DOC_ID, AsyncMock(), USER
            )
        assert result is collection

    async def test_404_when_document_not_in_collection(self):
        with apply_patches(
            {
                "_resolve_collection": AsyncMock(return_value=make_collection()),
                "_resolve_document_membership": AsyncMock(
                    return_value=make_membership(in_collection=False)
                ),
            }
        ):
            with pytest.raises(HTTPException) as err:
                await documents_router._memory_document(
                    COLLECTION_ID, DOC_ID, AsyncMock(), USER
                )
        assert err.value.status_code == 404


class TestInspectDocumentMemory:
    def _targets(self, inspection, document_info):
        hippo = MagicMock()
        hippo.return_value.document_info = document_info
        return {
            "_resolve_collection": AsyncMock(return_value=make_collection()),
            "_resolve_document_membership": AsyncMock(return_value=make_membership()),
            "LongMemoryDocumentService": long_memory_service(inspection=inspection),
            "app.services.hipporag_service.HippoRAGService": hippo,
        }

    async def test_merges_long_memory_and_worker_info(self):
        inspection = AsyncMock(return_value={"rows": [{"id": "1"}]})
        document_info = AsyncMock(return_value={"availability": "up"})
        with apply_patches(self._targets(inspection, document_info)):
            result = await documents_router.inspect_document_memory(
                COLLECTION_ID, DOC_ID, session=AsyncMock(), user=USER
            )
        assert result == {
            "rows": [{"id": "1"}],
            "worker": {"availability": "up"},
        }
        inspection.assert_awaited_once_with(DOC_ID)
        document_info.assert_awaited_once_with(DOC_ID)

    async def test_worker_failure_degrades_to_unavailable_payload(self):
        document_info = AsyncMock(side_effect=RuntimeError("worker down"))
        with apply_patches(self._targets(AsyncMock(return_value={}), document_info)):
            result = await documents_router.inspect_document_memory(
                COLLECTION_ID, DOC_ID, session=AsyncMock(), user=USER
            )
        assert result["worker"] == {
            "availability": "unknown",
            "error": "LongMemory worker is unavailable",
        }


class TestQueueDocumentMemory:
    def _targets(self, enqueue, membership=None):
        return {
            "_resolve_collection": AsyncMock(return_value=make_collection()),
            "_require_collection_editor": AsyncMock(),
            "_resolve_document_membership": AsyncMock(
                return_value=membership or make_membership()
            ),
            "require_document_content_access": AsyncMock(),
            "LongMemoryDocumentService": long_memory_service(enqueue=enqueue),
            "app.workers.tasks_long_memory_documents.execute_long_memory_document": MagicMock(),
        }

    async def test_add_queues_operation_and_dispatches_worker(self):
        enqueue = AsyncMock(return_value=SimpleNamespace(id=OPERATION_ID, status="pending"))
        dispatch = MagicMock()
        session = AsyncMock()
        targets = self._targets(enqueue)
        targets["app.workers.tasks_long_memory_documents.execute_long_memory_document"] = dispatch
        with apply_patches(targets):
            result = await documents_router.add_document_memory(
                COLLECTION_ID, DOC_ID, session=session, user=USER
            )
        enqueue.assert_awaited_once_with(DOC_ID, "add")
        session.commit.assert_awaited_once()
        dispatch.delay.assert_called_once_with(str(OPERATION_ID))
        assert result == {
            "document_id": str(DOC_ID),
            "operation_id": str(OPERATION_ID),
            "status": "queued",
        }

    async def test_remove_uses_delete_action_and_returns_raw_status(self):
        enqueue = AsyncMock(return_value=SimpleNamespace(id=OPERATION_ID, status="running"))
        with apply_patches(self._targets(enqueue)):
            result = await documents_router.remove_document_memory(
                COLLECTION_ID, DOC_ID, session=AsyncMock(), user=USER
            )
        enqueue.assert_awaited_once_with(DOC_ID, "delete")
        assert result["status"] == "running"

    async def test_enqueue_conflict_becomes_409(self):
        enqueue = AsyncMock(side_effect=ValueError("operation already active"))
        session = AsyncMock()
        with apply_patches(self._targets(enqueue)):
            with pytest.raises(HTTPException) as err:
                await documents_router.add_document_memory(
                    COLLECTION_ID, DOC_ID, session=session, user=USER
                )
        assert err.value.status_code == 409
        assert err.value.detail == "operation already active"
        session.commit.assert_not_awaited()

    async def test_dispatch_failure_is_swallowed(self):
        enqueue = AsyncMock(return_value=SimpleNamespace(id=OPERATION_ID, status="pending"))
        dispatch = MagicMock()
        dispatch.delay = MagicMock(side_effect=RuntimeError("broker down"))
        targets = self._targets(enqueue)
        targets["app.workers.tasks_long_memory_documents.execute_long_memory_document"] = dispatch
        session = AsyncMock()
        with apply_patches(targets):
            result = await documents_router.add_document_memory(
                COLLECTION_ID, DOC_ID, session=session, user=USER
            )
        assert result["status"] == "queued"
        session.commit.assert_awaited_once()

    async def test_legacy_extract_endpoint_is_gone(self):
        with pytest.raises(HTTPException) as err:
            await documents_router.add_document_memory_legacy(
                COLLECTION_ID, DOC_ID, session=AsyncMock(), user=USER
            )
        assert err.value.status_code == 410


class TestCleanupDocumentVectors:
    def _targets(self, exists=None, resolve=None, build=None):
        qdrant = MagicMock()
        qdrant.return_value.collection_exists = AsyncMock(
            side_effect=exists if exists is not None else []
        )
        qdrant.return_value.delete_by_filter = AsyncMock()
        lifecycle = MagicMock()
        lifecycle.return_value.resolve_target_vector_models = AsyncMock(
            return_value=resolve if resolve is not None else []
        )
        return {
            "app.adapters.impl.qdrant.QdrantVectorStore": qdrant,
            "app.services.collection.vector_lifecycle.CollectionVectorLifecycleService": lifecycle,
            "app.services.collection.vector_lifecycle.build_model_scoped_qdrant_collections": MagicMock(
                return_value=build or []
            ),
        }

    async def test_noop_without_qdrant_collection(self):
        targets = self._targets()
        with apply_patches(targets):
            await documents_router._cleanup_document_vectors(
                make_collection(qdrant_collection_name=None), AsyncMock(), DOC_ID
            )
        targets["app.adapters.impl.qdrant.QdrantVectorStore"].return_value.assert_not_called()

    async def test_deletes_only_existing_model_scoped_collections(self):
        targets = self._targets(
            exists=[True, False],
            resolve=["m1", "m2"],
            build=[("m1", "qc_m1"), ("m2", "qc_m2")],
        )
        with apply_patches(targets):
            await documents_router._cleanup_document_vectors(
                make_collection(qdrant_collection_name="qc"), AsyncMock(), DOC_ID
            )
        qdrant = targets["app.adapters.impl.qdrant.QdrantVectorStore"].return_value
        qdrant.collection_exists.assert_any_await("qc_m1")
        qdrant.collection_exists.assert_any_await("qc_m2")
        qdrant.delete_by_filter.assert_awaited_once_with("qc_m1", {"source_id": str(DOC_ID)})

    async def test_cleanup_failure_is_swallowed(self):
        targets = self._targets()
        lifecycle = targets[
            "app.services.collection.vector_lifecycle.CollectionVectorLifecycleService"
        ]
        lifecycle.return_value.resolve_target_vector_models = AsyncMock(
            side_effect=RuntimeError("lifecycle boom")
        )
        with apply_patches(targets):
            await documents_router._cleanup_document_vectors(
                make_collection(qdrant_collection_name="qc"), AsyncMock(), DOC_ID
            )


class TestUploadCollectionDocument:
    def _targets(self, collection=None, upload_result=None, upload_error=None, redis=None):
        upload = MagicMock()
        if upload_error is not None:
            upload.return_value.upload_document = AsyncMock(side_effect=upload_error)
        else:
            result = (
                upload_result
                if upload_result is not None
                else {"doc_id": str(DOC_ID), "artifacts": {"original": {"key": "k1"}}}
            )
            upload.return_value.upload_document = AsyncMock(return_value=result)
        return {
            "_resolve_collection": AsyncMock(return_value=collection or make_collection()),
            "_require_collection_editor": AsyncMock(),
            "resolve_memory_scopes": AsyncMock(),
            "get_redis_client": MagicMock(return_value=redis),
            "get_settings": settings_mock(),
            "AsyncRepositoryFactory": MagicMock(),
            "CollectionDocumentUploadService": upload,
            "s3_manager": s3_mock(),
        }

    def _call(self, file, session, **overrides):
        kwargs = dict(
            file=file,
            title=None,
            source=None,
            scope=None,
            tags=None,
            meta_fields=None,
            memory_enabled=None,
            project_keys=None,
            memory_scope_keys=None,
            auto_ingest=False,
            session=session,
            user=USER,
        )
        kwargs.update(overrides)
        return documents_router.upload_collection_document(COLLECTION_ID, **kwargs)

    async def test_upload_happy_path_without_auto_ingest(self):
        targets = self._targets()
        session = AsyncMock()
        with apply_patches(targets):
            result = await self._call(make_file(filename=None), session, title="T")
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        kwargs = upload.await_args.kwargs
        assert result["doc_id"] == str(DOC_ID)
        assert kwargs["collection_id"] == COLLECTION_ID
        assert kwargs["file_content"] == b"12345"
        assert kwargs["filename"].startswith("upload_")
        assert kwargs["user_id"] == USER_ID
        assert kwargs["content_type"] == "text/plain"
        assert kwargs["title"] == "T"
        assert kwargs["tags"] == []
        assert kwargs["meta_fields"] == {}
        assert kwargs["project_keys"] == []
        assert kwargs["memory_scope_keys"] == []
        targets["resolve_memory_scopes"].assert_awaited_once_with(session, ["company"])
        session.commit.assert_awaited_once()

    async def test_auto_ingest_starts_ingest_for_new_document(self):
        targets = self._targets()
        status_manager = MagicMock()
        ingest = MagicMock()
        ingest.return_value.start_ingest = AsyncMock()
        targets["RAGStatusManager"] = status_manager
        targets["RAGIngestService"] = ingest
        with apply_patches(targets):
            await self._call(make_file(), AsyncMock(), tags='["a"]', auto_ingest=True)
        request = ingest.return_value.start_ingest.await_args.args[0]
        assert request.document_id == DOC_ID

    async def test_file_over_limit_rejected_413(self):
        with apply_patches(self._targets()):
            with pytest.raises(HTTPException) as err:
                await self._call(make_file(content=b"x" * 11), AsyncMock())
        assert err.value.status_code == 413
        assert "10 bytes" in err.value.detail

    async def test_tags_json_array_and_comma_fallback(self):
        targets = self._targets()
        with apply_patches(targets):
            await self._call(make_file(), AsyncMock(), tags='["a", "b"]')
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        assert upload.await_args.kwargs["tags"] == ["a", "b"]

        targets = self._targets()
        with apply_patches(targets):
            await self._call(make_file(), AsyncMock(), tags="a, b ,, c")
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        assert upload.await_args.kwargs["tags"] == ["a", "b", "c"]

    @pytest.mark.parametrize("tags", ['{"a": 1}', "[1, 2]"])
    async def test_invalid_tags_rejected_422(self, tags):
        with apply_patches(self._targets()):
            with pytest.raises(HTTPException) as err:
                await self._call(make_file(), AsyncMock(), tags=tags)
        assert err.value.status_code == 422
        assert "tags" in err.value.detail

    async def test_meta_fields_parsed_and_validated(self):
        targets = self._targets()
        with apply_patches(targets):
            await self._call(make_file(), AsyncMock(), meta_fields='{"x": 1}')
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        assert upload.await_args.kwargs["meta_fields"] == {"x": 1}

        for raw in ("not json", "[1, 2]"):
            with apply_patches(self._targets()):
                with pytest.raises(HTTPException) as err:
                    await self._call(make_file(), AsyncMock(), meta_fields=raw)
            assert err.value.status_code == 422
            assert "meta_fields" in err.value.detail

    async def test_scope_keys_comma_fallback_with_dedupe(self):
        targets = self._targets()
        session = AsyncMock()
        with apply_patches(targets):
            await self._call(make_file(), session, project_keys='["A", "a"]')
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        assert upload.await_args.kwargs["project_keys"] == ["a"]
        targets["resolve_memory_scopes"].assert_awaited_once_with(session, ["a"])

    async def test_scope_keys_malformed_json_array_rejected(self):
        with apply_patches(self._targets()):
            with pytest.raises(HTTPException) as err:
                await self._call(make_file(), AsyncMock(), project_keys='["a",')
        assert err.value.status_code == 422
        assert "project_keys" in err.value.detail

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"project_keys": "[1]"},
            {"project_keys": '["a", "b"]'},
            {"memory_scope_keys": '["a", "b"]'},
        ],
    )
    async def test_invalid_or_multiple_scopes_rejected_422(self, kwargs):
        with apply_patches(self._targets()):
            with pytest.raises(HTTPException) as err:
                await self._call(make_file(), AsyncMock(), **kwargs)
        assert err.value.status_code == 422

    async def test_matching_project_and_memory_scope_allowed(self):
        targets = self._targets()
        with apply_patches(targets):
            await self._call(
                make_file(), AsyncMock(), project_keys='["x"]', memory_scope_keys="x"
            )
        upload = targets["CollectionDocumentUploadService"].return_value.upload_document
        assert upload.await_args.kwargs["project_keys"] == ["x"]
        assert upload.await_args.kwargs["memory_scope_keys"] == ["x"]

    async def test_unknown_scope_rejected_422(self):
        targets = self._targets()
        targets["resolve_memory_scopes"] = AsyncMock(
            side_effect=ValueError("unknown memory scope")
        )
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._call(make_file(), AsyncMock())
        assert err.value.status_code == 422
        assert err.value.detail == "unknown memory scope"

    async def test_redis_client_builds_event_publisher(self):
        redis = SimpleNamespace(name="redis")
        publisher = MagicMock()
        targets = self._targets(redis=redis)
        targets["app.services.rag_event_publisher.RAGEventPublisher"] = publisher
        with apply_patches(targets):
            await self._call(make_file(), AsyncMock())
        publisher.assert_called_once_with(redis)

    async def test_upload_failure_rolls_back_without_artifact_cleanup(self):
        targets = self._targets(upload_error=RuntimeError("upload failed"))
        session = AsyncMock()
        with apply_patches(targets):
            with pytest.raises(RuntimeError):
                await self._call(make_file(), session)
        session.rollback.assert_awaited_once()
        targets["s3_manager"].delete_object.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def _failing_ingest(self, session):
        targets = self._targets()
        ingest = MagicMock()
        ingest.return_value.start_ingest = AsyncMock(side_effect=RuntimeError("ingest failed"))
        targets["RAGStatusManager"] = MagicMock()
        targets["RAGIngestService"] = ingest
        with apply_patches(targets):
            with pytest.raises(RuntimeError):
                await self._call(make_file(), session, auto_ingest=True)
        return targets

    async def test_ingest_failure_cleans_up_unpersisted_artifact(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        targets = await self._failing_ingest(session)
        session.rollback.assert_awaited_once()
        targets["s3_manager"].delete_object.assert_awaited_once_with("rag-bucket", "k1")
        session.commit.assert_not_awaited()

    async def test_ingest_failure_keeps_persisted_artifact(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=DOC_ID)
        targets = await self._failing_ingest(session)
        targets["s3_manager"].delete_object.assert_not_awaited()

    async def test_ingest_failure_preserves_artifact_when_state_unknown(self):
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=RuntimeError("db gone"))
        targets = await self. _failing_ingest(session)
        targets["s3_manager"].delete_object.assert_not_awaited()

    async def test_ingest_failure_without_original_key_skips_s3(self):
        targets = self._targets(upload_result={"doc_id": str(DOC_ID)})
        ingest = MagicMock()
        ingest.return_value.start_ingest = AsyncMock(side_effect=RuntimeError("ingest failed"))
        targets["RAGStatusManager"] = MagicMock()
        targets["RAGIngestService"] = ingest
        session = AsyncMock()
        with apply_patches(targets):
            with pytest.raises(RuntimeError):
                await self._call(make_file(), session, auto_ingest=True)
        targets["s3_manager"].delete_object.assert_not_awaited()

    async def test_s3_cleanup_failure_is_swallowed(self):
        targets = self._targets()
        ingest = MagicMock()
        ingest.return_value.start_ingest = AsyncMock(side_effect=RuntimeError("ingest failed"))
        targets["RAGStatusManager"] = MagicMock()
        targets["RAGIngestService"] = ingest
        targets["s3_manager"].delete_object = AsyncMock(side_effect=RuntimeError("s3 down"))
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        with apply_patches(targets):
            with pytest.raises(RuntimeError):
                await self._call(make_file(), session, auto_ingest=True)
        targets["s3_manager"].delete_object.assert_awaited_once()


def list_session(count=1, status_rows=None, rows=None):
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar=lambda: count),
            SimpleNamespace(all=lambda: status_rows or [("ready", 1)]),
            SimpleNamespace(all=lambda: rows or []),
        ]
    )
    return session


def list_targets(collection=None, inspections=None, normalize_meta=None):
    normalize = MagicMock(return_value=normalize_meta or {})
    inspection = AsyncMock(side_effect=inspections or [])
    return {
        "_resolve_collection": AsyncMock(return_value=collection or make_collection()),
        "normalize_document_source_meta": normalize,
        "LongMemoryDocumentService": long_memory_service(inspection=inspection),
    }


LIST_META = {
    "document": {
        "scope": "project",
        "tags": ["x"],
        "size_bytes": 42,
        "content_type": "application/pdf",
        "title": "Meta title",
        "source": "upload",
    },
    "collection": {"row_id": "r1"},
    "artifacts": {"original": {"key": "k1"}, "text": {"key": None}, "preview": {}},
    "memory": {"policy": "explicit", "enabled": False, "project_keys": ["p"], "scope_keys": ["s"]},
}


class TestListCollectionDocuments:
    async def _run(self, targets, session, **overrides):
        kwargs = dict(page=1, size=50, status=None, query=None, session=session, user=USER)
        kwargs.update(overrides)
        return await documents_router.list_collection_documents(COLLECTION_ID, **kwargs)

    async def test_not_a_document_collection_rejected_400(self):
        targets = list_targets(collection=make_collection(collection_type="sql"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock())
        assert err.value.status_code == 400

    async def test_serializes_items_with_stats_and_memory(self):
        doc1 = make_doc(updated_at=None)
        doc2 = make_doc(id=OTHER_DOC_ID, name=None, agg_status="ready")
        inspections = [
            {"action": "add", "status": "completed", "progress": {"percent": 100}},
            {"action": "delete", "status": "completed", "progress": {"percent": 0}},
        ]
        targets = list_targets(normalize_meta=LIST_META, inspections=inspections)
        session = list_session(
            count=2,
            status_rows=[("ready", 1), ("embedding", 1), (None, 1)],
            rows=[(doc1, "raw1"), (doc2, "raw2")],
        )
        with apply_patches(targets):
            response = await self._run(targets, session, query="abc")
        assert response["total"] == 2
        assert response["has_more"] is False
        assert response["stats"] == {
            "total": 3,
            "ready": 1,
            "failed": 0,
            "partial": 0,
            "archived": 0,
            "processing": 1,
            "uploaded": 1,
        }
        item1, item2 = response["items"]
        assert item1["id"] == str(DOC_ID)
        assert item1["name"] == "Doc"
        assert item1["title"] == "Meta title"
        assert item1["size_bytes"] == 42
        assert item1["s3_key"] == "k1"
        assert item1["updated_at"] is None
        assert item1["scope"] == "project"
        assert item1["artifacts"] == {"original": {"key": "k1"}}
        assert item1["document"]["tags"] == ["x"]
        assert item1["memory"] == {
            "policy": "explicit",
            "enabled": False,
            "effective_enabled": False,
            "project_keys": ["p"],
            "scope_keys": ["s"],
            "extraction_status": "completed",
            "extraction_metrics": {"percent": 100},
        }
        assert item1["meta_fields"] == {}
        assert item2["name"] == "doc.pdf"
        assert item2["memory"]["extraction_status"] == "deleted"

    async def test_memory_defaults_to_collection_policy(self):
        meta = {"document": {}, "collection": {}, "artifacts": {}, "memory": {}}
        targets = list_targets(
            collection=make_collection(memory_enabled=True),
            normalize_meta=meta,
            inspections=[{"action": "add", "status": "pending", "progress": {}}],
        )
        session = list_session(rows=[(make_doc(agg_status="ready"), "raw")])
        with apply_patches(targets):
            response = await self._run(targets, session)
        memory = response["items"][0]["memory"]
        assert memory == {
            "policy": "collection",
            "enabled": None,
            "effective_enabled": True,
            "project_keys": [],
            "scope_keys": [],
            "extraction_status": "pending",
            "extraction_metrics": {},
        }

    async def test_missing_agg_status_computed_from_pipelines(self):
        doc = make_doc(agg_status=None, status="uploaded")
        targets = list_targets(normalize_meta=LIST_META, inspections=[{"action": "add", "status": "pending", "progress": {}}])
        repo = MagicMock()
        repo.return_value.get_pipeline_nodes = AsyncMock(return_value=["n1"])
        repo.return_value.get_embedding_nodes = AsyncMock(return_value=["e1"])
        status_manager = MagicMock()
        status_manager.return_value._get_target_models = AsyncMock(return_value=["m1"])
        calculate = MagicMock(return_value=("partial", {"detail": 1}))
        targets["app.repositories.rag_status_repo.AsyncRAGStatusRepository"] = repo
        targets["AsyncRepositoryFactory"] = MagicMock()
        targets["RAGStatusManager"] = status_manager
        targets["calculate_aggregate_status"] = calculate
        session = list_session(rows=[(doc, "raw")])
        with apply_patches(targets):
            response = await self._run(targets, session)
        assert response["items"][0]["agg_status"] == "partial"
        calculate.assert_called_once_with(
            doc_id=DOC_ID, pipeline_nodes=["n1"], embedding_nodes=["e1"], target_models=["m1"]
        )

    async def test_missing_agg_status_falls_back_to_doc_status_on_error(self):
        doc = make_doc(agg_status=None, status="uploaded")
        targets = list_targets(normalize_meta=LIST_META, inspections=[{"action": "add", "status": "pending", "progress": {}}])
        repo = MagicMock()
        repo.return_value.get_pipeline_nodes = AsyncMock(side_effect=RuntimeError("repo boom"))
        status_manager = MagicMock()
        status_manager.return_value._get_target_models = AsyncMock(
            side_effect=RuntimeError("status boom")
        )
        targets["app.repositories.rag_status_repo.AsyncRAGStatusRepository"] = repo
        targets["AsyncRepositoryFactory"] = MagicMock()
        targets["RAGStatusManager"] = status_manager
        session = list_session(rows=[(doc, "raw")])
        with apply_patches(targets):
            response = await self._run(targets, session)
        assert response["items"][0]["agg_status"] == "uploaded"

    async def test_table_fields_enrich_meta_fields(self):
        collection = make_collection(
            table_name="tbl_x",
            fields=[
                {"name": "title", "data_type": "text"},
                {"name": "attachment", "data_type": "file"},
            ],
        )
        targets = list_targets(
            collection=collection, normalize_meta=LIST_META, inspections=[{"action": "add", "status": "pending", "progress": {}}]
        )
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: 1),
                SimpleNamespace(all=lambda: [("ready", 1)]),
                SimpleNamespace(all=lambda: [(make_doc(agg_status="ready"), "raw")]),
                SimpleNamespace(
                    mappings=lambda: SimpleNamespace(
                        all=lambda: [{"id": "r1", "title": "Dynamic title", "attachment": None}]
                    )
                ),
            ]
        )
        with apply_patches(targets):
            response = await self._run(targets, session)
        assert response["items"][0]["meta_fields"] == {"title": "Dynamic title"}
        dynamic_query = session.execute.await_args_list[3].args[0]
        assert "tbl_x" in str(dynamic_query)
        assert session.execute.await_args_list[3].args[1] == {"rid_0": "r1"}

    @pytest.mark.parametrize("status", ["ready", "processing", "legacy_raw_status"])
    async def test_status_filter_variants(self, status):
        targets = list_targets(normalize_meta=LIST_META, inspections=[{"action": "add", "status": "pending", "progress": {}}])
        session = list_session(rows=[(make_doc(agg_status="ready"), "raw")])
        with apply_patches(targets):
            response = await self._run(targets, session, status=status)
        assert response["items"][0]["id"] == str(DOC_ID)

    async def test_unexpected_error_becomes_500(self):
        targets = list_targets()
        targets["_resolve_collection"] = AsyncMock(side_effect=RuntimeError("boom"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock())
        assert err.value.status_code == 500


class TestDeleteCollectionDocuments:
    def _targets(self, collection=None, membership=None):
        return {
            "_resolve_collection": AsyncMock(return_value=collection or make_collection()),
            "_require_collection_editor": AsyncMock(),
            "_resolve_document_membership": AsyncMock(
                return_value=membership or make_membership()
            ),
            "require_document_content_access": AsyncMock(),
            "_stop_pipeline_and_revoke": AsyncMock(),
            "RAGStatusManager": MagicMock(),
            "LongMemoryDocumentService": long_memory_service(
                enqueue=AsyncMock(return_value=SimpleNamespace(id=OPERATION_ID, status="pending"))
            ),
            "normalize_document_source_meta": MagicMock(side_effect=lambda meta: meta),
            "get_settings": settings_mock(),
            "s3_manager": s3_mock(),
        }

    def _happy_session(self, doc=None, extra_executes=0):
        doc = doc or make_doc()
        session = AsyncMock()
        session.get = AsyncMock(return_value=doc)
        session.execute = AsyncMock(
            side_effect=[
                *([SimpleNamespace()] * extra_executes),
                SimpleNamespace(),  # delete RAGStatus
                SimpleNamespace(),  # delete membership
                SimpleNamespace(scalar_one_or_none=lambda: doc),  # doc select
            ]
        )
        return session

    async def _run(self, targets, session, doc_ids):
        return await documents_router.delete_collection_documents(
            COLLECTION_ID, doc_ids=doc_ids, session=session, user=USER
        )

    async def test_happy_delete_removes_artifacts_and_rows(self):
        doc = make_doc()
        targets = self._targets()
        session = self._happy_session(doc)
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response == {
            "deleted": 1,
            "collection_id": str(COLLECTION_ID),
            "not_found": [],
            "skipped_foreign": [],
            "failed": [],
        }
        targets["s3_manager"].delete_object.assert_awaited_once_with("rag-bucket", "orig")
        targets["s3_manager"].delete_folder.assert_awaited_once_with(
            "rag-bucket", f"{TENANT_ID}/{DOC_ID}"
        )
        targets["LongMemoryDocumentService"].return_value.enqueue.assert_awaited_once_with(
            DOC_ID, "delete"
        )
        targets["_stop_pipeline_and_revoke"].assert_awaited_once()
        session.delete.assert_any_await(targets["_resolve_document_membership"].return_value.source)
        session.delete.assert_any_await(doc)
        session.commit.assert_awaited_once()
        targets["RAGStatusManager"].return_value.schedule_collection_projection.assert_called_once_with(
            COLLECTION_ID
        )

    async def test_membership_row_deleted_for_collection_only(self):
        targets = self._targets()
        session = self._happy_session()
        with apply_patches(targets):
            await self._run(targets, session, [str(DOC_ID)])
        membership_delete = session.execute.await_args_list[1].args[0]
        # SQLAlchemy renders the table name, not the ORM class name.
        assert "document_collection_memberships" in str(membership_delete)

    async def test_dynamic_table_row_deleted(self):
        collection = make_collection(table_name="tbl_x")
        membership = make_membership(
            source=SimpleNamespace(
                meta={
                    "artifacts": {"original": {"key": "orig"}},
                    "collection": {"row_id": "row-9"},
                }
            )
        )
        targets = self._targets(collection=collection, membership=membership)
        session = self._happy_session(extra_executes=1)
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["deleted"] == 1
        row_delete = session.execute.await_args_list[0].args[0]
        assert "tbl_x" in str(row_delete)
        assert session.execute.await_args_list[0].args[1] == {"rid": "row-9"}

    async def test_foreign_document_skipped_without_access_check(self):
        targets = self._targets(membership=make_membership(in_collection=False))
        with apply_patches(targets):
            response = await self._run(targets, AsyncMock(), [str(DOC_ID)])
        assert response["skipped_foreign"] == [str(DOC_ID)]
        assert response["deleted"] == 0
        targets["require_document_content_access"].assert_not_awaited()
        targets["RAGStatusManager"].return_value.schedule_collection_projection.assert_not_called()

    async def test_orphan_document_deleted_via_tenant_lookup(self):
        targets = self._targets(membership=make_membership(in_tenant=False, source=None))
        doc = make_doc()
        session = self._happy_session(doc)
        # Orphan mode performs one extra select before the delete statements.
        session.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: doc),  # orphan lookup
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(scalar_one_or_none=lambda: doc),  # final doc select
            ]
        )
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["deleted"] == 1
        targets["require_document_content_access"].assert_awaited_once()

    async def test_orphan_document_missing_reported_not_found(self):
        targets = self._targets(membership=make_membership(in_tenant=False, source=None))
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[SimpleNamespace(scalar_one_or_none=lambda: None)]
        )
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["not_found"] == [str(DOC_ID)]
        assert response["deleted"] == 0
        session.commit.assert_awaited_once()

    async def test_invalid_ids_deduplicated_and_reported_failed(self):
        targets = self._targets()
        with apply_patches(targets):
            response = await self._run(targets, AsyncMock(), ["nope", "nope"])
        assert response["failed"] == ["nope"]
        assert response["deleted"] == 0
        targets["_resolve_document_membership"].assert_not_awaited()

    async def test_duplicate_id_spellings_collapse_to_one_delete(self):
        targets = self._targets()
        session = self._happy_session()
        with apply_patches(targets):
            response = await self._run(
                targets, session, [str(DOC_ID), str(DOC_ID).upper()]
            )
        assert response["deleted"] == 1
        # Two membership resolutions per unique document: preflight + delete loop.
        assert targets["_resolve_document_membership"].await_count == 2

    async def test_delete_failure_records_failed_id(self):
        targets = self._targets()
        session = AsyncMock()
        session.get = AsyncMock(side_effect=RuntimeError("delete boom"))
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["failed"] == [str(DOC_ID)]
        assert response["deleted"] == 0
        session.commit.assert_awaited_once()
        targets["RAGStatusManager"].return_value.schedule_collection_projection.assert_not_called()

    async def test_pipeline_s3_and_row_failures_are_swallowed(self):
        collection = make_collection(table_name="tbl_x")
        membership = make_membership(
            source=SimpleNamespace(
                meta={
                    "artifacts": {"original": {"key": "orig"}},
                    "collection": {"row_id": "row-1"},
                }
            )
        )
        targets = self._targets(collection=collection, membership=membership)
        targets["_stop_pipeline_and_revoke"] = AsyncMock(side_effect=RuntimeError("stop boom"))
        targets["s3_manager"].delete_object = AsyncMock(side_effect=RuntimeError("s3 object boom"))
        targets["s3_manager"].delete_folder = AsyncMock(side_effect=RuntimeError("s3 folder boom"))
        doc = make_doc()
        session = AsyncMock()
        session.get = AsyncMock(return_value=doc)
        session.execute = AsyncMock(
            side_effect=[
                RuntimeError("dynamic row boom"),
                SimpleNamespace(),  # delete RAGStatus
                SimpleNamespace(),  # delete membership
                SimpleNamespace(scalar_one_or_none=lambda: doc),  # final doc select
            ]
        )
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["deleted"] == 1
        assert response["failed"] == []
        session.commit.assert_awaited_once()

    async def test_missing_final_document_row_reports_not_found(self):
        targets = self._targets()
        doc = make_doc()
        session = AsyncMock()
        session.get = AsyncMock(return_value=doc)
        session.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(),  # delete RAGStatus
                SimpleNamespace(),  # delete membership
                SimpleNamespace(scalar_one_or_none=lambda: None),  # final doc select
            ]
        )
        with apply_patches(targets):
            response = await self._run(targets, session, [str(DOC_ID)])
        assert response["not_found"] == [str(DOC_ID)]
        assert response["deleted"] == 0

    async def test_not_a_document_collection_rejected_400(self):
        targets = self._targets(collection=make_collection(collection_type="sql"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock(), [str(DOC_ID)])
        assert err.value.status_code == 400

    async def test_unexpected_error_becomes_500(self):
        targets = self._targets()
        targets["_resolve_collection"] = AsyncMock(side_effect=RuntimeError("boom"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock(), [str(DOC_ID)])
        assert err.value.status_code == 500


class TestReindexCollectionDocuments:
    def _targets(self, collection=None, policies=None, retry_error=None):
        status_manager = MagicMock()
        if policies is not None:
            status_manager.return_value.get_ingest_policy = AsyncMock(side_effect=policies)
        else:
            status_manager.return_value.get_ingest_policy = AsyncMock(
                return_value={"start_allowed": True}
            )
        ingest = MagicMock()
        if retry_error is not None:
            ingest.return_value.retry_failed = AsyncMock(side_effect=retry_error)
        else:
            ingest.return_value.retry_failed = AsyncMock()
        collection_service = MagicMock()
        collection_service.return_value.sync_collection_status = AsyncMock()
        return {
            "_resolve_collection": AsyncMock(return_value=collection or make_collection()),
            "_require_collection_editor": AsyncMock(),
            "require_document_content_access": AsyncMock(),
            "get_redis_client": MagicMock(return_value=None),
            "AsyncRepositoryFactory": MagicMock(),
            "RAGStatusManager": status_manager,
            "RAGIngestService": ingest,
            "CollectionService": collection_service,
        }

    async def _run(self, targets, session):
        return await documents_router.reindex_collection_documents(
            COLLECTION_ID, session=session, user=USER
        )

    async def test_empty_collection_returns_zeroes_without_commit(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
        )
        targets = self._targets()
        with apply_patches(targets):
            response = await self._run(targets, session)
        assert response == {
            "status": "ok",
            "collection_id": str(COLLECTION_ID),
            "total": 0,
            "queued": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
        }
        session.commit.assert_not_awaited()

    async def test_mixed_queue_skip_and_failure_results(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [DOC_ID, OTHER_DOC_ID, uuid4()])
            )
        )
        targets = self._targets(
            policies=[
                {"start_allowed": True},
                {"start_allowed": False, "start_reason": "already_running"},
                RuntimeError("policy boom"),
            ]
        )
        with apply_patches(targets):
            response = await self._run(targets, session)
        assert response["total"] == 3
        assert response["queued"] == 1
        assert response["skipped"] == 1
        assert response["failed"] == 1
        statuses = {(item["document_id"], item["status"]) for item in response["items"]}
        assert (str(DOC_ID), "queued") in statuses
        skipped = next(i for i in response["items"] if i["status"] == "skipped")
        assert skipped["reason"] == "already_running"
        failed = next(i for i in response["items"] if i["status"] == "failed")
        assert "policy boom" in failed["error"]
        targets["RAGIngestService"].return_value.retry_failed.assert_awaited_once_with(
            DOC_ID, Step.EXTRACT
        )
        targets["CollectionService"].return_value.sync_collection_status.assert_awaited_once_with(
            targets["_resolve_collection"].return_value, persist=False
        )
        session.commit.assert_awaited_once()

    async def test_not_a_document_collection_rejected_400(self):
        targets = self._targets(collection=make_collection(collection_type="sql"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock())
        assert err.value.status_code == 400

    async def test_unexpected_error_becomes_500(self):
        targets = self._targets()
        targets["_resolve_collection"] = AsyncMock(side_effect=RuntimeError("boom"))
        with apply_patches(targets):
            with pytest.raises(HTTPException) as err:
                await self._run(targets, AsyncMock())
        assert err.value.status_code == 500
