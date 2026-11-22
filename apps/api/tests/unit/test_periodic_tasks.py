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


def test_expired_chat_attachment_cleanup_is_scheduled_hourly_on_cleanup_queue():
    schedule = build_default_beat_schedule()
    spec = schedule["expired-chat-attachments-cleanup"]

    assert spec["task"] == "app.workers.tasks_cleanup.cleanup_expired_chat_attachments"
    assert spec["schedule"] == 3600.0
    route = celery_app.amqp.router.route({}, spec["task"])
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


def test_periodic_schedule_has_operator_metadata_and_tracking_headers():
    from app.services.periodic_task_catalog import PERIODIC_TASK_PRESENTATION

    schedule = build_default_beat_schedule()
    assert set(schedule) == set(PERIODIC_TASK_PRESENTATION)
    for slug, entry in schedule.items():
        name, description = PERIODIC_TASK_PRESENTATION[slug]
        assert name and description and name != slug
        assert entry["options"]["headers"]["periodic_slug"] == slug


def test_periodic_dispatch_is_gated_by_celery_before_start(monkeypatch):
    import logging
    from datetime import datetime, timezone

    from app.workers import periodic_task_tracker as tracker

    start = AsyncMock(side_effect=[(None, False), (datetime.now(timezone.utc), True)])
    finish = AsyncMock()
    monkeypatch.setattr(tracker, "_start", start)
    monkeypatch.setattr(tracker, "_finish", finish)

    task_logger = logging.getLogger("app.tests.periodic_task")
    handler = tracker.PeriodicRunLogHandler()
    task_logger.addHandler(handler)

    @celery_app.task(name="test.periodic.tracker")
    def check_task():
        task_logger.warning("checked connector token=secret-value")
        return {"checked": 1}

    try:
        headers = {"periodic_slug": "tracked"}
        check_task.apply(headers=headers)
        finish.assert_not_awaited()
        outcome = check_task.apply(headers={**headers, "periodic_manual": "1"})
        assert outcome.get() == {"checked": 1}
        run, status, retval = finish.await_args.args
        assert status == "success" and retval == {"checked": 1}
        assert run.slug == "tracked"
        assert [event["message"] for event in run.events] == ["checked connector token=***"]
        assert [call.kwargs["manual"] for call in start.await_args_list] == [False, True]
        check_task.apply()
        assert start.await_count == 2
        assert finish.await_count == 1
    finally:
        task_logger.removeHandler(handler)
        celery_app.tasks.unregister("test.periodic.tracker")


def test_run_result_redacts_secrets_and_limits_oversize_payloads():
    from app.services.periodic_task_service import MAX_RESULT_BYTES, safe_run_result

    assert safe_run_result({"token": "secret-value", "checked": 3}) == ({"token": "***", "checked": 3}, False)
    assert safe_run_result("x" * MAX_RESULT_BYTES) == (None, True)
    assert safe_run_result(None) == (None, False)


def test_tool_payload_cleanup_disposes_engine_in_its_creation_loop(monkeypatch):
    import asyncio

    from app.services import tool_result_store
    from app.workers import tasks_cleanup

    loops = []
    disposed = []

    def create_engine():
        owner = asyncio.get_running_loop()
        loops.append(owner)

        @asynccontextmanager
        async def begin():
            assert asyncio.get_running_loop() is owner
            yield SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=3)))

        async def dispose():
            assert asyncio.get_running_loop() is owner
            disposed.append(owner)

        return SimpleNamespace(begin=begin, dispose=dispose)

    monkeypatch.setattr(tool_result_store, "create_tool_results_engine", create_engine)
    assert tasks_cleanup.cleanup_expired_tool_payloads.run() == 3
    assert tasks_cleanup.cleanup_expired_tool_payloads.run() == 3
    assert disposed == loops and len(set(loops)) == 2


def test_discovery_counts_reported_provider_failure(monkeypatch):
    from app.workers import tasks_health

    instance = SimpleNamespace(id="provider-id", slug="mcp_sql")
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [instance]))
    session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())

    @asynccontextmanager
    async def session_scope():
        yield session

    service = SimpleNamespace(rescan=AsyncMock(return_value={
        "mcp_upserted": 0,
        "mcp_failed_providers": [{"provider_slug": "mcp_sql", "error": "Name or service not known"}],
    }))
    monkeypatch.setattr(tasks_health, "get_worker_session", session_scope)
    monkeypatch.setattr(tasks_health, "acquire_advisory_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(tasks_health, "release_advisory_lock", AsyncMock())
    monkeypatch.setattr(tasks_health, "ToolDiscoveryService", lambda _session: service)

    summary = tasks_health.rescan_discovery.run()
    assert summary["providers_scanned"] == 1
    assert summary["successful_scans"] == 0
    assert summary["failed_scans"] == 1
    assert summary["details"][0]["success"] is False
