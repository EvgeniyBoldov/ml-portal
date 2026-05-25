from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from celery.schedules import crontab
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import get_effective_beat_schedule
from app.models.periodic_task import PeriodicTask


@dataclass
class BeatTaskDef:
    slug: str
    task_path: str
    schedule: Dict[str, Any]


def _schedule_to_dict(schedule: Any) -> Dict[str, Any]:
    if hasattr(schedule, "run_every"):
        seconds = int(getattr(schedule.run_every, "total_seconds", lambda: 0)())
        return {"type": "interval", "seconds": seconds}
    if isinstance(schedule, crontab):
        return {
            "type": "crontab",
            "minute": str(schedule._orig_minute),
            "hour": str(schedule._orig_hour),
            "day_of_week": str(schedule._orig_day_of_week),
            "day_of_month": str(schedule._orig_day_of_month),
            "month_of_year": str(schedule._orig_month_of_year),
        }
    if isinstance(schedule, (int, float)):
        return {"type": "interval", "seconds": int(schedule)}
    return {"type": "unknown", "raw": str(schedule)}


def _category_for_slug(slug: str) -> str:
    s = slug.lower()
    if "health" in s:
        return "health"
    if "cleanup" in s:
        return "cleanup"
    if "reconcile" in s:
        return "reconcile"
    if "sync" in s:
        return "sync"
    return "other"


def get_beat_schedule_defs() -> list[BeatTaskDef]:
    schedule = get_effective_beat_schedule()
    defs: list[BeatTaskDef] = []
    for slug, spec in schedule.items():
        task_path = str((spec or {}).get("task") or "").strip()
        if not task_path:
            continue
        defs.append(
            BeatTaskDef(
                slug=str(slug),
                task_path=task_path,
                schedule=_schedule_to_dict((spec or {}).get("schedule")),
            )
        )
    return defs


class PeriodicTaskSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync_from_beat(self) -> None:
        defs = get_beat_schedule_defs()
        slugs = {d.slug for d in defs}

        existing_rows = (await self.session.execute(select(PeriodicTask))).scalars().all()
        by_slug = {row.slug: row for row in existing_rows}

        for item in defs:
            row = by_slug.get(item.slug)
            if row is None:
                row = PeriodicTask(
                    slug=item.slug,
                    task_path=item.task_path,
                    name=item.slug.replace("-", " ").title(),
                    category=_category_for_slug(item.slug),
                    default_schedule=item.schedule,
                    is_enabled=True,
                    is_orphaned=False,
                )
                self.session.add(row)
                continue
            row.task_path = item.task_path
            row.category = _category_for_slug(item.slug)
            row.default_schedule = item.schedule
            row.is_orphaned = False

        for row in existing_rows:
            if row.slug not in slugs:
                row.is_orphaned = True

        await self.session.flush()
