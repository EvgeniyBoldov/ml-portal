from datetime import datetime
from pathlib import Path
import importlib.util
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chat_turn_service import ChatTurnService
from app.core.chat_lifecycle import normalize_chat_turn_status, waiting_status_for_pause


@pytest.mark.parametrize(
    ("stored", "pause", "expected"),
    [
        ("running", None, "running"),
        ("started", None, "running"),
        ("resumed", None, "running"),
        ("paused", "waiting_input", "waiting_input"),
        ("paused", "waiting_confirmation", "waiting_confirmation"),
        ("paused", "legacy_unknown_pause", "waiting_input"),
        ("waiting_input", None, "waiting_input"),
        ("waiting_confirmation", None, "waiting_confirmation"),
        ("completed", None, "completed"),
        ("failed", None, "failed"),
        ("cancelled", None, "cancelled"),
    ],
)
def test_legacy_and_canonical_chat_turn_status_projection(stored, pause, expected):
    assert normalize_chat_turn_status(stored, pause) == expected


def test_pause_transition_uses_waiting_lifecycle_status():
    assert waiting_status_for_pause("waiting_input") == "waiting_input"
    assert waiting_status_for_pause("waiting_confirmation") == "waiting_confirmation"
    assert waiting_status_for_pause("legacy_unknown_pause") == "waiting_input"


@pytest.mark.asyncio
async def test_heartbeat_refreshes_only_active_turn():
    session = AsyncMock()
    service = ChatTurnService(session)
    turn = SimpleNamespace(status="running", heartbeat_at=None)
    service.get_by_runtime_run_id = AsyncMock(return_value=turn)

    assert await service.heartbeat_turn("run-1") is True
    assert isinstance(turn.heartbeat_at, datetime)
    session.flush.assert_awaited_once()
    turn.status = "completed"
    assert await service.heartbeat_turn("run-1") is False
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_clears_waiting_checkpoint_metadata():
    session = AsyncMock()
    service = ChatTurnService(session)
    turn = SimpleNamespace(
        status="waiting_confirmation",
        pause_status="waiting_confirmation",
        paused_action={"name": "confirm"},
        paused_context={"checkpoint": "saved"},
        paused_at=datetime.now(),
        error_message=None,
        completed_at=None,
    )
    service.get_by_id = AsyncMock(return_value=turn)

    result = await service.cancel_turn("turn-1", error_message="cancelled_by_user")

    assert result.status == "cancelled"
    assert result.pause_status is None
    assert result.paused_action is None
    assert result.paused_context is None
    assert result.paused_at is None
    assert result.error_message == "cancelled_by_user"
    assert result.completed_at is not None
    session.flush.assert_awaited_once()


def test_lifecycle_migration_backfills_aliases_and_heartbeat(monkeypatch):
    api_root = Path(__file__).parents[2]
    migration_path = api_root / "src/app/migrations/versions/0206_normalize_chat_turn_lifecycle.py"
    if not migration_path.exists():
        migration_path = api_root / "app/migrations/versions/0206_normalize_chat_turn_lifecycle.py"
    spec = importlib.util.spec_from_file_location("chat_lifecycle_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements = []
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement)))
    monkeypatch.setattr(migration.op, "add_column", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "alter_column", lambda *_args, **_kwargs: None)
    migration.upgrade()
    sql = "\n".join(statements)
    assert "status IN ('started', 'resumed')" in sql
    assert "waiting_confirmation" in sql and "waiting_input" in sql
    assert "heartbeat_at = started_at" in sql
