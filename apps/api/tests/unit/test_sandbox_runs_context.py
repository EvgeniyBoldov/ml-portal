from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.routers.sandbox.runs import _fail_sandbox_chat_turn


@pytest.mark.asyncio
async def test_setup_failure_terminalizes_existing_hidden_sandbox_turn() -> None:
    turn = SimpleNamespace(id=uuid4())
    turns = AsyncMock()
    turns.get_by_runtime_run_id = AsyncMock(return_value=turn)

    with patch("app.api.v1.routers.sandbox.runs.ChatTurnService", return_value=turns):
        await _fail_sandbox_chat_turn(AsyncMock(), run_id=uuid4(), error="agent resolution failed")

    turns.fail_turn.assert_awaited_once_with(turn.id, error_message="agent resolution failed")
