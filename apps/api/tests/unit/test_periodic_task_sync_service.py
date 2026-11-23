"""Unit tests for PeriodicTaskSyncService (app/services/periodic_task_sync_service.py)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celery.schedules import crontab
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.periodic_task import PeriodicTask
from app.services.periodic_task_sync_service import (
    BeatTaskDef,
    PeriodicTaskSyncService,
    _category_for_slug,
    _schedule_to_dict,
    get_beat_schedule_defs,
)


class IntervalSchedule:
    """Minimal celery interval schedule stand-in (has run_every)."""

    def __init__(self, seconds: int) -> None:
        self.run_every = timedelta(seconds=seconds)


class TestScheduleToDict:
    def test_interval_schedule(self):
        assert _schedule_to_dict(IntervalSchedule(90)) == {"type": "interval", "seconds": 90}

    def test_plain_number(self):
        assert _schedule_to_dict(60) == {"type": "interval", "seconds": 60}
        assert _schedule_to_dict(1.5) == {"type": "interval", "seconds": 1}

    def test_crontab_schedule(self):
        schedule = crontab(minute=0, hour=4, day_of_week="*", day_of_month="1", month_of_year="*")

        result = _schedule_to_dict(schedule)

        assert result["type"] == "crontab"
        assert result["minute"] == "0"
        assert result["hour"] == "4"
        assert result["day_of_month"] == "1"

    def test_unknown_schedule(self):
        result = _schedule_to_dict("every full moon")

        assert result == {"type": "unknown", "raw": "every full moon"}

    def test_none_schedule(self):
        assert _schedule_to_dict(None) == {"type": "unknown", "raw": "None"}


class TestCategoryForSlug:
    def test_categories(self):
        assert _category_for_slug("mcp-connectors-health-check") == "health"
        assert _category_for_slug("expired-tokens-cleanup") == "cleanup"
        assert _category_for_slug("memory-finalize-outbox-reconcile") == "reconcile"
        assert _category_for_slug("ldap-users-sync") == "sync"
        assert _category_for_slug("discovery-rescan") == "other"

    def test_case_insensitive(self):
        assert _category_for_slug("HEALTH-watchdog") == "health"


class TestGetBeatScheduleDefs:
    def test_builds_defs_and_skips_entries_without_task(self):
        schedule = {
            "health-check": {"task": "app.workers.health_check", "schedule": IntervalSchedule(30)},
            "broken-entry": {"schedule": IntervalSchedule(30)},
            "empty-task": {"task": "   ", "schedule": IntervalSchedule(30)},
        }

        with patch(
            "app.services.periodic_task_sync_service.get_effective_beat_schedule",
            return_value=schedule,
        ):
            defs = get_beat_schedule_defs()

        assert defs == [
            BeatTaskDef(
                slug="health-check",
                task_path="app.workers.health_check",
                schedule={"type": "interval", "seconds": 30},
            )
        ]

    def test_none_spec_is_skipped(self):
        with patch(
            "app.services.periodic_task_sync_service.get_effective_beat_schedule",
            return_value={"broken": None},
        ):
            assert get_beat_schedule_defs() == []


class TestSyncFromBeat:
    def _session_returning(self, rows: list[PeriodicTask]) -> AsyncMock:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result)
        return session

    def _defs(self, *defs: BeatTaskDef) -> list[BeatTaskDef]:
        return list(defs)

    async def test_creates_new_task_with_catalog_presentation(self):
        session = self._session_returning([])
        defs = self._defs(
            BeatTaskDef(
                slug="mcp-connectors-health-check",
                task_path="app.workers.check_mcp",
                schedule={"type": "interval", "seconds": 60},
            )
        )

        with patch("app.services.periodic_task_sync_service.get_beat_schedule_defs", return_value=defs):
            await PeriodicTaskSyncService(session).sync_from_beat()

        added = [call.args[0] for call in session.add.call_args_list]
        assert len(added) == 1
        row = added[0]
        assert isinstance(row, PeriodicTask)
        assert row.slug == "mcp-connectors-health-check"
        # Presentation from the operator catalog, not the raw slug.
        assert row.name == "Проверка MCP-коннекторов"
        assert row.description
        assert row.category == "health"
        assert row.default_schedule == {"type": "interval", "seconds": 60}
        assert row.is_enabled is True
        assert row.is_orphaned is False
        session.flush.assert_awaited_once()

    async def test_creates_task_without_presentation_as_other(self):
        session = self._session_returning([])
        defs = self._defs(
            BeatTaskDef(slug="brand-new-task", task_path="app.workers.new_task", schedule={"type": "crontab", "hour": "4"})
        )

        with patch("app.services.periodic_task_sync_service.get_beat_schedule_defs", return_value=defs):
            await PeriodicTaskSyncService(session).sync_from_beat()

        row = session.add.call_args.args[0]
        assert row.name == "brand-new-task"
        assert row.description is None
        assert row.category == "other"

    async def test_updates_existing_row_from_beat(self):
        existing = PeriodicTask(
            slug="ldap-users-sync",
            task_path="app.workers.OLD_PATH",
            name="Old name",
            category="other",
            default_schedule={"type": "interval", "seconds": 999},
            is_orphaned=True,
        )
        session = self._session_returning([existing])
        defs = self._defs(
            BeatTaskDef(
                slug="ldap-users-sync",
                task_path="app.workers.sync_ldap",
                schedule={"type": "crontab", "hour": "3"},
            )
        )

        with patch("app.services.periodic_task_sync_service.get_beat_schedule_defs", return_value=defs):
            await PeriodicTaskSyncService(session).sync_from_beat()

        assert existing.task_path == "app.workers.sync_ldap"
        assert existing.name == "Синхронизация пользователей LDAP"
        assert existing.category == "sync"
        assert existing.default_schedule == {"type": "crontab", "hour": "3"}
        assert existing.is_orphaned is False
        session.add.assert_not_called()

    async def test_marks_rows_missing_from_beat_as_orphaned(self):
        active = PeriodicTask(
            slug="kept-task", task_path="p", name="n", category="other", default_schedule={}
        )
        orphan = PeriodicTask(
            slug="removed-task", task_path="p", name="n", category="other", default_schedule={}, is_orphaned=False
        )
        session = self._session_returning([active, orphan])
        defs = self._defs(BeatTaskDef(slug="kept-task", task_path="p", schedule={}))

        with patch("app.services.periodic_task_sync_service.get_beat_schedule_defs", return_value=defs):
            await PeriodicTaskSyncService(session).sync_from_beat()

        assert active.is_orphaned is False
        assert orphan.is_orphaned is True
