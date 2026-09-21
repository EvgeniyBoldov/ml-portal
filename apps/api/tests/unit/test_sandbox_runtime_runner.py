import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.sandbox.runtime_runner import SandboxRuntimeRunner


@pytest.mark.asyncio
async def test_cancel_local_interrupts_only_registered_live_task():
    runner = SandboxRuntimeRunner()
    run_id = uuid4()
    task = asyncio.create_task(asyncio.sleep(60))
    runner._tasks[run_id] = task  # local registry state is the unit under test

    assert await runner.cancel_local(run_id) is True
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_local_is_idempotent_when_run_is_not_owned_here():
    assert await SandboxRuntimeRunner().cancel_local(uuid4()) is False


@pytest.mark.asyncio
async def test_terminal_completion_completes_companion_chat_turn() -> None:
    turn_id = str(uuid4())
    turns = AsyncMock()
    command = SimpleNamespace(pipeline_request=SimpleNamespace(chat_turn_id=turn_id, sandbox_overrides={}))

    with patch("app.services.sandbox.runtime_runner.ChatTurnService", return_value=turns):
        await SandboxRuntimeRunner._persist_chat_turn_terminal(
            terminal_db=AsyncMock(), command=command, status="completed", error=None, paused_payload=None,
        )

    turns.complete_turn.assert_awaited_once_with(turn_id)


@pytest.mark.asyncio
async def test_terminal_pause_pauses_companion_chat_turn() -> None:
    turn_id = str(uuid4())
    run_id = uuid4()
    turns = AsyncMock()
    command = SimpleNamespace(
        run_id=run_id,
        pipeline_request=SimpleNamespace(chat_turn_id=turn_id, sandbox_overrides={}),
    )
    paused = {"reason": "waiting_input", "action": {"kind": "input"}, "context": {"question": "why"}}

    with patch("app.services.sandbox.runtime_runner.ChatTurnService", return_value=turns):
        await SandboxRuntimeRunner._persist_chat_turn_terminal(
            terminal_db=AsyncMock(), command=command, status="waiting_input", error=None, paused_payload=paused,
        )

    turns.pause_turn.assert_awaited_once_with(
        turn_id, pause_status="waiting_input", runtime_run_id=run_id,
        paused_action={"kind": "input"}, paused_context={"question": "why"},
    )
