"""Unit tests for app/workers/tasks_cleanup.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.workers import tasks_cleanup


class FakeResult:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Routes delete() statements to a FIFO and selects by lead entity."""

    def __init__(self):
        self.delete_results: list[FakeResult] = []
        self.select_results: dict[type, list[FakeResult]] = {}
        self.get_map: dict[tuple, object] = {}
        self.executed: list[object] = []
        self.get_calls: list[tuple] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()

    def queue_select(self, entity, rows):
        self.select_results.setdefault(entity, []).append(FakeResult(rows=rows))

    async def execute(self, stmt):
        self.executed.append(stmt)
        if getattr(stmt, "__visit_name__", "") == "delete":
            return self.delete_results.pop(0)
        entity = stmt.column_descriptions[0]["entity"]
        queue = self.select_results.get(entity)
        if queue:
            return queue.pop(0)
        return FakeResult(rows=[])

    async def get(self, model, entity_id):
        self.get_calls.append((model, entity_id))
        return self.get_map.get((model, entity_id))


def make_session_scope(session):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


class TestCleanupOldAuditLogs:
    def test_deletes_old_rows_and_commits(self, monkeypatch):
        session = FakeSession()
        session.delete_results.append(FakeResult(rowcount=5))
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        assert tasks_cleanup.cleanup_old_audit_logs.run() == 5
        assert len(session.executed) == 1
        session.commit.assert_awaited_once()

    def test_retries_on_error(self, monkeypatch):
        session = FakeSession()

        async def failing_execute(_stmt):
            raise RuntimeError("db down")

        session.execute = failing_execute
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.cleanup_old_audit_logs.run()


class TestCleanupOldRuntimeEvents:
    def test_deletes_events_and_orphan_sequences(self, monkeypatch):
        session = FakeSession()
        session.delete_results.append(FakeResult(rowcount=10))
        session.delete_results.append(FakeResult(rowcount=4))
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(
            tasks_cleanup, "get_settings", lambda: SimpleNamespace(TOOL_RESULTS_RETENTION_DAYS=14)
        )

        assert tasks_cleanup.cleanup_old_runtime_events.run() == 10
        assert len(session.executed) == 2
        assert getattr(session.executed[0], "__visit_name__", "") == "delete"
        assert getattr(session.executed[1], "__visit_name__", "") == "delete"
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    def test_rolls_back_and_retries_on_error(self, monkeypatch):
        session = FakeSession()
        session.delete_results.append(FakeResult(rowcount=10))

        async def failing_execute(_stmt):
            raise RuntimeError("db down")

        session.execute = failing_execute
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(
            tasks_cleanup, "get_settings", lambda: SimpleNamespace(TOOL_RESULTS_RETENTION_DAYS=14)
        )

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.cleanup_old_runtime_events.run()
        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()


class TestCleanupExpiredSandboxSessions:
    def test_deletes_each_expired_session_and_counts_successes(self, monkeypatch):
        session = FakeSession()
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        session.queue_select(tasks_cleanup.SandboxSession, ids)
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        delete_session = AsyncMock(side_effect=[True, False, True])
        created_with = []

        class RecordingSandboxService:
            def __init__(self, actual_session):
                created_with.append(actual_session)
                self.delete_session = delete_session

        monkeypatch.setattr(tasks_cleanup, "SandboxService", RecordingSandboxService)

        assert tasks_cleanup.cleanup_expired_sandbox_sessions.run() == 2
        assert created_with == [session]
        assert [call.args[0] for call in delete_session.await_args_list] == ids
        session.commit.assert_awaited_once()


class TestCleanupDetachedChatAttachments:
    def test_uses_service_with_24h_cutoff_and_commits(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        cleanup = AsyncMock(return_value=7)
        created_with = []

        class RecordingService:
            def __init__(self, actual_session):
                created_with.append(actual_session)
                self.cleanup_expired_detached_attachments = cleanup

        monkeypatch.setattr(tasks_cleanup, "ChatAttachmentService", RecordingService)
        before = datetime.now(timezone.utc)

        assert tasks_cleanup.cleanup_expired_detached_chat_attachments.run() == 7
        assert created_with == [session]
        older_than = cleanup.await_args.kwargs["older_than"]
        expected = before - timedelta(hours=tasks_cleanup.DETACHED_CHAT_ATTACHMENT_RETENTION_HOURS)
        assert expected - timedelta(seconds=5) <= older_than <= expected + timedelta(seconds=5)
        session.commit.assert_awaited_once()


class TestCleanupOrphanedChatAttachments:
    def test_combines_reference_and_storage_cleanup(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        ref_cleanup = AsyncMock(return_value=3)
        storage_cleanup = AsyncMock(return_value=4)
        storage_sessions = []

        class RecordingReferenceService:
            def __init__(self, _session):
                self.cleanup_orphaned_attachments = ref_cleanup

        class RecordingStorageService:
            def __init__(self, actual_session):
                storage_sessions.append(actual_session)
                self.cleanup = storage_cleanup

        monkeypatch.setattr(tasks_cleanup, "ChatArtifactReferenceService", RecordingReferenceService)
        monkeypatch.setattr(
            "app.services.runtime_storage_cleanup_service.RuntimeStorageCleanupService",
            RecordingStorageService,
        )

        assert tasks_cleanup.cleanup_orphaned_chat_attachments.run() == 7
        ref_cleanup.assert_awaited_once()
        storage_cleanup.assert_awaited_once()
        assert storage_sessions == [session]
        assert storage_cleanup.await_args.kwargs["older_than"] is not None
        session.commit.assert_awaited_once()


class TestCleanupExpiredChatAttachments:
    def test_uses_retention_setting_and_returns_count(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(
            tasks_cleanup, "get_settings", lambda: SimpleNamespace(CHAT_ATTACHMENT_RETENTION_DAYS=30)
        )

        cleanup = AsyncMock(return_value=9)

        class RecordingService:
            def __init__(self, _session):
                self.cleanup_expired_chat_attachments = cleanup

        monkeypatch.setattr(tasks_cleanup, "ChatArtifactReferenceService", RecordingService)

        assert tasks_cleanup.cleanup_expired_chat_attachments.run() == 9
        older_than = cleanup.await_args.kwargs["older_than"]
        assert older_than is not None
        assert (datetime.now(timezone.utc) - older_than) > timedelta(days=29)
        session.commit.assert_awaited_once()

    def test_retries_on_error(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(
            tasks_cleanup, "get_settings", lambda: SimpleNamespace(CHAT_ATTACHMENT_RETENTION_DAYS=30)
        )

        class FailingService:
            def __init__(self, _session):
                self.cleanup_expired_chat_attachments = AsyncMock(
                    side_effect=RuntimeError("storage down")
                )

        monkeypatch.setattr(tasks_cleanup, "ChatArtifactReferenceService", FailingService)

        with pytest.raises(RuntimeError, match="storage down"):
            tasks_cleanup.cleanup_expired_chat_attachments.run()


class TestCleanupExpiredFileDataIndexes:
    def test_returns_disposed_index_count(self, monkeypatch):
        cleanup = AsyncMock(return_value=5)
        monkeypatch.setattr(
            "app.services.file_data_service.FileDataService.cleanup_expired_indexes", cleanup
        )

        assert tasks_cleanup.cleanup_expired_file_data_indexes.run() == 5
        cleanup.assert_awaited_once_with()

    def test_retries_on_error(self, monkeypatch):
        cleanup = AsyncMock(side_effect=ValueError("index corrupt"))
        monkeypatch.setattr(
            "app.services.file_data_service.FileDataService.cleanup_expired_indexes", cleanup
        )

        with pytest.raises(ValueError, match="index corrupt"):
            tasks_cleanup.cleanup_expired_file_data_indexes.run()


class TestCleanupDeprecatedEntities:
    def test_handles_delete_not_found_value_error_and_generic_error(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        user_model = tasks_cleanup.Users
        collection_model = tasks_cleanup.Collection
        agent_model = tasks_cleanup.Agent

        u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        c1, a1 = uuid.uuid4(), uuid.uuid4()
        session.queue_select(user_model, [u1, u2, u3])
        session.queue_select(collection_model, [c1])
        session.queue_select(agent_model, [a1])
        session.get_map = {
            (user_model, u1): SimpleNamespace(delete_cascade=False),
            (user_model, u2): SimpleNamespace(delete_cascade=False),
            # u3 intentionally missing: session.get returns None
            (collection_model, c1): SimpleNamespace(delete_cascade=True),
            (agent_model, a1): SimpleNamespace(delete_cascade=False),
        }

        hard_delete = AsyncMock(
            side_effect=[None, ValueError("not_found"), ValueError("referenced by chat"), RuntimeError("db down")]
        )
        created_with = []

        class RecordingLifecycleService:
            def __init__(self, actual_session):
                created_with.append(actual_session)
                self.hard_delete = hard_delete

        monkeypatch.setattr(tasks_cleanup, "LifecycleAdminService", RecordingLifecycleService)

        result = tasks_cleanup.cleanup_deprecated_entities.run()

        assert result == {
            "tenant": 0,
            "user": 1,
            "collection": 0,
            "agent": 0,
            "rbac_rule": 0,
            "chat": 0,
            "sandbox_session": 0,
            "memory_scope": 0,
        }
        assert created_with[0] is session
        assert [(call.args[0], call.args[1], call.kwargs["cascade"]) for call in hard_delete.await_args_list] == [
            ("user", u1, False),
            ("user", u2, False),
            ("collection", c1, True),
            ("agent", a1, False),
        ]
        # one successful commit + three rollbacks (not_found, value error, generic)
        session.commit.assert_awaited_once()
        assert session.rollback.await_count == 3
        # u3 was looked up but never hard-deleted
        assert (user_model, u3) in session.get_calls

    def test_retries_when_query_fails(self, monkeypatch):
        session = FakeSession()

        async def failing_execute(_stmt):
            raise RuntimeError("db down")

        session.execute = failing_execute
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.cleanup_deprecated_entities.run()


class TestRunAllCleanup:
    def _stub_task(self, payload, delay=None):
        delay_mock = delay if delay is not None else Mock(
            return_value=SimpleNamespace(get=Mock(return_value=payload))
        )
        return SimpleNamespace(delay=delay_mock)

    def test_fans_out_seven_cleanup_tasks(self, monkeypatch):
        stubs = {
            "cleanup_old_audit_logs": self._stub_task("audit-ok"),
            "cleanup_old_runtime_events": self._stub_task("events-ok"),
            "cleanup_expired_sandbox_sessions": self._stub_task("sandbox-ok"),
            "cleanup_expired_runtime_tool_results": self._stub_task("tool-results-ok"),
            "cleanup_expired_detached_chat_attachments": self._stub_task("detached-ok"),
            "cleanup_orphaned_chat_attachments": self._stub_task("orphaned-ok"),
            "cleanup_deprecated_entities": self._stub_task("deprecated-ok"),
        }
        for name, stub in stubs.items():
            monkeypatch.setattr(tasks_cleanup, name, stub)

        result = tasks_cleanup.run_all_cleanup.run()

        assert result == {
            "audit_logs": "audit-ok",
            "runtime_events": "events-ok",
            "sandbox_sessions": "sandbox-ok",
            "runtime_tool_results": "tool-results-ok",
            "detached_chat_attachments": "detached-ok",
            "orphaned_chat_attachments": "orphaned-ok",
            "deprecated_entities": "deprecated-ok",
        }
        for stub in stubs.values():
            stub.delay.assert_called_once_with()
            stub.delay.return_value.get.assert_called_once_with(timeout=300)

    def test_records_error_when_task_fails(self, monkeypatch):
        failing_delay = Mock(side_effect=TimeoutError("broker timeout"))
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_old_audit_logs", self._stub_task(None, delay=failing_delay)
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_old_runtime_events", self._stub_task("events-ok")
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_expired_sandbox_sessions", self._stub_task("sandbox-ok")
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_expired_runtime_tool_results", self._stub_task("tool-results-ok")
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_expired_detached_chat_attachments", self._stub_task("detached-ok")
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_orphaned_chat_attachments", self._stub_task("orphaned-ok")
        )
        monkeypatch.setattr(
            tasks_cleanup, "cleanup_deprecated_entities", self._stub_task("deprecated-ok")
        )

        result = tasks_cleanup.run_all_cleanup.run()

        assert result["audit_logs"] == "error: broker timeout"
        assert result["runtime_events"] == "events-ok"


class TestExpireChatContextItems:
    def test_expires_due_items_and_commits(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        created_with = []
        limits = []

        class RecordingContextRepository:
            def __init__(self, actual_session):
                created_with.append(actual_session)

            async def expire_due_items(self, limit):
                limits.append(limit)
                return 12

        monkeypatch.setattr(tasks_cleanup, "ChatContextRepository", RecordingContextRepository)

        assert tasks_cleanup.expire_chat_context_items.run() == {"expired": 12}
        assert created_with == [session]
        assert limits == [tasks_cleanup.CHAT_CONTEXT_EXPIRY_BATCH_SIZE]
        session.commit.assert_awaited_once()

    def test_rolls_back_and_propagates_error(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        class FailingContextRepository:
            def __init__(self, _session):
                pass

            async def expire_due_items(self, limit):
                raise RuntimeError("db down")

        monkeypatch.setattr(tasks_cleanup, "ChatContextRepository", FailingContextRepository)

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.expire_chat_context_items.run()
        session.rollback.assert_awaited_once()


class TestCleanupExpiredRuntimeToolResults:
    def test_deletes_expired_results_and_returns_rowcount(self, monkeypatch):
        session = FakeSession()
        session.delete_results.append(FakeResult(rowcount=3))
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        assert tasks_cleanup.cleanup_expired_runtime_tool_results.run() == 3
        assert len(session.executed) == 1
        assert getattr(session.executed[0], "__visit_name__", "") == "delete"
        session.commit.assert_awaited_once()

    def test_retries_on_error(self, monkeypatch):
        session = FakeSession()

        async def failing_execute(_stmt):
            raise RuntimeError("db down")

        session.execute = failing_execute
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.cleanup_expired_runtime_tool_results.run()


class FakeToolResultsEngine:
    def __init__(self, *, rowcount=0, execute_error=None, begin_error=None):
        self.rowcount = rowcount
        self.execute_error = execute_error
        self.begin_error = begin_error
        self.executed_sql: list[str] = []
        self.dispose = AsyncMock()

    async def _execute(self, stmt):
        self.executed_sql.append(getattr(stmt, "text", str(stmt)))
        if self.execute_error is not None:
            raise self.execute_error
        return FakeResult(rowcount=self.rowcount)

    @asynccontextmanager
    async def begin(self):
        if self.begin_error is not None:
            raise self.begin_error
        yield SimpleNamespace(execute=self._execute)


class TestCleanupExpiredToolPayloads:
    def test_deletes_expired_payloads_and_disposes_engine(self, monkeypatch):
        engine = FakeToolResultsEngine(rowcount=4)
        monkeypatch.setattr(
            "app.services.tool_result_store.create_tool_results_engine", lambda: engine
        )

        assert tasks_cleanup.cleanup_expired_tool_payloads.run() == 4
        assert len(engine.executed_sql) == 1
        assert "runtime_tool_payloads" in engine.executed_sql[0]
        assert "LIMIT 5000" in engine.executed_sql[0]
        engine.dispose.assert_awaited_once()

    def test_retries_on_error_and_still_disposes_engine(self, monkeypatch):
        engine = FakeToolResultsEngine(execute_error=RuntimeError("store down"))
        monkeypatch.setattr(
            "app.services.tool_result_store.create_tool_results_engine", lambda: engine
        )

        with pytest.raises(RuntimeError, match="store down"):
            tasks_cleanup.cleanup_expired_tool_payloads.run()
        engine.dispose.assert_awaited_once()


class TestCleanupRetryBranches:
    def test_sandbox_sessions_retries_on_error(self, monkeypatch):
        session = FakeSession()

        async def failing_execute(_stmt):
            raise RuntimeError("db down")

        session.execute = failing_execute
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        with pytest.raises(RuntimeError, match="db down"):
            tasks_cleanup.cleanup_expired_sandbox_sessions.run()

    def test_detached_chat_attachments_retries_on_error(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        class FailingAttachmentService:
            def __init__(self, _session):
                self.cleanup_expired_detached_attachments = AsyncMock(
                    side_effect=RuntimeError("storage down")
                )

        monkeypatch.setattr(tasks_cleanup, "ChatAttachmentService", FailingAttachmentService)

        with pytest.raises(RuntimeError, match="storage down"):
            tasks_cleanup.cleanup_expired_detached_chat_attachments.run()

    def test_orphaned_chat_attachments_retries_on_error(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_cleanup, "get_worker_session", make_session_scope(session))

        class FailingReferenceService:
            def __init__(self, _session):
                self.cleanup_orphaned_attachments = AsyncMock(
                    side_effect=RuntimeError("reference down")
                )

        monkeypatch.setattr(tasks_cleanup, "ChatArtifactReferenceService", FailingReferenceService)

        with pytest.raises(RuntimeError, match="reference down"):
            tasks_cleanup.cleanup_orphaned_chat_attachments.run()


class TestRunAllCleanupAllFailures:
    def _stub_failing_task(self):
        failing_delay = Mock(side_effect=TimeoutError("broker down"))
        return SimpleNamespace(delay=failing_delay)

    def test_records_error_for_every_task(self, monkeypatch):
        names = [
            "cleanup_old_audit_logs",
            "cleanup_old_runtime_events",
            "cleanup_expired_sandbox_sessions",
            "cleanup_expired_runtime_tool_results",
            "cleanup_expired_detached_chat_attachments",
            "cleanup_orphaned_chat_attachments",
            "cleanup_deprecated_entities",
        ]
        for name in names:
            monkeypatch.setattr(tasks_cleanup, name, self._stub_failing_task())

        result = tasks_cleanup.run_all_cleanup.run()

        assert set(result) == {
            "audit_logs",
            "runtime_events",
            "sandbox_sessions",
            "runtime_tool_results",
            "detached_chat_attachments",
            "orphaned_chat_attachments",
            "deprecated_entities",
        }
        assert all(value == "error: broker down" for value in result.values())
