from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.periodic_task import PeriodicTask, PeriodicTaskRun
from app.repositories.periodic_tasks import PeriodicTaskRepository
from app.runtime.redactor import RuntimeRedactor


RECENT_RUNS = 20
MAX_RUN_EVENTS = 48
MAX_RESULT_BYTES = 16 * 1024
TERMINAL_STATUSES = frozenset({"success", "failure", "skipped"})
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s/@]+@")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


def run_event(message: str, *, level: str = "INFO") -> dict[str, str]:
    return {"at": datetime.now(timezone.utc).isoformat(), "level": level, "message": message}


def safe_run_text(value: str, limit: int = 1000) -> str:
    text = _URL_CREDENTIALS.sub(r"\1***@", value[:limit * 4])
    text = _BEARER_TOKEN.sub("Bearer ***", text)
    return RuntimeRedactor().redact(text).replace("\x00", "")[:limit]


def safe_run_result(value: Any) -> tuple[Any, bool]:
    if value is None:
        return None, False
    try:
        encoded = json.dumps(RuntimeRedactor().redact(value), ensure_ascii=True, allow_nan=False)
        if len(encoded) <= MAX_RESULT_BYTES and r"\u0000" not in encoded:
            return json.loads(encoded), False
    except (TypeError, ValueError, RecursionError):
        pass
    return None, True


class PeriodicTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PeriodicTaskRepository(session)

    async def list_tasks(
        self, *, category: str | None = None, is_enabled: bool | None = None,
    ) -> list[PeriodicTask]:
        return await self.repo.list_tasks(category=category, is_enabled=is_enabled)

    async def get_by_slug(self, slug: str) -> PeriodicTask | None:
        return await self.repo.get_task(slug)

    async def recent_runs(self, task: PeriodicTask) -> list[PeriodicTaskRun]:
        return await self.repo.list_runs(task.id, limit=RECENT_RUNS)

    async def get_run(self, task: PeriodicTask, run_id: str) -> PeriodicTaskRun | None:
        return await self.repo.get_run(task.id, run_id)

    async def set_enabled(self, slug: str, is_enabled: bool) -> PeriodicTask | None:
        task = await self.repo.get_task(slug, lock=True)
        if task is not None:
            task.is_enabled = is_enabled
            await self.session.flush()
        return task

    async def trigger_run(self, slug: str) -> tuple[bool, str | None]:
        from app.celery_app import app as celery_app, build_default_beat_schedule

        task = await self.get_by_slug(slug)
        if task is None or task.is_orphaned:
            return False, None

        run_id = str(uuid4())
        queued_at = datetime.now(timezone.utc)
        options = (build_default_beat_schedule().get(slug, {}).get("options") or {}).copy()
        options.pop("headers", None)
        await asyncio.to_thread(
            celery_app.send_task,
            task.task_path,
            task_id=run_id,
            headers={"periodic_slug": slug, "periodic_manual": "1"},
            **options,
        )

        # The worker may start before the broker publish returns.
        locked = await self.repo.get_task(slug, lock=True)
        if locked is not None and await self.repo.get_run(locked.id, run_id) is None:
            run = PeriodicTaskRun(
                id=run_id, task_id=locked.id, source="manual", status="queued",
                created_at=queued_at, events=[run_event("Ручной запуск поставлен в очередь.")],
            )
            await self._add_run(locked, run)
        return True, run_id

    async def start_run(
        self, slug: str, task_path: str, run_id: str, *, manual: bool,
    ) -> tuple[datetime | None, bool]:
        """Return the persisted attempt start and whether the delivery may run."""
        task = await self.repo.get_task(slug, lock=True)
        if task is None:
            return None, True
        if task.task_path != task_path or (not manual and not task.is_enabled):
            return None, False

        run = await self.repo.get_run(task.id, run_id)
        if run is not None and run.status in TERMINAL_STATUSES:
            return None, False

        now = datetime.now(timezone.utc)
        allowed = not task.is_orphaned
        new_run = run is None
        if run is None:
            run = PeriodicTaskRun(
                id=run_id, task_id=task.id, source="manual" if manual else "schedule",
                created_at=now,
                events=[run_event("Воркер получил ручной запуск из очереди.")] if manual else [],
            )

        if allowed:
            run.status = "running"
            run.started_at = now
            run.finished_at = None
            run.error = None
            run.duration_ms = None
            event = run_event("Воркер начал выполнение.")
        else:
            run.status = "skipped"
            run.finished_at = now
            run.duration_ms = None
            event = run_event("Запуск пропущен. Задача снята с расписания.", level="WARNING")
        run.events = [*run.events, event][-MAX_RUN_EVENTS:]

        if new_run:
            await self._add_run(task, run)
        elif task.last_run_id == run.id:
            self._project_run(task, run)
        return (now if allowed else None), allowed

    async def finish_run(
        self, slug: str, run_id: str, started_at: datetime, status: str, duration_ms: int,
        retval: Any, events: list[dict[str, str]],
    ) -> None:
        task = await self.repo.get_task(slug, lock=True)
        if task is None:
            return
        run = await self.repo.get_run(task.id, run_id)
        if run is None or run.status != "running" or run.started_at != started_at:
            return

        run.status = status
        run.duration_ms = duration_ms
        run.finished_at = datetime.now(timezone.utc) if status in TERMINAL_STATUSES else None
        if status == "success":
            run.result, run.result_limited = safe_run_result(retval)
        elif status in {"failure", "retry"}:
            run.error = safe_run_text(str(retval), 2000)
        message, level = {
            "success": ("Выполнение завершено.", "INFO"),
            "failure": ("Выполнение завершилось ошибкой.", "ERROR"),
            "retry": ("Запланирована повторная попытка.", "WARNING"),
            "skipped": ("Выполнение пропущено воркером.", "WARNING"),
        }[status]
        run.events = [*run.events, *events, run_event(message, level=level)][-MAX_RUN_EVENTS:]
        if task.last_run_id == run.id:
            self._project_run(task, run)

    async def _add_run(self, task: PeriodicTask, run: PeriodicTaskRun) -> None:
        self.repo.add_run(run)
        if task.last_run_at is None or task.last_run_at <= run.created_at:
            self._project_run(task, run)
        await self.session.flush()
        await self.repo.prune_runs(task.id, keep=RECENT_RUNS)

    @staticmethod
    def _project_run(task: PeriodicTask, run: PeriodicTaskRun) -> None:
        task.last_run_id = run.id
        task.last_run_at = run.created_at
        task.last_status = run.status
        task.last_duration_ms = run.duration_ms
        task.last_error = run.error
