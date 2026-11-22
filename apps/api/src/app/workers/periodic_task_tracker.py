from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from celery import Task, signals
from celery.exceptions import Ignore

from app.services.periodic_task_service import PeriodicTaskService, run_event, safe_run_text
from app.workers.session_factory import get_worker_session


@dataclass
class ActiveRun:
    slug: str
    task_id: str
    started_at: datetime
    started: float
    events: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=36))


_active_run: ContextVar[ActiveRun | None] = ContextVar("periodic_active_run", default=None)


class PeriodicRunLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        run = _active_run.get()
        if run is not None and record.name.startswith("app.") and record.levelno >= logging.INFO:
            try:
                run.events.append(run_event(safe_run_text(record.getMessage(), 500), level=record.levelname))
            except Exception:
                self.handleError(record)


@signals.after_setup_logger.connect
def _setup_periodic_log_capture(logger: logging.Logger, **_kwargs: Any) -> None:
    if not any(isinstance(handler, PeriodicRunLogHandler) for handler in logger.handlers):
        logger.addHandler(PeriodicRunLogHandler())


async def _start(slug: str, task_path: str, task_id: str, *, manual: bool) -> tuple[datetime | None, bool]:
    async with get_worker_session() as session, session.begin():
        return await PeriodicTaskService(session).start_run(slug, task_path, task_id, manual=manual)


async def _finish(run: ActiveRun, status: str, retval: Any) -> None:
    duration_ms = round((time.monotonic() - run.started) * 1000)
    async with get_worker_session() as session, session.begin():
        await PeriodicTaskService(session).finish_run(
            run.slug, run.task_id, run.started_at, status, duration_ms, retval, list(run.events),
        )


class PeriodicTrackedTask(Task):
    def before_start(self, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        headers = self.request.headers or {}
        slug = headers.get("periodic_slug")
        if not isinstance(slug, str) or not slug:
            return
        started_at, execute = asyncio.run(
            _start(slug, self.name, task_id, manual=headers.get("periodic_manual") == "1")
        )
        if not execute:
            raise Ignore()
        if started_at is not None:
            _active_run.set(ActiveRun(slug, task_id, started_at, time.monotonic()))


@signals.task_postrun.connect
def periodic_task_postrun(task_id: str, state: str | None, retval: Any, **_kwargs: Any) -> None:
    run = _active_run.get()
    if run is None or run.task_id != task_id:
        return
    _active_run.set(None)
    status = {
        "SUCCESS": "success", "FAILURE": "failure", "RETRY": "retry",
        "IGNORED": "skipped", "REJECTED": "failure",
    }.get(state)
    if status:
        asyncio.run(_finish(run, status, retval))
