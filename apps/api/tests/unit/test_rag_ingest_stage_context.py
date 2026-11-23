"""Unit tests for app.workers.tasks_rag_ingest.stage_context."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.rag_status_manager import StageStatus
from app.workers.tasks_rag_ingest import stage_context as sc
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext

TENANT = uuid.uuid4()
SOURCE = uuid.uuid4()
RUN = uuid.uuid4()

# Routing keys mirroring the entity/expr of each select in stage_context.py
K_RUN = "RAGIngestRun"
K_OUTBOX = "RAGIngestStageOutbox"
K_STAGE_RUN = "RAGIngestStageRun"
K_STATES = "RAGIngestStageRun.status"
K_GEN = "RAGDocument.ingest_generation"


# ── fakes ────────────────────────────────────────────────────────────────


class FakeResult:
    """Result wrapper popping pre-queued values in call order."""

    def __init__(self, pop):
        self._pop = pop

    def scalar_one_or_none(self):
        return self._pop()

    def scalars(self):
        return self

    def all(self):
        return self._pop()

    def first(self):
        return self._pop()


class FakeSession:
    """Session routing execute()/scalar() by select expr to FIFO queues."""

    def __init__(self):
        self.queue: dict[str, deque] = defaultdict(deque)
        self.added: list = []
        self.queries: list[str] = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def q(self, key: str, *items) -> None:
        for item in items:
            self.queue[key].append(item)

    def _pop(self, key: str):
        dq = self.queue.get(key)
        return dq.popleft() if dq else None

    @staticmethod
    def _key(stmt) -> str:
        expr = stmt.column_descriptions[0]["expr"]
        if isinstance(expr, type):
            return expr.__name__
        return f"{expr.class_.__name__}.{expr.key}"

    async def execute(self, stmt):
        key = self._key(stmt)
        self.queries.append(key)
        return FakeResult(lambda: self._pop(key))

    async def scalar(self, stmt):
        key = self._key(stmt)
        self.queries.append(key)
        return self._pop(key)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1
        # Emulate SQLAlchemy applying Python-side column defaults on flush.
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


class FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.setex_calls: list = []

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))


def make_ctx(
    session: FakeSession | None = None,
    redis: FakeRedis | None = None,
    status_manager=None,
    stage_name: str = "extract",
    run_id: uuid.UUID | None = None,
    generation: int | None = None,
    celery_task_id: str | None = None,
) -> IngestStageContext:
    session = session or FakeSession()
    status_manager = status_manager or SimpleNamespace(transition_stage=AsyncMock())
    return IngestStageContext(
        source_id=SOURCE,
        tenant_id=TENANT,
        stage_name=stage_name,
        session=session,
        redis=redis or FakeRedis(),
        settings=SimpleNamespace(S3_BUCKET_RAG="rag-bucket", REDIS_URL="redis://fake"),
        repo_factory=SimpleNamespace(),
        event_publisher=SimpleNamespace(),
        status_manager=status_manager,
        celery_task_id=celery_task_id,
        run_id=run_id,
        generation=generation,
    )


# ── helpers ──────────────────────────────────────────────────────────────


class TestHelperProperties:
    async def test_tenant_id_str(self):
        ctx = make_ctx()
        assert ctx.tenant_id_str == str(TENANT)

    async def test_elapsed_sec_positive_float(self):
        ctx = make_ctx()
        assert isinstance(ctx.elapsed_sec, float)
        assert ctx.elapsed_sec >= 0

    async def test_start_time_independent_per_context(self):
        ctx_a = make_ctx()
        ctx_b = make_ctx()
        assert ctx_a.start_time <= ctx_b.start_time


# ── status shortcuts ─────────────────────────────────────────────────────


class TestSetProcessing:
    async def test_marks_stage_and_stage_run_processing(self):
        session = FakeSession()
        stage_run = SimpleNamespace(status="pending", started_at=None, celery_task_id="old")
        session.q(K_STAGE_RUN, stage_run)
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm, stage_name="extract",
                       run_id=RUN, celery_task_id="celery-1")

        await ctx.set_processing()

        sm.transition_stage.assert_awaited_once_with(
            doc_id=SOURCE, stage="extract",
            new_status=StageStatus.PROCESSING, celery_task_id="celery-1",
        )
        assert stage_run.status == "processing"
        assert stage_run.started_at is not None
        assert stage_run.celery_task_id == "celery-1"
        assert session.commit_calls == 1

    async def test_preserves_existing_started_at(self):
        session = FakeSession()
        from datetime import datetime, timezone
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        stage_run = SimpleNamespace(status="pending", started_at=started, celery_task_id=None)
        session.q(K_STAGE_RUN, stage_run)
        ctx = make_ctx(session=session, stage_name="normalize", run_id=RUN)

        await ctx.set_processing()

        assert stage_run.started_at == started


class TestSetCompleted:
    async def test_transitions_with_metrics(self):
        session = FakeSession()
        stage_run = SimpleNamespace(status="processing", finished_at=None, metrics_json=None)
        session.q(K_STAGE_RUN, stage_run)
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm, stage_name="chunk",
                       run_id=RUN)

        await ctx.set_completed(metrics={"chunks": 5, "model_version": "v2"})

        sm.transition_stage.assert_awaited_once_with(
            doc_id=SOURCE, stage="chunk", new_status=StageStatus.COMPLETED,
            metrics={"chunks": 5, "model_version": "v2"}, model_version="v2",
        )
        assert stage_run.status == "completed"
        assert stage_run.finished_at is not None
        assert stage_run.metrics_json == {"chunks": 5, "model_version": "v2"}
        # set_completed does not commit by itself
        assert session.commit_calls == 0

    async def test_without_metrics_model_version_none(self):
        session = FakeSession()
        session.q(K_STAGE_RUN, None)  # no stage run row
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm, run_id=RUN)

        await ctx.set_completed()

        sm.transition_stage.assert_awaited_once_with(
            doc_id=SOURCE, stage="extract", new_status=StageStatus.COMPLETED,
            metrics=None, model_version=None,
        )


# ── set_failed ───────────────────────────────────────────────────────────


class TestSetFailedSharedStage:
    async def test_cancels_pipeline_and_fails_run(self):
        session = FakeSession()
        chunk_cmd = SimpleNamespace(status="dispatched", last_error=None)
        pending_cmd = SimpleNamespace(status="pending", status_after=None)
        chunk_sr = SimpleNamespace(status="processing")
        later_processing = SimpleNamespace(
            status="processing", stage_key="embed.m1", finished_at=None)
        later_queued = SimpleNamespace(
            status="queued", stage_key="index.m1", finished_at=None)
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, chunk_sr, [later_processing, later_queued])
        session.q(K_OUTBOX, chunk_cmd, [pending_cmd])
        session.q(K_RUN, run, run)
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm,
                       stage_name="chunk", run_id=RUN)

        error = "x" * 600
        await ctx.set_failed(error)

        assert chunk_cmd.status == "failed"
        assert chunk_cmd.last_error == "x" * 500  # truncated
        assert pending_cmd.status == "cancelled"
        assert later_processing.status == "cancelled"
        assert later_processing.finished_at is not None
        assert later_queued.status == "cancelled"
        assert run.status == "failed"
        assert run.error_short == "x" * 500
        assert run.finished_at is not None
        # transition for the failing stage + one per non-terminal later stage
        assert sm.transition_stage.await_count == 3
        assert sm.transition_stage.await_args_list[-1].args == (
            SOURCE, "index.m1", StageStatus.CANCELLED)

    async def test_finalizes_run_when_all_stage_runs_terminal(self):
        session = FakeSession()
        stage_run = SimpleNamespace(status="processing")
        cmd = SimpleNamespace(status="dispatched", last_error=None)
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, stage_run, [])
        session.q(K_OUTBOX, cmd, [])
        session.q(K_RUN, None, run)  # first run lookup misses, final re-fetch hits
        session.q(K_STATES, ["failed", "cancelled"])
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm,
                       stage_name="extract", run_id=RUN)

        await ctx.set_failed("boom")

        assert run.status == "failed"
        assert run.error_short == "boom"
        assert run.finished_at is not None
        assert session.flush_calls >= 1

    async def test_run_left_unfinished_when_stage_runs_not_terminal(self):
        session = FakeSession()
        stage_run = SimpleNamespace(status="processing")
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, stage_run, [])
        session.q(K_OUTBOX, None, [])
        session.q(K_RUN, None, run)
        session.q(K_STATES, ["processing"])
        ctx = make_ctx(session=session, stage_name="normalize", run_id=RUN)

        await ctx.set_failed("boom")

        assert run.status == "running"
        assert run.finished_at is None

    async def test_without_run_id_only_transition(self):
        session = FakeSession()
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm)

        await ctx.set_failed("boom")

        sm.transition_stage.assert_awaited_once_with(
            doc_id=SOURCE, stage="extract",
            new_status=StageStatus.FAILED, error="boom")
        # _update_stage_run early-returns before issuing any query
        assert session.queries == []


class TestSetFailedEmbedBranch:
    async def test_cancels_sibling_index_only(self):
        session = FakeSession()
        embed_sr = SimpleNamespace(status="processing")
        index_run = SimpleNamespace(
            status="pending", finished_at=None)
        embed_cmd = SimpleNamespace(status="dispatched", last_error=None)
        index_cmd = SimpleNamespace(status="pending")
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, embed_sr, index_run)
        session.q(K_OUTBOX, embed_cmd, index_cmd)
        session.q(K_RUN, run, run)
        session.q(K_STATES, ["failed", "cancelled"])
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm,
                       stage_name="embed.m1", run_id=RUN)

        await ctx.set_failed("embed boom")

        assert index_cmd.status == "cancelled"
        assert index_run.status == "cancelled"
        assert index_run.finished_at is not None
        # transition: stage itself FAILED + index.m1 CANCELLED
        assert sm.transition_stage.await_count == 2
        assert sm.transition_stage.await_args_list[-1].args == (
            SOURCE, "index.m1", StageStatus.CANCELLED)
        # embed failure records error but run finalizes only when terminal
        assert run.error_short == "embed boom"
        assert run.status == "failed"
        assert run.finished_at is not None

    async def test_leaves_completed_index_command_and_running_index_run(self):
        session = FakeSession()
        embed_sr = SimpleNamespace(status="processing")
        index_run = SimpleNamespace(status="processing", finished_at=None)
        embed_cmd = SimpleNamespace(status="running", last_error=None)
        index_cmd = SimpleNamespace(status="completed")
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, embed_sr, index_run)
        session.q(K_OUTBOX, embed_cmd, index_cmd)
        session.q(K_RUN, run, run)
        session.q(K_STATES, ["completed"])
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm,
                       stage_name="embed.m1", run_id=RUN)

        await ctx.set_failed("boom")

        assert index_cmd.status == "completed"
        assert index_run.status == "processing"
        assert index_run.finished_at is None
        # all terminal without failures -> run completes, error cleared
        assert run.status == "completed"
        assert run.error_short is None

    async def test_index_stage_failure_sets_error_short_without_cancels(self):
        session = FakeSession()
        index_sr = SimpleNamespace(status="processing")
        index_cmd = SimpleNamespace(status="dispatched", last_error=None)
        run = SimpleNamespace(
            status="running", error_short=None, finished_at=None)
        session.q(K_STAGE_RUN, index_sr, None)
        session.q(K_OUTBOX, index_cmd, None)
        session.q(K_RUN, run, run)
        session.q(K_STATES, ["failed"])
        sm = SimpleNamespace(transition_stage=AsyncMock())
        ctx = make_ctx(session=session, status_manager=sm,
                       stage_name="index.m1", run_id=RUN)

        await ctx.set_failed("index boom")

        assert run.error_short == "index boom"
        assert run.status == "failed"


# ── is_current_generation / mark_stale ──────────────────────────────────


class TestIsCurrentGeneration:
    async def test_true_without_run_id(self):
        ctx = make_ctx(generation=3)
        assert await ctx.is_current_generation() is True
        assert ctx.session.queries == []

    async def test_true_without_generation(self):
        ctx = make_ctx(run_id=RUN)
        assert await ctx.is_current_generation() is True

    async def test_true_when_generation_and_status_match(self):
        ctx = make_ctx(run_id=RUN, generation=2)
        ctx.session.q(K_GEN, (2, "running"))
        assert await ctx.is_current_generation() is True

    async def test_false_on_generation_mismatch(self):
        ctx = make_ctx(run_id=RUN, generation=2)
        ctx.session.q(K_GEN, (3, "running"))
        assert await ctx.is_current_generation() is False

    async def test_false_on_terminal_run_status(self):
        ctx = make_ctx(run_id=RUN, generation=2)
        ctx.session.q(K_GEN, (2, "failed"))
        assert await ctx.is_current_generation() is False

    async def test_false_when_row_missing(self):
        ctx = make_ctx(run_id=RUN, generation=2)
        assert await ctx.is_current_generation() is False

    async def test_none_generation_treated_as_zero(self):
        ctx = make_ctx(run_id=RUN, generation=0)
        ctx.session.q(K_GEN, (None, "queued"))
        assert await ctx.is_current_generation() is True


class TestMarkStale:
    async def test_noop_without_run_id(self):
        ctx = make_ctx()
        await ctx.mark_stale()
        assert ctx.session.queries == []

    async def test_cancels_stage_run_command_and_run(self):
        session = FakeSession()
        stage_run = SimpleNamespace(status="processing", error_short=None)
        cmd = SimpleNamespace(status="dispatched")
        run = SimpleNamespace(status="running", finished_at=None)
        session.q(K_STAGE_RUN, stage_run)
        session.q(K_OUTBOX, cmd)
        session.q(K_RUN, run)
        ctx = make_ctx(session=session, stage_name="chunk", run_id=RUN)

        await ctx.mark_stale()

        assert stage_run.status == "cancelled"
        assert stage_run.error_short == "superseded by a newer ingest generation"
        assert cmd.status == "cancelled"
        assert run.status == "cancelled"
        assert run.finished_at is not None
        # once inside _update_stage_run, once at the end of mark_stale
        assert session.flush_calls == 2

    async def test_leaves_terminal_run_untouched(self):
        session = FakeSession()
        session.q(K_STAGE_RUN, None)
        session.q(K_OUTBOX, None)
        run = SimpleNamespace(status="completed", finished_at=None)
        session.q(K_RUN, run)
        ctx = make_ctx(session=session, stage_name="extract", run_id=RUN)

        await ctx.mark_stale()

        assert run.status == "completed"
        assert run.finished_at is None


# ── _update_stage_run ────────────────────────────────────────────────────


class TestUpdateStageRun:
    async def test_noop_without_run_id(self):
        session = FakeSession()
        ctx = make_ctx(session=session)
        await ctx._update_stage_run(status="completed")
        assert session.queries == []

    async def test_noop_when_stage_run_missing(self):
        session = FakeSession()
        session.q(K_STAGE_RUN, None)
        ctx = make_ctx(session=session, run_id=RUN)
        await ctx._update_stage_run(status="completed")
        assert session.queries == [K_STAGE_RUN]

    async def test_applies_all_fields(self):
        session = FakeSession()
        stage_run = SimpleNamespace(
            status="pending", celery_task_id=None, result_json=None,
            metrics_json=None, error_short=None, output_fingerprint=None,
            finished_at=None,
        )
        session.q(K_STAGE_RUN, stage_run)
        ctx = make_ctx(session=session, run_id=RUN)

        await ctx._update_stage_run(
            status="failed", celery_task_id="celery-7",
            result={"a": 1}, metrics={"m": 2}, error="err",
            output_fingerprint="fp",
        )

        assert stage_run.status == "failed"
        assert stage_run.finished_at is not None
        assert stage_run.celery_task_id == "celery-7"
        assert stage_run.result_json == {"a": 1}
        assert stage_run.metrics_json == {"m": 2}
        assert stage_run.error_short == "err"
        assert stage_run.output_fingerprint == "fp"
        assert session.flush_calls == 1

    async def test_none_values_leave_fields_untouched(self):
        session = FakeSession()
        stage_run = SimpleNamespace(
            status="processing", result_json={"keep": True},
            finished_at=None,
        )
        session.q(K_STAGE_RUN, stage_run)
        ctx = make_ctx(session=session, run_id=RUN)

        await ctx._update_stage_run()

        assert stage_run.status == "processing"
        assert stage_run.result_json == {"keep": True}


# ── record_result ────────────────────────────────────────────────────────


class TestRecordResult:
    async def test_noop_without_run_id(self):
        session = FakeSession()
        ctx = make_ctx(session=session)
        assert await ctx.record_result({"x": 1}) == []
        assert session.queries == []

    async def test_extract_enqueues_normalize_and_completes_run(self):
        session = FakeSession()
        stage_run = SimpleNamespace(result_json=None, output_fingerprint=None)
        own_cmd = SimpleNamespace(status="dispatched")
        run = SimpleNamespace(status="running", finished_at=None, target_models=["m1"])
        session.q(K_STAGE_RUN, stage_run)
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, None, own_cmd)
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="extract", run_id=RUN)

        result = {"chunks": [], "ok": True}
        command_ids = await ctx.record_result(result)

        assert len(command_ids) == 1
        created = session.added[0]
        assert created.stage_key == "normalize"
        assert created.status == "pending"
        assert created.payload == result
        assert command_ids == [str(created.id)]
        expected_fp = hashlib.sha256(
            json.dumps(result, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        assert stage_run.result_json == result
        assert stage_run.output_fingerprint == expected_fp
        assert own_cmd.status == "completed"
        assert run.status == "completed"
        assert run.finished_at is not None

    async def test_chunk_enqueues_one_embed_per_target_model(self):
        session = FakeSession()
        stage_run = SimpleNamespace()
        run = SimpleNamespace(status="running", finished_at=None,
                              target_models=["m1", "m2"])
        session.q(K_STAGE_RUN, stage_run)
        session.q(K_RUN, run, run)
        own_cmd = SimpleNamespace(status="running")
        session.q(K_OUTBOX, None, None, own_cmd)  # two lookups miss, then own command
        session.q(K_STATES, ["processing"])  # run stays running
        ctx = make_ctx(session=session, stage_name="chunk", run_id=RUN)

        command_ids = await ctx.record_result({"n": 2})

        assert [c.stage_key for c in session.added] == ["embed.m1", "embed.m2"]
        assert len(command_ids) == 2
        assert own_cmd.status == "completed"
        # not all stage runs terminal -> run untouched
        assert run.status == "running"
        assert run.finished_at is None

    async def test_embed_enqueues_matching_index(self):
        session = FakeSession()
        run = SimpleNamespace(status="running", finished_at=None, target_models=[])
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, None, SimpleNamespace(status="running"))
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="embed.m1", run_id=RUN)

        command_ids = await ctx.record_result({"model": "m1"})

        assert [c.stage_key for c in session.added] == ["index.m1"]
        assert len(command_ids) == 1
        assert run.status == "completed"

    async def test_index_stage_has_no_next_commands(self):
        session = FakeSession()
        run = SimpleNamespace(status="running", finished_at=None)
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, SimpleNamespace(status="running"))
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="index.m1", run_id=RUN)

        assert await ctx.record_result({"points": 3}) == []
        assert session.added == []
        assert run.status == "completed"

    async def test_existing_command_reused_not_duplicated(self):
        session = FakeSession()
        run = SimpleNamespace(status="running", finished_at=None)
        existing = SimpleNamespace(
            id=uuid.uuid4(), stage_key="normalize", status="cancelled",
            payload=None,
        )
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, existing, SimpleNamespace(status="running"))
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="extract", run_id=RUN)

        command_ids = await ctx.record_result({"ok": True})

        assert command_ids == [str(existing.id)]
        assert session.added == []

    async def test_missing_run_returns_empty_commands(self):
        session = FakeSession()
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, None)
        ctx = make_ctx(session=session, stage_name="extract", run_id=RUN)

        assert await ctx.record_result({"ok": True}) == []

    async def test_normalize_enqueues_long_memory_operation(self, monkeypatch):
        captured = {}
        operation_id = uuid.uuid4()

        class FakeLMD:
            def __init__(self, session):
                captured["session"] = session

            async def enqueue(self, source_id, action, automatic=False, ingest_run_id=None):
                captured["call"] = (source_id, action, automatic, ingest_run_id)
                return SimpleNamespace(id=operation_id)

        monkeypatch.setattr(
            "app.services.long_memory_document_service.LongMemoryDocumentService", FakeLMD)
        session = FakeSession()
        run = SimpleNamespace(status="running", finished_at=None)
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, None, SimpleNamespace(status="running"))
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="normalize", run_id=RUN)

        command_ids = await ctx.record_result({"pages": 1})

        assert captured["session"] is session
        assert captured["call"] == (SOURCE, "add", True, str(RUN))
        assert [c.stage_key for c in session.added] == ["chunk"]
        # operation id recorded for post-commit dispatch
        assert ctx.long_memory_operation_ids == [str(operation_id)]

    async def test_normalize_without_operation_records_nothing(self, monkeypatch):
        class FakeLMD:
            def __init__(self, session):
                pass

            async def enqueue(self, *args, **kwargs):
                return None

        monkeypatch.setattr(
            "app.services.long_memory_document_service.LongMemoryDocumentService", FakeLMD)
        session = FakeSession()
        run = SimpleNamespace(status="running", finished_at=None)
        session.q(K_STAGE_RUN, SimpleNamespace())
        session.q(K_RUN, run, run)
        session.q(K_OUTBOX, None, SimpleNamespace(status="running"))
        session.q(K_STATES, ["completed"])
        ctx = make_ctx(session=session, stage_name="normalize", run_id=RUN)

        await ctx.record_result({"pages": 1})

        assert ctx.long_memory_operation_ids == []


# ── completed_result ─────────────────────────────────────────────────────


class TestCompletedResult:
    async def test_none_without_run_id(self):
        ctx = make_ctx()
        assert await ctx.completed_result() is None

    async def test_returns_copy_of_completed_result(self):
        ctx = make_ctx(run_id=RUN)
        row = SimpleNamespace(status="completed", result_json={"a": 1})
        ctx.session.q(K_STAGE_RUN, row)

        out = await ctx.completed_result()

        assert out == {"a": 1}
        assert out is not row.result_json

    async def test_none_for_not_completed_row(self):
        ctx = make_ctx(run_id=RUN)
        ctx.session.q(K_STAGE_RUN, SimpleNamespace(status="processing", result_json={"a": 1}))
        assert await ctx.completed_result() is None

    async def test_none_for_non_dict_result(self):
        ctx = make_ctx(run_id=RUN)
        ctx.session.q(K_STAGE_RUN, SimpleNamespace(status="completed", result_json="oops"))
        assert await ctx.completed_result() is None

    async def test_none_for_missing_row(self):
        ctx = make_ctx(run_id=RUN)
        assert await ctx.completed_result() is None


# ── idempotency ──────────────────────────────────────────────────────────


class TestIdempotency:
    def test_idem_key_plain_stage(self):
        ctx = make_ctx(stage_name="extract")
        assert ctx._idem_key() == f"{TENANT}:{SOURCE}:extract"

    def test_idem_key_strips_model_suffix(self):
        ctx = make_ctx(stage_name="embed.m1")
        assert ctx._idem_key(model_alias="m1") == f"{TENANT}:{SOURCE}:embed:m1"
        ctx2 = make_ctx(stage_name="index.m2")
        assert ctx2._idem_key(model_alias="m2") == f"{TENANT}:{SOURCE}:index:m2"

    async def test_check_returns_none_when_cache_empty(self):
        ctx = make_ctx(stage_name="extract")
        assert await ctx.check_idempotency() is None

    async def test_check_returns_none_on_invalid_json(self):
        ctx = make_ctx(stage_name="extract")
        ctx.redis.store[f"{TENANT}:{SOURCE}:extract"] = "{not-json"
        assert await ctx.check_idempotency() is None

    async def test_check_returns_cached_without_s3_field(self):
        ctx = make_ctx(stage_name="extract")
        ctx.redis.store[f"{TENANT}:{SOURCE}:extract"] = json.dumps({"done": True})
        assert await ctx.check_idempotency() == {"done": True}

    async def test_check_validates_s3_artifact_exists(self, monkeypatch):
        ctx = make_ctx(stage_name="extract")
        key = f"{TENANT}:{SOURCE}:extract"
        ctx.redis.store[key] = json.dumps({"extracted_key": "rag/old.jsonl"})
        exists = AsyncMock(return_value=False)
        monkeypatch.setattr(sc.s3_manager, "object_exists", exists)

        assert await ctx.check_idempotency(s3_key_field="extracted_key") is None
        exists.assert_awaited_once_with("rag-bucket", "rag/old.jsonl")

    async def test_check_returns_cached_when_s3_artifact_exists(self, monkeypatch):
        ctx = make_ctx(stage_name="extract")
        ctx.redis.store[f"{TENANT}:{SOURCE}:extract"] = json.dumps({"extracted_key": "rag/x.jsonl"})
        monkeypatch.setattr(sc.s3_manager, "object_exists", AsyncMock(return_value=True))

        assert await ctx.check_idempotency(s3_key_field="extracted_key") == {
            "extracted_key": "rag/x.jsonl"}

    async def test_check_skips_s3_validation_when_field_missing(self, monkeypatch):
        ctx = make_ctx(stage_name="extract")
        ctx.redis.store[f"{TENANT}:{SOURCE}:extract"] = json.dumps({"other": 1})
        exists = AsyncMock()
        monkeypatch.setattr(sc.s3_manager, "object_exists", exists)

        assert await ctx.check_idempotency(s3_key_field="extracted_key") == {"other": 1}
        exists.assert_not_awaited()

    async def test_save_appends_pending_entry(self):
        ctx = make_ctx(stage_name="embed.m1")
        await ctx.save_idempotency({"k": "v"}, model_alias="m1", ttl=120)
        assert ctx.pending_idempotency == [
            (f"{TENANT}:{SOURCE}:embed:m1", {"k": "v"}, 120),
        ]

    async def test_save_default_ttl(self):
        ctx = make_ctx(stage_name="chunk")
        await ctx.save_idempotency({"k": "v"})
        assert ctx.pending_idempotency[0][2] == 86400


# ── S3 shortcuts ─────────────────────────────────────────────────────────


class TestS3Shortcuts:
    async def test_s3_get_uses_rag_bucket(self, monkeypatch):
        ctx = make_ctx()
        get_object = AsyncMock(return_value=b"bytes")
        monkeypatch.setattr(sc.s3_manager, "get_object", get_object)

        assert await ctx.s3_get("rag/a.jsonl") == b"bytes"
        get_object.assert_awaited_once_with(bucket="rag-bucket", key="rag/a.jsonl")

    async def test_s3_put_uploads_content(self, monkeypatch):
        ctx = make_ctx()
        upload = AsyncMock(return_value=True)
        monkeypatch.setattr(sc.s3_manager, "upload_content_sync", upload)

        await ctx.s3_put("rag/out.jsonl", b"data", content_type="application/json")

        upload.assert_awaited_once_with(
            bucket="rag-bucket", key="rag/out.jsonl",
            content=b"data", content_type="application/json",
        )

    async def test_s3_put_raises_on_failed_upload(self, monkeypatch):
        ctx = make_ctx()
        monkeypatch.setattr(sc.s3_manager, "upload_content_sync",
                            AsyncMock(return_value=False))

        with pytest.raises(IOError, match="Failed to write RAG artifact"):
            await ctx.s3_put("rag/out.jsonl", b"data")


# ── _build_stage_context ─────────────────────────────────────────────────


def _patch_build_dependencies(monkeypatch, redis_client, session):
    monkeypatch.setattr(sc, "get_settings",
                        lambda: SimpleNamespace(REDIS_URL="redis://fake", S3_BUCKET_RAG="rag-bucket"))
    monkeypatch.setattr(sc.aioredis, "from_url", lambda *a, **k: redis_client)

    @asynccontextmanager
    async def fake_session():
        yield session

    monkeypatch.setattr(sc, "get_worker_session", fake_session)

    created = {}

    factory = Mock(side_effect=lambda sess, tid: ("factory", sess, tid))
    publisher = Mock(side_effect=lambda client: ("publisher", client))
    manager = Mock(side_effect=lambda sess, fac, pub: ("manager", sess, fac, pub))
    monkeypatch.setattr(sc, "AsyncRepositoryFactory", factory)
    monkeypatch.setattr(sc, "RAGEventPublisher", publisher)
    monkeypatch.setattr(sc, "RAGStatusManager", manager)
    return factory, publisher, manager


class TestBuildContext:
    async def test_wires_all_dependencies(self, monkeypatch):
        session = FakeSession()
        redis_client = SimpleNamespace(
            close=AsyncMock(),
            connection_pool=SimpleNamespace(disconnect=AsyncMock()),
        )
        factory, publisher, manager = _patch_build_dependencies(
            monkeypatch, redis_client, session)

        async with sc._build_stage_context(
            stage_name="extract", source_id=str(SOURCE), tenant_id=str(TENANT),
            celery_task_id="celery-1", run_id=str(RUN), generation=4,
        ) as ctx:
            assert ctx.source_id == SOURCE
            assert ctx.tenant_id == TENANT
            assert ctx.stage_name == "extract"
            assert ctx.session is session
            assert ctx.redis is redis_client
            assert ctx.celery_task_id == "celery-1"
            assert ctx.run_id == RUN
            assert ctx.generation == 4
            assert ctx.repo_factory == ("factory", session, TENANT)
            assert ctx.event_publisher == ("publisher", redis_client)
            assert ctx.status_manager == (
                "manager", session, ("factory", session, TENANT), ("publisher", redis_client))
            factory.assert_called_once_with(session, TENANT)
            redis_client.close.assert_not_awaited()

        redis_client.close.assert_awaited_once()
        redis_client.connection_pool.disconnect.assert_awaited_once()

    async def test_redis_close_failure_swallowed(self, monkeypatch):
        session = FakeSession()
        redis_client = SimpleNamespace(
            close=AsyncMock(side_effect=RuntimeError("close boom")),
            connection_pool=SimpleNamespace(disconnect=AsyncMock()),
        )
        _patch_build_dependencies(monkeypatch, redis_client, session)

        async with sc._build_stage_context(
            stage_name="extract", source_id=str(SOURCE), tenant_id=str(TENANT),
        ) as ctx:
            assert ctx.session is session

        redis_client.connection_pool.disconnect.assert_not_awaited()


# ── run_stage ────────────────────────────────────────────────────────────


def make_run_ctx(**overrides):
    ctx = SimpleNamespace(
        source_id=SOURCE,
        tenant_id=TENANT,
        stage_name="extract",
        session=FakeSession(),
        redis=FakeRedis(),
        completed_result=AsyncMock(return_value=None),
        is_current_generation=AsyncMock(return_value=True),
        record_result=AsyncMock(return_value=[]),
        mark_stale=AsyncMock(),
        set_failed=AsyncMock(),
        pending_idempotency=[],
        long_memory_operation_ids=[],
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def patch_stage_context_builder(monkeypatch, ctx):
    captured = {}

    @asynccontextmanager
    async def fake_build(**kwargs):
        captured["kwargs"] = kwargs
        yield ctx

    monkeypatch.setattr(sc, "_build_stage_context", fake_build)
    return captured


def make_celery_task(task_id="celery-9"):
    return SimpleNamespace(request=SimpleNamespace(id=task_id))


class TestRunStage:
    def test_happy_path_persists_and_dispatches(self, monkeypatch):
        ctx = make_run_ctx(
            record_result=AsyncMock(return_value=["cmd-1"]),
            pending_idempotency=[("idem-key", {"v": 1}, 30)],
            long_memory_operation_ids=["op-1"],
        )
        captured = patch_stage_context_builder(monkeypatch, ctx)
        dispatch_task = Mock()
        lmd_task = Mock()
        monkeypatch.setattr(
            "app.workers.tasks_rag_ingest.dispatch.dispatch_rag_ingest_stage_outbox",
            dispatch_task)
        monkeypatch.setattr(
            "app.workers.tasks_long_memory_documents.execute_long_memory_document",
            lmd_task)
        data = {"ok": True}
        execute_fn = AsyncMock(return_value=SimpleNamespace(to_dict=lambda: data))

        result = sc.run_stage(
            stage_name="extract", source_id=str(SOURCE), tenant_id=str(TENANT),
            celery_task=make_celery_task(), execute_fn=execute_fn,
            run_id=str(RUN), generation=2,
        )

        assert result == data
        assert captured["kwargs"]["celery_task_id"] == "celery-9"
        assert captured["kwargs"]["run_id"] == str(RUN)
        assert captured["kwargs"]["generation"] == 2
        assert captured["kwargs"]["stage_name"] == "extract"
        assert ctx.record_result.await_args.args == (data,)
        assert ctx.session.commit_calls == 1
        assert ctx.redis.setex_calls == [("idem-key", 30, json.dumps({"v": 1}))]
        dispatch_task.delay.assert_called_once_with("cmd-1")
        lmd_task.delay.assert_called_once_with("op-1")

    def test_plain_dict_result_returned_as_is(self, monkeypatch):
        ctx = make_run_ctx()
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock(return_value={"raw": 1})

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert result == {"raw": 1}
        ctx.record_result.assert_awaited_once_with({"raw": 1})

    def test_completed_result_short_circuits(self, monkeypatch):
        ctx = make_run_ctx(completed_result=AsyncMock(return_value={"cached": 1}))
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock()

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert result == {"cached": 1}
        execute_fn.assert_not_awaited()
        ctx.record_result.assert_not_awaited()
        assert ctx.session.commit_calls == 0

    def test_stale_before_execution_marks_stale(self, monkeypatch):
        ctx = make_run_ctx(is_current_generation=AsyncMock(return_value=False))
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock()

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn,
            run_id=str(RUN), generation=1,
        )

        assert result == {"source_id": str(SOURCE), "stale": True}
        execute_fn.assert_not_awaited()
        ctx.mark_stale.assert_awaited_once()
        assert ctx.session.commit_calls == 1
        ctx.record_result.assert_not_awaited()

    def test_stale_after_execution_rolls_back(self, monkeypatch):
        ctx = make_run_ctx(
            is_current_generation=AsyncMock(side_effect=[True, False]))
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock(return_value={"ok": 1})

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert result == {"source_id": str(SOURCE), "stale": True}
        assert ctx.session.rollback_calls == 1
        ctx.mark_stale.assert_awaited_once()
        assert ctx.session.commit_calls == 1
        ctx.record_result.assert_not_awaited()

    def test_execution_failure_persists_failed_and_reraises(self, monkeypatch):
        ctx = make_run_ctx()
        patch_stage_context_builder(monkeypatch, ctx)
        boom = ValueError("boom")
        execute_fn = AsyncMock(side_effect=boom)

        with pytest.raises(ValueError, match="boom"):
            sc.run_stage(
                "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert ctx.session.rollback_calls == 1
        ctx.set_failed.assert_awaited_once_with("ValueError: boom")
        assert ctx.session.commit_calls == 1

    def test_error_with_stale_generation_returns_stale(self, monkeypatch):
        ctx = make_run_ctx(
            is_current_generation=AsyncMock(side_effect=[True, False]))
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock(side_effect=RuntimeError("explode"))

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn,
            run_id=str(RUN), generation=1,
        )

        assert result == {"source_id": str(SOURCE), "stale": True}
        ctx.mark_stale.assert_awaited_once()
        ctx.set_failed.assert_not_awaited()

    def test_set_failed_failure_invokes_custom_error_notify(self, monkeypatch):
        ctx = make_run_ctx(set_failed=AsyncMock(side_effect=RuntimeError("status boom")))
        patch_stage_context_builder(monkeypatch, ctx)
        notify = AsyncMock()
        boom = ValueError("boom")
        execute_fn = AsyncMock(side_effect=boom)

        with pytest.raises(ValueError, match="boom"):
            sc.run_stage(
                "extract", str(SOURCE), str(TENANT), make_celery_task(),
                execute_fn, error_notify_fn=notify,
            )

        notify.assert_awaited_once_with(str(SOURCE), str(TENANT), "extract", boom)

    def test_set_failed_failure_falls_back_to_notify_stage_error(self, monkeypatch):
        ctx = make_run_ctx(set_failed=AsyncMock(side_effect=RuntimeError("status boom")))
        patch_stage_context_builder(monkeypatch, ctx)
        notify = AsyncMock()
        monkeypatch.setattr(sc, "notify_stage_error", notify)
        boom = ValueError("boom")
        execute_fn = AsyncMock(side_effect=boom)

        with pytest.raises(ValueError, match="boom"):
            sc.run_stage(
                "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        notify.assert_awaited_once_with(str(SOURCE), str(TENANT), "extract", boom)

    def test_failing_error_notify_does_not_mask_original(self, monkeypatch):
        ctx = make_run_ctx(set_failed=AsyncMock(side_effect=RuntimeError("status boom")))
        patch_stage_context_builder(monkeypatch, ctx)
        notify = AsyncMock(side_effect=RuntimeError("notify boom"))
        execute_fn = AsyncMock(side_effect=ValueError("boom"))

        with pytest.raises(ValueError, match="boom"):
            sc.run_stage(
                "extract", str(SOURCE), str(TENANT), make_celery_task(),
                execute_fn, error_notify_fn=notify,
            )

    def test_broker_dispatch_failure_is_non_fatal(self, monkeypatch):
        ctx = make_run_ctx(
            record_result=AsyncMock(return_value=["cmd-1"]),
            long_memory_operation_ids=["op-1"],
        )
        patch_stage_context_builder(monkeypatch, ctx)
        dispatch_task = Mock()
        dispatch_task.delay = Mock(side_effect=RuntimeError("broker down"))
        lmd_task = Mock()
        lmd_task.delay = Mock(side_effect=RuntimeError("broker down"))
        monkeypatch.setattr(
            "app.workers.tasks_rag_ingest.dispatch.dispatch_rag_ingest_stage_outbox",
            dispatch_task)
        monkeypatch.setattr(
            "app.workers.tasks_long_memory_documents.execute_long_memory_document",
            lmd_task)
        execute_fn = AsyncMock(return_value={"ok": True})

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert result == {"ok": True}
        dispatch_task.delay.assert_called_once_with("cmd-1")
        lmd_task.delay.assert_called_once_with("op-1")

    def test_idempotency_cache_failure_is_non_fatal(self, monkeypatch):
        ctx = make_run_ctx(pending_idempotency=[("idem-key", {"v": 1}, 30)])
        ctx.redis.setex = AsyncMock(side_effect=RuntimeError("redis down"))
        patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock(return_value={"ok": True})

        result = sc.run_stage(
            "extract", str(SOURCE), str(TENANT), make_celery_task(), execute_fn)

        assert result == {"ok": True}
        ctx.redis.setex.assert_awaited_once()

    def test_celery_task_without_id_passes_none(self, monkeypatch):
        ctx = make_run_ctx()
        captured = patch_stage_context_builder(monkeypatch, ctx)
        execute_fn = AsyncMock(return_value={"ok": 1})

        sc.run_stage(
            "extract", str(SOURCE), str(TENANT),
            SimpleNamespace(request=SimpleNamespace()), execute_fn,
        )

        assert captured["kwargs"]["celery_task_id"] is None
