from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from celery import signals
from celery.exceptions import Ignore
from sqlalchemy import select

from app.models.periodic_task import PeriodicTask
from app.workers.session_factory import get_worker_session


_TASK_TIMES: dict[str, float] = {}


async def _get_by_task_path(task_path: str) -> PeriodicTask | None:
    async with get_worker_session() as session:
        row = (
            await session.execute(select(PeriodicTask).where(PeriodicTask.task_path == task_path))
        ).scalar_one_or_none()
        return row


async def _update_start(task_path: str) -> bool:
    async with get_worker_session() as session:
        row = (
            await session.execute(select(PeriodicTask).where(PeriodicTask.task_path == task_path))
        ).scalar_one_or_none()
        if row is None:
            return True
        if not row.is_enabled:
            row.last_run_at = datetime.now(timezone.utc)
            row.last_status = "skipped"
            await session.flush()
            await session.commit()
            return False
        row.last_run_at = datetime.now(timezone.utc)
        row.last_status = "running"
        row.last_error = None
        await session.flush()
        await session.commit()
        return True


async def _update_success(task_path: str, duration_ms: int | None) -> None:
    async with get_worker_session() as session:
        row = (
            await session.execute(select(PeriodicTask).where(PeriodicTask.task_path == task_path))
        ).scalar_one_or_none()
        if row is None:
            return
        row.last_status = "success"
        row.last_duration_ms = duration_ms
        row.last_error = None
        row.last_run_at = datetime.now(timezone.utc)
        await session.flush()
        await session.commit()


async def _update_failure(task_path: str, error_text: str, duration_ms: int | None) -> None:
    async with get_worker_session() as session:
        row = (
            await session.execute(select(PeriodicTask).where(PeriodicTask.task_path == task_path))
        ).scalar_one_or_none()
        if row is None:
            return
        row.last_status = "failure"
        row.last_duration_ms = duration_ms
        row.last_error = error_text[:2000]
        row.last_run_at = datetime.now(timezone.utc)
        await session.flush()
        await session.commit()


@signals.task_prerun.connect
def periodic_task_prerun(task_id=None, task=None, **kwargs):
    if task is None:
        return
    task_path = str(getattr(task, "name", "") or "").strip()
    if not task_path:
        return
    _TASK_TIMES[task_id] = time.monotonic()
    req = getattr(task, "request", None)
    headers = getattr(req, "headers", {}) or {}
    is_manual = str(headers.get("periodic_manual", "")).strip() == "1"
    if is_manual:
        return

    allowed = asyncio.run(_update_start(task_path))
    if not allowed:
        raise Ignore()


@signals.task_postrun.connect
def periodic_task_postrun(task_id=None, task=None, state=None, **kwargs):
    if task is None:
        return
    task_path = str(getattr(task, "name", "") or "").strip()
    if not task_path:
        return
    started = _TASK_TIMES.pop(task_id, None)
    duration_ms = int((time.monotonic() - started) * 1000) if started else None
    if str(state).upper() == "SUCCESS":
        asyncio.run(_update_success(task_path, duration_ms))


@signals.task_failure.connect
def periodic_task_failure(task_id=None, exception=None, traceback=None, sender=None, **kwargs):
    task_path = str(getattr(sender, "name", "") or "").strip()
    if not task_path:
        return
    started = _TASK_TIMES.pop(task_id, None)
    duration_ms = int((time.monotonic() - started) * 1000) if started else None
    error_text = str(exception or "Task failed")
    asyncio.run(_update_failure(task_path, error_text, duration_ms))
