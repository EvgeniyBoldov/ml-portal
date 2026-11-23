"""Unit tests for the RAG status stream router (rag/stream.py).

Endpoint functions are invoked directly (no HTTP layer): services and
repository factories are patched at their import sites. The SSE generator
is exercised through StreamingResponse.body_iterator; because an async
generator body only runs while it is iterated, collection and assertions
happen inside the patch contexts.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.api.v1.routers.rag import stream as stream_router

DOC_ID = uuid4()
STREAM_MODULE = "app.api.v1.routers.rag.stream"


def make_user(role: str = "editor", tenant_ids: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), role=role,
        tenant_ids=tenant_ids if tenant_ids is not None else [str(uuid4())],
    )


def make_document(tenant_id=None) -> SimpleNamespace:
    return SimpleNamespace(id=DOC_ID, tenant_id=tenant_id or uuid4())


def factory_mock(document: SimpleNamespace | None) -> MagicMock:
    factory = MagicMock()
    factory.tenant_id = uuid4()
    factory.get_rag_documents_repository.return_value.get_by_id = AsyncMock(
        return_value=document,
    )
    return factory


def status_manager_cls_mock() -> MagicMock:
    cls = MagicMock()
    instance = cls.return_value
    instance.check_ingest_allowed = AsyncMock(return_value={"allowed": True})
    instance._get_target_models = AsyncMock(return_value=["text-embed-x"])
    instance.get_ingest_policy = AsyncMock(return_value={"controls": []})
    instance.get_document_status = AsyncMock(return_value={"stages": {}})
    instance.stop_stage = AsyncMock(return_value=None)
    instance.status_repo.get_node = AsyncMock(return_value=None)
    return cls


def make_listen(events: list[dict], error: Exception | None = None):
    async def listen():
        for event in events:
            yield event
        if error is not None:
            raise error

    return listen


def subscriber_cls_mock(events: list[dict], error: Exception | None = None) -> MagicMock:
    cls = MagicMock()
    cls.return_value.subscribe = AsyncMock()
    cls.return_value.unsubscribe = AsyncMock()
    cls.return_value.listen = make_listen(events, error)
    return cls


async def collect_stream(response: StreamingResponse) -> list[str]:
    return [chunk async for chunk in response.body_iterator]


class TestStreamRagStatus:
    async def test_reader_is_forbidden(self):
        session = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await stream_router.stream_rag_status(
                user=make_user("reader"), session=session, redis=MagicMock(),
            )
        assert exc.value.status_code == 403

    async def test_missing_redis_is_service_unavailable(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.stream_rag_status(
                user=make_user("editor"), session=AsyncMock(), redis=None,
            )
        assert exc.value.status_code == 503

    async def test_editor_without_tenants_is_forbidden(self):
        resolve = AsyncMock(return_value=[])
        session = AsyncMock()

        with patch(f"{STREAM_MODULE}.resolve_active_user_tenant_ids", resolve):
            with pytest.raises(HTTPException) as exc:
                await stream_router.stream_rag_status(
                    user=make_user("editor"), session=session, redis=MagicMock(),
                )

        assert exc.value.status_code == 403
        session.close.assert_not_awaited()

    async def test_editor_stream_filters_by_document_and_unsubscribes(self):
        tenant_id = uuid4()
        redis = MagicMock()
        resolve = AsyncMock(return_value=[tenant_id])
        session = AsyncMock()
        matching = {"document_id": str(DOC_ID), "event_type": "status_update", "stage": "extract"}
        other = {"document_id": str(uuid4()), "event_type": "status_update"}
        subscriber = subscriber_cls_mock([other, matching])

        with patch(f"{STREAM_MODULE}.resolve_active_user_tenant_ids", resolve), \
                patch(f"{STREAM_MODULE}.RAGEventSubscriber", subscriber):
            response = await stream_router.stream_rag_status(
                user=make_user("editor"), session=session, redis=redis,
                document_id=str(DOC_ID),
            )
            chunks = await collect_stream(response)

            assert isinstance(response, StreamingResponse)
            assert response.media_type == "text/event-stream"
            assert response.headers["X-Accel-Buffering"] == "no"
            assert len(chunks) == 1
            assert "event: status_update" in chunks[0]
            assert json.loads(chunks[0].split("data: ", 1)[1])["document_id"] == str(DOC_ID)

            subscriber.assert_called_once_with(
                redis_client=redis, tenant_id=str(tenant_id), is_admin=False,
            )
            session.close.assert_awaited_once()
            subscriber.return_value.subscribe.assert_awaited_once()
            subscriber.return_value.unsubscribe.assert_awaited_once()

    async def test_admin_subscribes_without_tenant_scope(self):
        resolve = AsyncMock()
        subscriber = subscriber_cls_mock([])

        with patch(f"{STREAM_MODULE}.resolve_active_user_tenant_ids", resolve), \
                patch(f"{STREAM_MODULE}.RAGEventSubscriber", subscriber):
            response = await stream_router.stream_rag_status(
                user=make_user("admin"), session=AsyncMock(), redis=MagicMock(),
            )
            await collect_stream(response)

            resolve.assert_not_awaited()
            subscriber.assert_called_once()
            assert subscriber.call_args.kwargs["tenant_id"] is None
            assert subscriber.call_args.kwargs["is_admin"] is True
            subscriber.return_value.unsubscribe.assert_awaited_once()

    async def test_listen_error_yields_error_event_and_unsubscribes(self):
        subscriber = subscriber_cls_mock([], error=RuntimeError("redis gone"))

        with patch(f"{STREAM_MODULE}.RAGEventSubscriber", subscriber):
            response = await stream_router.stream_rag_status(
                user=make_user("admin"), session=AsyncMock(), redis=MagicMock(),
            )
            chunks = await collect_stream(response)

            assert len(chunks) == 1
            assert "event: error" in chunks[0]
            subscriber.return_value.unsubscribe.assert_awaited_once()

    async def test_disconnect_cancels_quietly(self):
        events = [{"document_id": str(DOC_ID), "event_type": "status_update"}]
        subscriber = subscriber_cls_mock(events, error=asyncio.CancelledError())

        with patch(f"{STREAM_MODULE}.RAGEventSubscriber", subscriber):
            response = await stream_router.stream_rag_status(
                user=make_user("admin"), session=AsyncMock(), redis=MagicMock(),
            )
            chunks = await collect_stream(response)

            assert len(chunks) == 1
            assert "event: status_update" in chunks[0]
            subscriber.return_value.unsubscribe.assert_awaited_once()

    async def test_heartbeat_is_emitted_after_interval(self):
        events = [{"document_id": str(DOC_ID), "event_type": "status_update"}]
        subscriber = subscriber_cls_mock(events)
        times = iter([0.0, 100.0])
        clock = SimpleNamespace(time=lambda: next(times))
        fake_asyncio = SimpleNamespace(
            get_event_loop=lambda: clock,
            CancelledError=asyncio.CancelledError,
        )

        with patch(f"{STREAM_MODULE}.RAGEventSubscriber", subscriber), \
                patch(f"{STREAM_MODULE}.asyncio", fake_asyncio):
            response = await stream_router.stream_rag_status(
                user=make_user("admin"), session=AsyncMock(), redis=MagicMock(),
            )
            chunks = await collect_stream(response)

            assert len(chunks) == 2
            assert chunks[1] == ": ping\n\n"


class TestGetDocumentStatus:
    async def test_reader_is_forbidden(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.get_document_status(
                document_id=str(DOC_ID), user=make_user("reader"), session=AsyncMock(),
            )
        assert exc.value.status_code == 403

    async def test_invalid_document_id(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.get_document_status(
                document_id="not-a-uuid", user=make_user("editor"), session=AsyncMock(),
            )
        assert exc.value.status_code == 400

    async def test_document_not_found(self):
        factory = factory_mock(None)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.get_document_status(
                    document_id=str(DOC_ID), user=make_user("editor"), session=AsyncMock(),
                )
        assert exc.value.status_code == 404

    async def test_editor_from_other_tenant_is_denied(self):
        document = make_document()
        other_tenant = str(uuid4())
        factory = factory_mock(document)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.get_document_status(
                    document_id=str(DOC_ID),
                    user=make_user("editor", tenant_ids=[other_tenant]),
                    session=AsyncMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Access denied"

    async def test_editor_without_tenants_is_denied(self):
        factory = factory_mock(make_document())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.get_document_status(
                    document_id=str(DOC_ID),
                    user=make_user("editor", tenant_ids=[]),
                    session=AsyncMock(),
                )
        assert exc.value.status_code == 403

    async def test_status_snapshot_is_returned(self):
        tenant_id = uuid4()
        document = make_document(tenant_id=tenant_id)
        factory = factory_mock(document)
        status_cls = status_manager_cls_mock()
        status_cls.return_value.get_document_status = AsyncMock(
            return_value={"stages": {"extract": "completed"}},
        )
        session = AsyncMock()

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls):
            result = await stream_router.get_document_status(
                document_id=str(DOC_ID),
                user=make_user("editor", tenant_ids=[str(tenant_id)]),
                session=session,
            )

        assert result == {"stages": {"extract": "completed"}}
        repo = factory.get_rag_documents_repository.return_value
        repo.get_by_id.assert_awaited_once_with(factory.tenant_id, DOC_ID)
        status_cls.assert_called_once_with(session, factory)


class TestStartIngest:
    def _patches(self, *, document=None):
        factory = factory_mock(document)
        status_cls = status_manager_cls_mock()
        publisher_cls = MagicMock()
        publisher_cls.return_value.publish_ingest_started = AsyncMock()
        ingest_cls = MagicMock()
        ingest_cls.return_value.start_ingest = AsyncMock(
            return_value={"status": "accepted", "run_id": str(uuid4())},
        )
        return factory, status_cls, publisher_cls, ingest_cls

    async def test_invalid_document_id(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.start_ingest(
                document_id="nope", user=make_user(), session=AsyncMock(),
                redis=MagicMock(),
            )
        assert exc.value.status_code == 400

    async def test_document_not_found(self):
        factory = factory_mock(None)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.start_ingest(
                    document_id=str(DOC_ID), user=make_user(), session=AsyncMock(),
                    redis=MagicMock(),
                )
        assert exc.value.status_code == 404

    async def test_unlinked_reader_is_denied(self):
        factory = factory_mock(make_document())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.start_ingest(
                    document_id=str(DOC_ID), user=make_user("reader"),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Insufficient permissions"

    async def test_unlinked_editor_from_other_tenant_is_denied(self):
        factory = factory_mock(make_document())
        other_tenant = str(uuid4())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.start_ingest(
                    document_id=str(DOC_ID),
                    user=make_user("editor", tenant_ids=[other_tenant]),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Access denied"

    async def test_lock_contention_reports_already_running(self):
        document = make_document()
        factory, status_cls, publisher_cls, _ = self._patches(document=document)
        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire = AsyncMock(return_value=False)
        redis.lock.return_value = lock

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls):
            result = await stream_router.start_ingest(
                document_id=str(DOC_ID), user=make_user(), session=AsyncMock(), redis=redis,
            )

        assert result["already_running"] is True
        assert result["status"] == "success"
        assert result["embedding_models"] == []
        assert result["active_stages"] == []
        status_cls.return_value.check_ingest_allowed.assert_not_awaited()
        lock.release.assert_not_awaited()

    @pytest.mark.parametrize("reason", ["ingest_already_running", "some_other_reason"])
    async def test_guard_rejections(self, reason):
        document = make_document()
        factory, status_cls, publisher_cls, ingest_cls = self._patches(document=document)
        status_cls.return_value.check_ingest_allowed = AsyncMock(
            return_value={"allowed": False, "reason": reason, "active_stages": ["extract"]},
        )
        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire = AsyncMock(return_value=True)
        redis.lock.return_value = lock

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls):
            if reason == "ingest_already_running":
                result = await stream_router.start_ingest(
                    document_id=str(DOC_ID), user=make_user(), session=AsyncMock(), redis=redis,
                )
                assert result["already_running"] is True
                assert result["active_stages"] == ["extract"]
            else:
                with pytest.raises(HTTPException) as exc:
                    await stream_router.start_ingest(
                        document_id=str(DOC_ID), user=make_user(), session=AsyncMock(), redis=redis,
                    )
                assert exc.value.status_code == 409
                assert exc.value.detail["reason"] == reason
                assert exc.value.detail["error"] == "Ingest not allowed"

        ingest_cls.return_value.start_ingest.assert_not_awaited()
        lock.release.assert_awaited_once()

    async def test_document_archived_guard_maps_to_conflict(self):
        document = make_document()
        factory, status_cls, publisher_cls, _ = self._patches(document=document)
        status_cls.return_value.check_ingest_allowed = AsyncMock(
            return_value={"allowed": False, "reason": "document_archived"},
        )
        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire = AsyncMock(return_value=True)
        redis.lock.return_value = lock

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls):
            with pytest.raises(HTTPException) as exc:
                await stream_router.start_ingest(
                    document_id=str(DOC_ID), user=make_user(), session=AsyncMock(),
                    redis=redis,
                )

        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "Document is archived"

    async def test_happy_path_publishes_and_releases_lock(self):
        document = make_document()
        user = make_user()
        session = AsyncMock()
        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire = AsyncMock(return_value=True)
        redis.lock.return_value = lock
        factory, status_cls, publisher_cls, ingest_cls = self._patches(document=document)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls), \
                patch("app.services.rag_ingest_service.RAGIngestService", ingest_cls):
            result = await stream_router.start_ingest(
                document_id=str(DOC_ID), user=user, session=session, redis=redis,
            )

        assert result["status"] == "success"
        assert result["embedding_models"] == ["text-embed-x"]

        publisher_cls.assert_called_once_with(redis)
        publisher_cls.return_value.publish_ingest_started.assert_awaited_once_with(
            doc_id=DOC_ID, tenant_id=document.tenant_id, user_id=user.id,
        )
        request = ingest_cls.return_value.start_ingest.await_args.args[0]
        assert request.document_id == DOC_ID
        ingest_cls.assert_called_once_with(session, factory, status_cls.return_value)
        lock.release.assert_awaited_once()

    async def test_without_redis_locking_is_skipped(self):
        document = make_document()
        factory, status_cls, publisher_cls, ingest_cls = self._patches(document=document)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls), \
                patch("app.services.rag_ingest_service.RAGIngestService", ingest_cls):
            result = await stream_router.start_ingest(
                document_id=str(DOC_ID), user=make_user(), session=AsyncMock(), redis=None,
            )

        assert result["status"] == "success"

    async def test_release_failure_is_swallowed(self):
        document = make_document()
        factory, status_cls, publisher_cls, ingest_cls = self._patches(document=document)
        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire = AsyncMock(return_value=True)
        lock.release = AsyncMock(side_effect=RuntimeError("lock lost"))
        redis.lock.return_value = lock

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls), \
                patch("app.services.rag_ingest_service.RAGIngestService", ingest_cls):
            result = await stream_router.start_ingest(
                document_id=str(DOC_ID), user=make_user(), session=AsyncMock(), redis=redis,
            )

        assert result["status"] == "success"


class TestStopIngest:
    async def _run(self, *, stage, node=None, stop_result=None, policy=None,
                   document=None, user=None, linked=True):
        document = document or make_document()
        user = user or make_user()
        factory = factory_mock(document)
        status_cls = status_manager_cls_mock()
        if policy is not None:
            status_cls.return_value.get_ingest_policy = AsyncMock(return_value=policy)
        status_cls.return_value.status_repo.get_node = AsyncMock(return_value=node)
        status_cls.return_value.stop_stage = AsyncMock(return_value=stop_result)
        publisher_cls = MagicMock()
        celery = MagicMock()

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=linked)), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls), \
                patch("app.celery_app.app.control", celery):
            result = await stream_router.stop_ingest(
                document_id=str(DOC_ID), stage=stage, user=user,
                session=AsyncMock(), redis=MagicMock(),
            )
        return result, factory, status_cls, celery

    async def test_invalid_document_id(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.stop_ingest(
                document_id="nope", stage="extract", user=make_user(),
                session=AsyncMock(), redis=MagicMock(),
            )
        assert exc.value.status_code == 400

    async def test_document_not_found(self):
        factory = factory_mock(None)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.stop_ingest(
                    document_id=str(DOC_ID), stage="extract", user=make_user(),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 404

    async def test_unlinked_reader_is_denied(self):
        factory = factory_mock(make_document())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.stop_ingest(
                    document_id=str(DOC_ID), stage="extract", user=make_user("reader"),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403

    async def test_unlinked_editor_from_other_tenant_is_denied(self):
        factory = factory_mock(make_document())
        other_tenant = str(uuid4())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.stop_ingest(
                    document_id=str(DOC_ID), stage="extract",
                    user=make_user("editor", tenant_ids=[other_tenant]),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Access denied"

    async def test_pipeline_stage_without_stoppable_controls(self):
        with pytest.raises(HTTPException) as exc:
            await self._run(stage="pipeline", policy={"controls": [
                {"can_stop": False, "node_type": "pipeline", "stage": "extract"},
            ]})
        assert exc.value.status_code == 409
        assert exc.value.detail["reason"] == "stage_not_stoppable"

    async def test_pipeline_stage_prefers_pipeline_control(self):
        node = SimpleNamespace(status="processing")
        result, _, status_cls, celery = await self._run(
            stage="pipeline", node=node, stop_result="celery-1",
            policy={"controls": [
                {"can_stop": True, "node_type": "embedding", "stage": "embed.model-b"},
                {"can_stop": True, "node_type": "pipeline", "stage": "extract"},
            ]},
        )

        status_cls.return_value.status_repo.get_node.assert_awaited_once_with(
            DOC_ID, "pipeline", "extract",
        )
        status_cls.return_value.stop_stage.assert_awaited_once_with(DOC_ID, "extract")
        celery.revoke.assert_called_once_with("celery-1", terminate=True, signal="SIGTERM")
        assert result["stage"] == "extract"
        assert result["message"] == "Stage extract stopped"

    async def test_pipeline_stage_falls_back_to_first_stoppable(self):
        node = SimpleNamespace(status="queued")
        result, _, status_cls, _ = await self._run(
            stage="pipeline", node=node, stop_result=None,
            policy={"controls": [
                {"can_stop": True, "node_type": "embedding", "stage": "embed.model-b"},
            ]},
        )

        status_cls.return_value.status_repo.get_node.assert_awaited_once_with(
            DOC_ID, "embedding", "model-b",
        )
        assert result["stage"] == "embed.model-b"

    async def test_missing_node_is_not_found(self):
        with pytest.raises(HTTPException) as exc:
            await self._run(stage="extract", node=None)
        assert exc.value.status_code == 404
        assert exc.value.detail["reason"] == "stage_not_found"

    async def test_finished_stage_is_not_stoppable(self):
        node = SimpleNamespace(status="completed")

        with pytest.raises(HTTPException) as exc:
            await self._run(stage="extract", node=node)
        assert exc.value.status_code == 409
        assert exc.value.detail["status"] == "completed"

    async def test_embed_stage_resolves_embedding_node(self):
        node = SimpleNamespace(status="queued")
        result, _, status_cls, celery = await self._run(
            stage="embed.model-a", node=node, stop_result="celery-2",
        )

        status_cls.return_value.status_repo.get_node.assert_awaited_once_with(
            DOC_ID, "embedding", "model-a",
        )
        celery.revoke.assert_called_once_with("celery-2", terminate=True, signal="SIGTERM")
        assert result["message"] == "Stage embed.model-a stopped"

    async def test_revoke_failure_is_swallowed(self):
        node = SimpleNamespace(status="processing")
        celery_before = MagicMock()
        celery_before.revoke.side_effect = RuntimeError("broker down")

        document = make_document()
        factory = factory_mock(document)
        status_cls = status_manager_cls_mock()
        status_cls.return_value.status_repo.get_node = AsyncMock(return_value=node)
        status_cls.return_value.stop_stage = AsyncMock(return_value="celery-3")

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=True)), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", MagicMock()), \
                patch("app.celery_app.app.control", celery_before):
            result = await stream_router.stop_ingest(
                document_id=str(DOC_ID), stage="extract", user=make_user(),
                session=AsyncMock(), redis=MagicMock(),
            )

        assert result["status"] == "success"

    async def test_no_celery_task_id_skips_revoke(self):
        node = SimpleNamespace(status="queued")

        _, _, _, celery = await self._run(stage="extract", node=node, stop_result=None)

        celery.revoke.assert_not_called()


class TestRetryIngest:
    async def _run(self, *, stage, node=None, document=None, user=None, linked=True):
        document = document or make_document()
        user = user or make_user()
        factory = factory_mock(document)
        status_cls = status_manager_cls_mock()
        status_cls.return_value.status_repo.get_node = AsyncMock(return_value=node)
        publisher_cls = MagicMock()
        ingest_cls = MagicMock()
        ingest_cls.return_value.retry_failed = AsyncMock()
        ingest_cls.return_value.reindex_document = AsyncMock()

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=linked)), \
                patch(f"{STREAM_MODULE}._ensure_worker_ready", AsyncMock()), \
                patch("app.services.rag_status_manager.RAGStatusManager", status_cls), \
                patch("app.services.rag_event_publisher.RAGEventPublisher", publisher_cls), \
                patch("app.services.rag_ingest_service.RAGIngestService", ingest_cls):
            result = await stream_router.retry_ingest(
                document_id=str(DOC_ID), stage=stage, user=user,
                session=AsyncMock(), redis=MagicMock(),
            )
        return result, factory, status_cls, ingest_cls

    async def test_invalid_document_id(self):
        with pytest.raises(HTTPException) as exc:
            await stream_router.retry_ingest(
                document_id="nope", stage="extract", user=make_user(),
                session=AsyncMock(), redis=MagicMock(),
            )
        assert exc.value.status_code == 400

    async def test_document_not_found(self):
        factory = factory_mock(None)

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.retry_ingest(
                    document_id=str(DOC_ID), stage="extract", user=make_user(),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 404

    async def test_unlinked_reader_is_denied(self):
        factory = factory_mock(make_document())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.retry_ingest(
                    document_id=str(DOC_ID), stage="extract", user=make_user("reader"),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Insufficient permissions"

    async def test_unlinked_editor_from_other_tenant_is_denied(self):
        factory = factory_mock(make_document())
        other_tenant = str(uuid4())

        with patch("app.repositories.factory.get_async_repository_factory", MagicMock(return_value=factory)), \
                patch(f"{STREAM_MODULE}.require_linked_document_content_access", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await stream_router.retry_ingest(
                    document_id=str(DOC_ID), stage="extract",
                    user=make_user("editor", tenant_ids=[other_tenant]),
                    session=AsyncMock(), redis=MagicMock(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Access denied"

    async def test_unsupported_stage_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await self._run(stage="chunk", node=SimpleNamespace(status="failed"))
        assert exc.value.status_code == 409
        assert exc.value.detail["reason"] == "retry_not_supported"

    async def test_missing_node_is_not_found(self):
        with pytest.raises(HTTPException) as exc:
            await self._run(stage="extract", node=None)
        assert exc.value.status_code == 404
        assert exc.value.detail["reason"] == "stage_not_found"

    @pytest.mark.parametrize("status_value", ["processing", "queued"])
    async def test_running_stage_cannot_be_retried(self, status_value):
        with pytest.raises(HTTPException) as exc:
            await self._run(stage="extract", node=SimpleNamespace(status=status_value))
        assert exc.value.status_code == 409
        assert exc.value.detail["reason"] == "stage_already_running"
        assert exc.value.detail["status"] == status_value

    async def test_extract_retry_uses_retry_failed(self):
        from app.schemas.common import Step

        result, _, _, ingest_cls = await self._run(
            stage="extract", node=SimpleNamespace(status="failed"),
        )

        ingest_cls.return_value.retry_failed.assert_awaited_once_with(DOC_ID, Step.EXTRACT)
        ingest_cls.return_value.reindex_document.assert_not_awaited()
        assert result["message"] == "Stage restarted"

    async def test_embed_stage_uses_reindex_document(self):
        result, _, status_cls, ingest_cls = await self._run(
            stage="embed.model-b", node=SimpleNamespace(status="failed"),
        )

        status_cls.return_value.status_repo.get_node.assert_awaited_once_with(
            DOC_ID, "embedding", "model-b",
        )
        ingest_cls.return_value.reindex_document.assert_awaited_once_with(DOC_ID, "model-b")
        ingest_cls.return_value.retry_failed.assert_not_awaited()
        assert result["message"] == "Stage restarted"

    async def test_index_stage_uses_reindex_document(self):
        _, _, _, ingest_cls = await self._run(
            stage="index.model-c", node=SimpleNamespace(status="cancelled"),
        )

        ingest_cls.return_value.reindex_document.assert_awaited_once_with(DOC_ID, "model-c")


class TestHelpers:
    @pytest.mark.parametrize("stage,expected", [
        ("extract", True),
        ("embed.model-a", True),
        ("index.model-b", True),
        ("chunk", False),
        ("extractor", False),
        ("embed", False),
        ("", False),
    ])
    def test_is_retry_supported(self, stage, expected):
        assert stream_router._is_retry_supported(stage) is expected

    def test_rag_problem_builds_detail_with_extras(self):
        problem = stream_router._rag_problem(
            status_code=409, error="boom", reason="why", stage="extract",
        )
        assert problem.status_code == 409
        assert problem.detail == {
            "error": "boom", "reason": "why", "stage": "extract",
        }

    async def test_ensure_worker_ready_passes_when_ping_succeeds(self, monkeypatch):
        celery = MagicMock()
        celery.ping.return_value = {"worker-1": {"ok": "pong"}}
        monkeypatch.setattr("app.celery_app.app.control", celery)

        assert await stream_router._ensure_worker_ready() is None

    async def test_ensure_worker_ready_fails_when_ping_is_empty(self, monkeypatch):
        celery = MagicMock()
        celery.ping.return_value = {}
        monkeypatch.setattr("app.celery_app.app.control", celery)

        with pytest.raises(HTTPException) as exc:
            await stream_router._ensure_worker_ready()
        assert exc.value.status_code == 503
        assert exc.value.detail["reason"] == "worker_unavailable"


class TestKnownIssues:
    """Tests that pin currently broken behavior (see the phase 2 report)."""

    # FIXME(known issue): rag/stream.py calls get_async_repository_factory(...)
    # without `await`, but the factory is `async def`, so in production
    # repo_factory is a coroutine and every document endpoint of this router
    # (GET /{document_id}, POST .../ingest/start|stop|retry) fails with
    # AttributeError: 'coroutine' object has no attribute
    # 'get_rag_documents_repository' (plus a "coroutine was never awaited"
    # warning). The tests above exercise the intended downstream logic through
    # a sync MagicMock seam; these tests pin the broken behavior itself until
    # the missing awaits are fixed.
    @pytest.mark.parametrize("endpoint", ["status", "start", "stop", "retry"])
    async def test_factory_call_without_await_breaks_document_endpoints(self, endpoint):
        factory = factory_mock(make_document())
        user = make_user()
        redis = MagicMock()

        # Default patch() of an async def target creates an AsyncMock: the
        # router's synchronous call returns a coroutine, exactly as in prod.
        with patch("app.repositories.factory.get_async_repository_factory", return_value=factory):
            with pytest.raises(AttributeError, match="get_rag_documents_repository"):
                if endpoint == "status":
                    await stream_router.get_document_status(
                        document_id=str(DOC_ID), user=user, session=AsyncMock(),
                    )
                elif endpoint == "start":
                    await stream_router.start_ingest(
                        document_id=str(DOC_ID), user=user, session=AsyncMock(), redis=redis,
                    )
                elif endpoint == "stop":
                    await stream_router.stop_ingest(
                        document_id=str(DOC_ID), stage="extract", user=user,
                        session=AsyncMock(), redis=redis,
                    )
                else:
                    await stream_router.retry_ingest(
                        document_id=str(DOC_ID), stage="extract", user=user,
                        session=AsyncMock(), redis=redis,
                    )
