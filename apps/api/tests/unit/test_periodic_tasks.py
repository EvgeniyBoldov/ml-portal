from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.celery_app import app as celery_app, build_default_beat_schedule


def test_every_periodic_task_targets_a_queue_consumed_by_workers():
    queue_names = {queue.name for queue in celery_app.conf.task_queues}

    # Generic/manual Celery sends fall back to this queue when no route matches.
    assert "celery" in queue_names

    for slug, spec in build_default_beat_schedule().items():
        task_path = spec["task"]
        explicit_queue = (spec.get("options") or {}).get("queue")
        route = celery_app.amqp.router.route({}, task_path)
        target_queue = explicit_queue or route["queue"].name

        assert target_queue in queue_names, f"{slug} targets unconsumed queue {target_queue}"


def test_retired_periodic_jobs_are_not_in_the_schedule():
    schedule = build_default_beat_schedule()

    assert {
        "memory-index-reconcile",
        "memory-freshness-refresh",
        "memory-document-contract-reextract",
        "shadow-memory-conflict-reconcile",
        "collection-vector-index-audit",
    }.isdisjoint(schedule)


def test_runtime_result_cleanup_has_a_worker_route():
    route = celery_app.amqp.router.route(
        {}, "app.workers.tasks_cleanup.cleanup_expired_runtime_tool_results"
    )

    assert route["queue"].name == "cleanup_low"


def test_chat_context_expiry_has_a_worker_route():
    route = celery_app.amqp.router.route(
        {}, "app.workers.tasks_cleanup.expire_chat_context_items"
    )

    assert route["queue"].name == "cleanup_low"


def test_cleanup_expired_runtime_tool_results_deletes_rows_and_commits(monkeypatch):
    from app.workers import tasks_cleanup

    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=3)),
        commit=AsyncMock(),
    )

    @asynccontextmanager
    async def session_scope():
        yield session

    monkeypatch.setattr(tasks_cleanup, "get_worker_session", session_scope)

    assert tasks_cleanup.cleanup_expired_runtime_tool_results.run() == 3
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_expire_chat_context_items_uses_transaction_and_reports_count(monkeypatch):
    from app.workers import tasks_cleanup

    session = object()
    repository = SimpleNamespace(expire_due_items=AsyncMock(return_value=4))
    transaction_names: list[str] = []

    @asynccontextmanager
    async def session_scope():
        yield session

    @asynccontextmanager
    async def transaction(_session, name):
        transaction_names.append(name)
        yield

    monkeypatch.setattr(tasks_cleanup, "get_worker_session", session_scope)
    monkeypatch.setattr(tasks_cleanup, "worker_transaction", transaction)
    monkeypatch.setattr(
        tasks_cleanup,
        "ChatContextRepository",
        lambda actual_session: repository if actual_session is session else None,
    )

    assert tasks_cleanup.expire_chat_context_items.run() == {"expired": 4}
    repository.expire_due_items.assert_awaited_once_with(limit=tasks_cleanup.CHAT_CONTEXT_EXPIRY_BATCH_SIZE)
    assert transaction_names == ["expire_chat_context_items"]
