from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.models.periodic_task import PeriodicTask
from app.services.periodic_task_service import RECENT_RUNS, PeriodicTaskService
from app.workers.session_factory import get_worker_session


pytestmark = pytest.mark.skipif(
    os.getenv("PERIODIC_TASKS_PG") != "1",
    reason="requires migrated local PostgreSQL",
)


@pytest.mark.asyncio
async def test_periodic_run_history_and_latest_projection():
    async with get_worker_session() as session:
        slug = f"periodic-test-{uuid4()}"
        path = "tests.periodic.noop"
        task = PeriodicTask(slug=slug, task_path=path, name="Periodic test", is_enabled=False)
        session.add(task)
        await session.flush()

        service = PeriodicTaskService(session)
        scheduled, manual, newer = (str(uuid4()) for _ in range(3))
        assert await service.start_run(slug, path, scheduled, manual=False) == (None, False)
        assert await service.get_run(task, scheduled) is None
        manual_start, allowed = await service.start_run(slug, path, manual, manual=True)
        assert allowed and manual_start
        newer_start, allowed = await service.start_run(slug, path, newer, manual=True)
        assert allowed and newer_start
        await service.finish_run(slug, manual, manual_start, "success", 100, {"checked": 1}, [])
        await session.flush()

        run = await service.get_run(task, manual)
        assert run is not None
        assert run.result == {"checked": 1}
        assert len(run.events) == 3
        assert task.last_run_id == newer
        assert task.last_status == "running"

        await service.finish_run(slug, newer, newer_start, "retry", 24, ValueError("retry later"), [])
        await session.flush()
        assert task.last_status == "retry"
        retry_start, allowed = await service.start_run(slug, path, newer, manual=True)
        assert allowed and retry_start
        await service.finish_run(slug, newer, newer_start, "failure", 19, ValueError("outdated"), [])
        assert task.last_status == "running"
        await service.finish_run(slug, newer, retry_start, "success", 15, 0, [])
        await session.flush()
        assert task.last_status == "success"
        assert task.last_duration_ms == 15
        assert (await service.get_run(task, newer)).result == 0

        await service.set_enabled(slug, True)
        for _ in range(RECENT_RUNS):
            await service.start_run(slug, path, str(uuid4()), manual=False)
        assert len(await service.recent_runs(task)) == RECENT_RUNS
        assert await service.get_run(task, scheduled) is None
        assert await service.get_run(task, manual) is None
        await session.rollback()


def test_tool_payload_cleanup_on_postgres(monkeypatch, caplog):
    from contextlib import asynccontextmanager

    from sqlalchemy import text

    from app.services import tool_result_store
    from app.workers import tasks_cleanup

    build_engine = tool_result_store.create_tool_results_engine

    class TestEngine:
        def __init__(self):
            self.engine = build_engine()

        @asynccontextmanager
        async def begin(self):
            async with self.engine.begin() as connection:
                await connection.execute(text(
                    "CREATE TEMP TABLE runtime_tool_payloads "
                    "(id integer PRIMARY KEY, expires_at timestamptz) ON COMMIT DROP"
                ))
                await connection.execute(text(
                    "INSERT INTO pg_temp.runtime_tool_payloads VALUES "
                    "(1, now() - interval '1 day'), (2, now() + interval '1 day')"
                ))
                yield connection
                remaining = (await connection.execute(text(
                    "SELECT id FROM pg_temp.runtime_tool_payloads"
                ))).scalars().all()
                assert remaining == [2]

        async def dispose(self):
            await self.engine.dispose()

    monkeypatch.setattr(tool_result_store, "create_tool_results_engine", TestEngine)

    assert tasks_cleanup.cleanup_expired_tool_payloads.run() == 1
    assert "Exception closing connection" not in caplog.text
