"""Unit tests for app/workers/tasks_rag_ingest/dispatch.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.rag_ingest import RAGIngestRun, RAGIngestStageOutbox
from app.workers.tasks_rag_ingest import dispatch as dispatch_mod


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
    """Routes scalar() calls to a FIFO and selects by lead entity."""

    def __init__(self):
        self.select_results: dict[type, list[FakeResult]] = {}
        self.scalar_values: list[object] = []
        self.executed: list[object] = []
        self.added: list[object] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.flush = AsyncMock()

    def queue_select(self, entity, rows):
        self.select_results.setdefault(entity, []).append(FakeResult(rows=rows))

    def queue_scalar(self, value):
        self.scalar_values.append(value)

    async def execute(self, stmt):
        self.executed.append(stmt)
        entity = stmt.column_descriptions[0]["entity"]
        queue = self.select_results.get(entity)
        if queue:
            return queue.pop(0)
        return FakeResult(rows=[])

    async def scalar(self, stmt):
        self.executed.append(stmt)
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    def add(self, obj):
        self.added.append(obj)


def make_session_scope(session):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def make_run(**over):
    base = dict(
        id=uuid.uuid4(),
        doc_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        generation=1,
        status="queued",
        resume_stage=None,
        started_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def make_document(run, **over):
    base = dict(id=run.doc_id, ingest_generation=run.generation)
    base.update(over)
    return SimpleNamespace(**base)


def make_stage_command(run, **over):
    base = dict(
        id=uuid.uuid4(),
        run_id=run.id,
        stage_key="extract",
        payload={"canonical_key": "k"},
        status="pending",
        attempts=0,
        celery_task_id=None,
        last_error=None,
        available_at=datetime.now(timezone.utc),
        dispatched_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def patch_status_manager(monkeypatch, node=None):
    """Replace dispatch.RAGStatusManager; returns (instances, get_node mock)."""
    instances = []
    get_node = AsyncMock(return_value=node)

    class _Manager:
        def __init__(self, session, repo_factory):
            instances.append((session, repo_factory))
            self.status_repo = SimpleNamespace(get_node=get_node)

        @staticmethod
        def _split_stage_name(stage):
            if "." in stage:
                node_type, node_key = stage.split(".", 1)
                return node_type, node_key
            return stage, ""

    monkeypatch.setattr(dispatch_mod, "RAGStatusManager", _Manager)
    return instances, get_node


class TestDispatchOutbox:
    def _queue_pair(self, session, run, document):
        session.queue_scalar(run.doc_id)
        session.queue_scalar(document)

    def test_returns_none_when_run_lookup_misses(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) is None
        assert len(session.executed) == 1  # only the doc_id scalar ran

    def test_returns_none_when_document_missing(self, monkeypatch):
        session = FakeSession()
        run = make_run()
        self._queue_pair(session, run, None)
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) is None
        assert len(session.executed) == 2

    def test_returns_none_when_row_not_found(self, monkeypatch):
        session = FakeSession()
        run = make_run()
        self._queue_pair(session, run, make_document(run))
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) is None

    def test_returns_task_id_when_outbox_not_pending(self, monkeypatch):
        session = FakeSession()
        run = make_run()
        outbox = SimpleNamespace(status="dispatched", celery_task_id="task-77")
        self._queue_pair(session, run, make_document(run))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) == "task-77"
        session.commit.assert_not_awaited()

    @pytest.mark.parametrize("run_status", ["cancelled", "failed", "completed"])
    def test_returns_task_id_when_run_terminal(self, monkeypatch, run_status):
        session = FakeSession()
        run = make_run(status=run_status)
        outbox = SimpleNamespace(status="pending", celery_task_id="task-88")
        self._queue_pair(session, run, make_document(run))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) == "task-88"
        session.commit.assert_not_awaited()

    def test_cancels_when_generation_mismatched(self, monkeypatch):
        session = FakeSession()
        run = make_run(generation=3)
        outbox = SimpleNamespace(status="pending", celery_task_id=None)
        self._queue_pair(session, run, make_document(run, ingest_generation=1))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4())) is None
        assert outbox.status == "cancelled"
        assert run.status == "cancelled"
        session.commit.assert_awaited_once()

    def test_dispatches_extract_stage(self, monkeypatch):
        session = FakeSession()
        run = make_run(status="queued", started_at=None)
        outbox = SimpleNamespace(
            id=uuid.uuid4(), run_id=run.id, payload={}, status="pending", attempts=2,
            celery_task_id=None, dispatched_at=None,
        )
        self._queue_pair(session, run, make_document(run))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        created = []

        class FakeStageOutbox:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.id = uuid.uuid4()
                created.append(self)

        monkeypatch.setattr("app.models.rag_ingest.RAGIngestStageOutbox", FakeStageOutbox)
        delay = Mock()
        monkeypatch.setattr(dispatch_mod, "dispatch_rag_ingest_stage_outbox", SimpleNamespace(delay=delay))

        result = dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4()))

        assert len(created) == 1
        command = created[0]
        assert command.run_id == run.id
        assert command.stage_key == "extract"
        assert command.payload == {"source_id": str(run.doc_id)}
        assert command.status == "pending"
        assert session.added == [command]
        assert outbox.status == "dispatched"
        assert outbox.attempts == 3
        assert outbox.dispatched_at is not None
        assert run.status == "running"
        assert run.started_at is not None
        session.commit.assert_awaited_once()
        delay.assert_called_once_with(str(command.id))
        assert result == str(command.id)

    def test_dispatches_embed_resume_stage_and_keeps_source_id(self, monkeypatch):
        session = FakeSession()
        run = make_run(resume_stage="embed")
        outbox = SimpleNamespace(
            run_id=run.id, payload={"model_alias": "m-1", "source_id": "pre-set"},
            status="pending", attempts=0, celery_task_id=None, dispatched_at=None,
        )
        self._queue_pair(session, run, make_document(run))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        created = []

        class FakeStageOutbox:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.id = uuid.uuid4()
                created.append(self)

        monkeypatch.setattr("app.models.rag_ingest.RAGIngestStageOutbox", FakeStageOutbox)
        monkeypatch.setattr(
            dispatch_mod, "dispatch_rag_ingest_stage_outbox", SimpleNamespace(delay=Mock())
        )

        dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4()))

        assert created[0].stage_key == "embed.m-1"
        # setdefault must not overwrite an existing source_id
        assert created[0].payload["source_id"] == "pre-set"
        assert run.started_at is not None

    def test_started_at_preserved_when_already_set(self, monkeypatch):
        session = FakeSession()
        started = datetime(2025, 1, 1, tzinfo=timezone.utc)
        run = make_run(started_at=started)
        outbox = SimpleNamespace(
            run_id=run.id, payload={}, status="pending", attempts=0,
            celery_task_id=None, dispatched_at=None,
        )
        self._queue_pair(session, run, make_document(run))
        from app.models.rag_ingest import RAGIngestOutbox

        session.queue_select(RAGIngestOutbox, [(outbox, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        class FakeStageOutbox:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.id = uuid.uuid4()

        monkeypatch.setattr("app.models.rag_ingest.RAGIngestStageOutbox", FakeStageOutbox)
        monkeypatch.setattr(
            dispatch_mod, "dispatch_rag_ingest_stage_outbox", SimpleNamespace(delay=Mock())
        )

        dispatch_mod.dispatch_rag_ingest_outbox.run(str(uuid.uuid4()))

        assert run.started_at == started


class TestDispatchStageOutbox:
    def _run_and_command(self, **command_over):
        run = make_run(status="queued")
        command = make_stage_command(run, **command_over)
        return run, command

    def _queue(self, monkeypatch, run, document, command):
        session = FakeSession()
        session.queue_scalar(run.doc_id)
        session.queue_scalar(document)
        session.queue_select(RAGIngestStageOutbox, [(command, run)])
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))
        return session

    def test_returns_none_when_run_lookup_misses(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) is None
        assert len(session.executed) == 1

    def test_returns_none_when_document_missing(self, monkeypatch):
        run, command = self._run_and_command()
        session = self._queue(monkeypatch, run, None, command)

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) is None
        assert len(session.executed) == 2

    def test_returns_none_when_row_not_found(self, monkeypatch):
        run, _command = self._run_and_command()
        session = FakeSession()
        session.queue_scalar(run.doc_id)
        session.queue_scalar(make_document(run))
        monkeypatch.setattr(dispatch_mod, "get_worker_session", make_session_scope(session))

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) is None

    def test_returns_task_id_when_command_not_pending(self, monkeypatch):
        run, command = self._run_and_command(status="dispatched", celery_task_id="task-5")
        session = self._queue(monkeypatch, run, make_document(run), command)

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) == "task-5"
        session.commit.assert_not_awaited()

    def test_returns_task_id_when_run_terminal_for_pipeline_stage(self, monkeypatch):
        run, command = self._run_and_command(celery_task_id="task-6")
        run.status = "completed"
        session = self._queue(monkeypatch, run, make_document(run), command)

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) == "task-6"
        session.commit.assert_not_awaited()

    def test_completed_run_proceeds_for_shadow_stage(self, monkeypatch):
        run, command = self._run_and_command(stage_key="shadow")
        run.status = "completed"
        session = self._queue(monkeypatch, run, make_document(run), command)
        instances, _ = patch_status_manager(monkeypatch)
        hipporag = SimpleNamespace(apply_async=Mock(return_value=None))
        monkeypatch.setattr(
            "app.workers.tasks_hipporag_document.index_hipporag_document", hipporag
        )

        result = dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        hipporag.apply_async.assert_called_once()
        args = hipporag.apply_async.call_args.kwargs["args"]
        assert args == [[command.payload], str(run.tenant_id), None, str(run.id)]
        assert result == hipporag.apply_async.call_args.kwargs["task_id"]
        assert command.status == "dispatched"
        # shadow stages never construct the status manager
        assert instances == []

    def test_cancels_on_generation_mismatch(self, monkeypatch):
        run, command = self._run_and_command()
        session = self._queue(monkeypatch, run, make_document(run, ingest_generation=9), command)

        assert dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4())) is None
        assert command.status == "cancelled"
        assert run.status == "cancelled"
        session.commit.assert_awaited_once()

    @pytest.mark.parametrize(
        "stage_key,expected_arg_names",
        [
            ("extract", "extract"),
            ("normalize", "normalize"),
            ("chunk", "chunk"),
            ("embed.m-1", "embed"),
            ("index.m-1", "index"),
        ],
    )
    def test_stage_arg_matrix(self, monkeypatch, stage_key, expected_arg_names):
        run, command = self._run_and_command(stage_key=stage_key)
        node = SimpleNamespace(status="idle", celery_task_id=None, updated_at=None)
        instances, get_node = patch_status_manager(monkeypatch, node=node)
        session = self._queue(monkeypatch, run, make_document(run), command)

        task_attr = {
            "extract": "extract_document",
            "normalize": "normalize_document",
            "chunk": "chunk_document",
            "embed": "embed_chunks_model",
            "index": "index_model",
        }[expected_arg_names]
        task_fn = SimpleNamespace(apply_async=Mock(return_value=None))
        monkeypatch.setattr(f"app.workers.tasks_rag_ingest.{task_attr}", task_fn)

        result = dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        task_fn.apply_async.assert_called_once()
        kwargs = task_fn.apply_async.call_args.kwargs
        assert set(kwargs) == {"args", "task_id"}
        assert result == kwargs["task_id"]
        args = kwargs["args"]
        if expected_arg_names == "extract":
            assert args == [str(run.doc_id), str(run.tenant_id), str(run.id), run.generation]
        elif expected_arg_names in {"normalize", "chunk"}:
            assert args == [command.payload, str(run.tenant_id), str(run.id), run.generation]
        elif expected_arg_names == "embed":
            assert args == [command.payload, str(run.tenant_id), "m-1", str(run.id), run.generation]
        else:
            assert args == [command.payload, str(run.tenant_id), str(run.id), run.generation]

        # queued-node persistence happens before publish
        assert len(instances) == 1
        expected_node = stage_key.split(".", 1) if "." in stage_key else (stage_key, "")
        get_node.assert_awaited_once_with(run.doc_id, *expected_node)
        assert node.status == "queued"
        assert node.celery_task_id == result
        assert node.updated_at is not None
        session.flush.assert_awaited_once()

        assert command.status == "dispatched"
        assert command.celery_task_id == result
        assert command.attempts == 1
        assert command.last_error is None
        assert command.dispatched_at is not None
        session.commit.assert_awaited_once()

    def test_missing_status_node_skips_flush(self, monkeypatch):
        run, command = self._run_and_command(stage_key="index.m-1")
        _instances, get_node = patch_status_manager(monkeypatch, node=None)
        session = self._queue(monkeypatch, run, make_document(run), command)
        task_fn = SimpleNamespace(apply_async=Mock(return_value=None))
        monkeypatch.setattr("app.workers.tasks_rag_ingest.index_model", task_fn)

        dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        get_node.assert_awaited_once()
        session.flush.assert_not_awaited()
        session.commit.assert_awaited_once()

    def test_unknown_stage_raises(self, monkeypatch):
        run, command = self._run_and_command(stage_key="bogus")
        self._queue(monkeypatch, run, make_document(run), command)
        patch_status_manager(monkeypatch, node=None)

        with pytest.raises(ValueError, match="Unsupported RAG ingest stage command: bogus"):
            dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

    def test_hipporag_stage_dispatches_without_status_manager(self, monkeypatch):
        run, command = self._run_and_command(stage_key="hipporag")
        session = self._queue(monkeypatch, run, make_document(run), command)
        instances, _ = patch_status_manager(monkeypatch)
        hipporag = SimpleNamespace(apply_async=Mock(return_value=None))
        monkeypatch.setattr(
            "app.workers.tasks_hipporag_document.index_hipporag_document", hipporag
        )

        result = dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        assert instances == []
        kwargs = hipporag.apply_async.call_args.kwargs
        assert kwargs["args"] == [[command.payload], str(run.tenant_id), None, str(run.id)]
        assert result == kwargs["task_id"]
        assert command.status == "dispatched"
        session.flush.assert_not_awaited()
        session.commit.assert_awaited_once()

    def test_broker_failure_records_error_and_backs_off(self, monkeypatch):
        run, command = self._run_and_command()
        session = self._queue(monkeypatch, run, make_document(run), command)
        patch_status_manager(monkeypatch, node=None)

        def failing_apply_async(**_kwargs):
            raise RuntimeError("broker down")

        monkeypatch.setattr(
            "app.workers.tasks_rag_ingest.extract_document",
            SimpleNamespace(apply_async=failing_apply_async),
        )

        before = datetime.now(timezone.utc)
        with pytest.raises(RuntimeError, match="broker down"):
            dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        assert command.status == "pending"  # stays retryable
        assert command.last_error == "broker publish failed: RuntimeError: broker down"
        assert command.attempts == 1
        # attempts=1 -> backoff 2**1 = 2 seconds
        assert abs((command.available_at - before).total_seconds() - 2) < 10
        session.commit.assert_awaited_once()

    def test_backoff_capped_at_300_seconds(self, monkeypatch):
        run, command = self._run_and_command(attempts=9)
        session = self._queue(monkeypatch, run, make_document(run), command)
        patch_status_manager(monkeypatch, node=None)

        def failing_apply_async(**_kwargs):
            raise RuntimeError("broker down")

        monkeypatch.setattr(
            "app.workers.tasks_rag_ingest.extract_document",
            SimpleNamespace(apply_async=failing_apply_async),
        )

        before = datetime.now(timezone.utc)
        with pytest.raises(RuntimeError, match="broker down"):
            dispatch_mod.dispatch_rag_ingest_stage_outbox.run(str(uuid.uuid4()))

        assert command.attempts == 10
        # min(300, 2**min(10, 8)) == 256
        assert abs((command.available_at - before).total_seconds() - 256) < 10
