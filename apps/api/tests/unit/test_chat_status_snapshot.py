from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services.chat_status_snapshot import (
    build_chat_status_snapshot,
    latest_chat_turns_for_owner,
    project_chat_status,
)


def _turn(**overrides):
    values = {
        "chat_id": uuid4(),
        "runtime_run_id": uuid4(),
        "status": "paused",
        "pause_status": "waiting_confirmation",
        "completed_at": None,
        "paused_at": None,
        "started_at": datetime(2026, 10, 27, tzinfo=timezone.utc),
        "user_message_id": uuid4(),
        "assistant_message_id": uuid4(),
        "error_message": "private error",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_status_projection_is_normalized_and_contains_no_message_or_error_data():
    turn = _turn()
    item = project_chat_status(
        turn,
        stage_snapshot={
            "stage": "executing",
            "updated_at": "2026-10-27T10:05:00+00:00",
            "description": "private runtime detail",
            "action": "private tool call",
        },
    )

    assert item == {
        "chat_id": str(turn.chat_id),
        "run_id": str(turn.runtime_run_id),
        "status": "waiting_confirmation",
        "stage": "executing",
        "updated_at": turn.started_at.isoformat(),
        "stage_updated_at": "2026-10-27T10:05:00+00:00",
    }
    assert not ({"content", "description", "action", "error_message", "user_message_id"} & item.keys())


def test_snapshot_sorts_by_chat_and_rejects_unknown_stage_values():
    first, second = _turn(), _turn(status="completed", pause_status=None)
    items = build_chat_status_snapshot(
        [second, first],
        stages_by_run_id={str(first.runtime_run_id): {"stage": "raw_trace_stage"}},
    )

    assert [item["chat_id"] for item in items] == sorted([str(first.chat_id), str(second.chat_id)])
    first_item = next(item for item in items if item["chat_id"] == str(first.chat_id))
    assert first_item["stage"] is None


@pytest.mark.asyncio
async def test_latest_turn_query_is_scoped_by_chat_owner():
    owner_id = uuid4()
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    session = AsyncMock()
    session.execute.return_value = result

    await latest_chat_turns_for_owner(session, owner_id=owner_id)

    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "chats.owner_id" in compiled
    assert "row_number() OVER (PARTITION BY chat_turns.chat_id" in compiled
