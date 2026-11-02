"""Sandbox lifecycle checks in an isolated PostgreSQL schema.

Run with SANDBOX_LIFECYCLE_PG=1. Existing application rows are never modified.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn
from app.models.sandbox import SandboxRun
from app.runtime import RuntimeEvent
from app.services.chat_turn_service import ChatTurnIdempotencyError, ChatTurnService
from app.services.sandbox.runtime_runner import SandboxRuntimeRunner
from app.services.sandbox.turn_lifecycle import SandboxTurnLifecycleService
from app.services.sandbox_service import SandboxService

pytestmark = pytest.mark.skipif(
    os.getenv("SANDBOX_LIFECYCLE_PG") != "1", reason="requires opt-in PostgreSQL",
)


@pytest_asyncio.fixture
async def sessions():
    schema = "sandbox_lifecycle_test_" + uuid4().hex
    admin = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for name in ("chats", "chat_turns", "sandbox_runs"):
                await conn.execute(text(
                    f'CREATE TABLE "{schema}"."{name}" (LIKE public."{name}" INCLUDING ALL)'
                ))
        engine = create_async_engine(
            get_settings().ASYNC_DB_URL,
            connect_args={"server_settings": {"search_path": f'"{schema}"'}},
        )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def seed_turn(sessions, *, run_status: str, turn_status: str, pause_status=None):
    chat_id, user_id, run_id, turn_id = (uuid4() for _ in range(4))
    async with sessions() as db:
        db.add(Chats(id=chat_id, owner_id=user_id, name="synthetic sandbox lifecycle"))
        db.add(SandboxRun(
            id=run_id, session_id=uuid4(), branch_id=uuid4(), snapshot_id=uuid4(),
            request_text="synthetic request", status=run_status,
        ))
        db.add(ChatTurn(
            id=turn_id, chat_id=chat_id, user_id=user_id,
            runtime_run_id=run_id, status=turn_status, pause_status=pause_status,
        ))
        await db.commit()
    return chat_id, user_id, run_id, turn_id


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["failed", "completed", "cancelled"])
async def test_terminal_sandbox_run_reconciles_waiting_turn_and_accepts_retry(sessions, terminal_status):
    chat_id, user_id, _, turn_id = await seed_turn(
        sessions, run_status=terminal_status, turn_status="waiting_input", pause_status="failed",
    )
    async with sessions() as db:
        assert await SandboxTurnLifecycleService(db).reconcile_terminal_turns(chat_id=chat_id) == 1
        await db.commit()
    async with sessions() as db:
        previous = await db.get(ChatTurn, turn_id)
        assert previous.status == terminal_status
        assert previous.pause_status is None
        assert previous.completed_at is not None
        new_turn = await ChatTurnService(db).start_turn(
            chat_id=chat_id, user_id=user_id, runtime_run_id=uuid4(),
        )
        assert new_turn.status == "running"
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "waiting_input", "waiting_confirmation"])
async def test_live_or_real_waiting_sandbox_run_remains_busy(sessions, status):
    chat_id, user_id, _, turn_id = await seed_turn(
        sessions, run_status=status, turn_status=status,
        pause_status=status if status.startswith("waiting_") else None,
    )
    async with sessions() as db:
        previous_turn = await db.get(ChatTurn, turn_id)
        previous_turn.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        # A live runner renews heartbeat even when started_at is old.
        previous_turn.heartbeat_at = datetime.now(timezone.utc)
        await db.commit()
    async with sessions() as db:
        assert await SandboxTurnLifecycleService(db).reconcile_terminal_turns(chat_id=chat_id) == 0
        with pytest.raises(ChatTurnIdempotencyError):
            await ChatTurnService(db).start_turn(chat_id=chat_id, user_id=user_id, runtime_run_id=uuid4())
        await db.rollback()
    async with sessions() as db:
        assert (await db.get(ChatTurn, turn_id)).status == status


@pytest.mark.asyncio
async def test_concurrent_retries_reconcile_once_and_open_only_one_turn(sessions):
    chat_id, user_id, _, _ = await seed_turn(
        sessions, run_status="failed", turn_status="waiting_input", pause_status="failed",
    )

    async def retry():
        async with sessions() as db:
            await SandboxTurnLifecycleService(db).reconcile_terminal_turns(chat_id=chat_id)
            try:
                await ChatTurnService(db).start_turn(chat_id=chat_id, user_id=user_id, runtime_run_id=uuid4())
                await db.commit()
                return True
            except ChatTurnIdempotencyError:
                await db.rollback()
                return False

    assert sorted(await asyncio.gather(retry(), retry())) == [False, True]


@pytest.mark.asyncio
async def test_concurrent_resume_claim_has_one_owner_and_loser_preserves_live_turn(sessions):
    _, _, run_id, turn_id = await seed_turn(
        sessions, run_status="waiting_input", turn_status="waiting_input", pause_status="waiting_input",
    )
    action = {"kind": "input", "pause_id": "first-pause"}
    context = {"pause_id": "first-pause", "question": "Need input"}
    async with sessions() as db:
        run = await db.get(SandboxRun, run_id)
        run.paused_action, run.paused_context = action, context
        await db.commit()

    async def resume():
        async with sessions() as db:
            claimed = await SandboxService(db).claim_resume_run(
                run_id, expected_status="waiting_input",
                expected_paused_action=action, expected_paused_context=context,
            )
            if not claimed:
                # A rejected request releases its transaction and cannot own
                # cleanup of the execution claimed by the winning request.
                await db.rollback()
                return False
            await ChatTurnService(db).resume_turn(turn_id)
            await db.commit()
            return True

    assert sorted(await asyncio.gather(resume(), resume())) == [False, True]
    async with sessions() as db:
        assert (await db.get(SandboxRun, run_id)).status == "running"
        assert (await db.get(ChatTurn, turn_id)).status == "running"


@pytest.mark.asyncio
async def test_stale_resume_checkpoint_cannot_claim_a_new_pause(sessions):
    _, _, run_id, _ = await seed_turn(
        sessions, run_status="waiting_input", turn_status="waiting_input", pause_status="waiting_input",
    )
    async with sessions() as db:
        run = await db.get(SandboxRun, run_id)
        run.paused_action = {"kind": "input", "pause_id": "new-pause"}
        run.paused_context = {"pause_id": "new-pause", "question": "A later question"}
        await db.commit()
    async with sessions() as db:
        assert not await SandboxService(db).claim_resume_run(
            run_id, expected_status="waiting_input",
            expected_paused_action={"kind": "input", "pause_id": "old-pause"},
            expected_paused_context={"pause_id": "old-pause", "question": "An earlier question"},
        )
        await db.rollback()
    async with sessions() as db:
        run = await db.get(SandboxRun, run_id)
        assert run.status == "waiting_input"
        assert run.paused_context["pause_id"] == "new-pause"


@pytest.mark.asyncio
@pytest.mark.parametrize("json_null", [False, True])
async def test_resume_claim_handles_legacy_null_pause_payloads(sessions, json_null):
    _, _, run_id, _ = await seed_turn(
        sessions, run_status="waiting_input", turn_status="waiting_input", pause_status="waiting_input",
    )
    if json_null:
        async with sessions() as db:
            await db.execute(text(
                "UPDATE sandbox_runs SET paused_action = 'null'::jsonb, paused_context = 'null'::jsonb "
                "WHERE id = :run_id"
            ), {"run_id": run_id})
            await db.commit()
    async with sessions() as db:
        assert await SandboxService(db).claim_resume_run(
            run_id, expected_status="waiting_input",
            expected_paused_action=None, expected_paused_context=None,
        )
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "completed", "failed", "cancelled"])
async def test_resume_claim_rejects_nonwaiting_runs(sessions, status):
    _, _, run_id, _ = await seed_turn(
        sessions, run_status=status, turn_status="running",
    )
    async with sessions() as db:
        assert not await SandboxService(db).claim_resume_run(
            run_id, expected_status=status,
            expected_paused_action=None, expected_paused_context=None,
        )
        await db.rollback()
    async with sessions() as db:
        assert (await db.get(SandboxRun, run_id)).status == status


@pytest.mark.asyncio
async def test_stale_stop_does_not_overwrite_completed_run(sessions):
    _, _, run_id, _ = await seed_turn(
        sessions, run_status="running", turn_status="running",
    )
    async with sessions() as stale_db:
        service = SandboxService(stale_db)
        stale_run = await service.get_run(run_id)
        assert stale_run.status == "running"
        async with sessions() as owner_db:
            await SandboxService(owner_db).finish_run(run_id, "completed")
            await owner_db.commit()
        # The stop request loaded running before the owner committed completed.
        # Its cached ORM record must not undo that terminal transition.
        await service.request_cancel(run_id)
        await stale_db.commit()
    async with sessions() as db:
        assert (await db.get(SandboxRun, run_id)).status == "completed"


@pytest.mark.asyncio
async def test_preflight_failure_closes_persisted_turn_and_accepts_retry(sessions, monkeypatch):
    from app.services.sandbox import runtime_runner as module

    chat_id, user_id, run_id, turn_id = await seed_turn(
        sessions, run_status="running", turn_status="running",
    )

    class Control:
        subscribe = AsyncMock()
        unsubscribe = AsyncMock()

        async def wait_for_cancel(self):
            await asyncio.Event().wait()

    class Pipeline:
        def __init__(self, **kwargs):
            pass

        async def execute(self, *args):
            yield RuntimeEvent.error("TurnPreflight unavailable", error_code="turn_preflight_unavailable")
            yield RuntimeEvent.stop(reason="failed", run_id=str(run_id), message="Preflight failed")

    monkeypatch.setattr(module, "RuntimeRunControlSubscriber", lambda **kwargs: Control())
    monkeypatch.setattr(module, "RuntimePipeline", Pipeline)
    monkeypatch.setattr(module.RuntimeEventJournalFactory, "create", lambda **kwargs: SimpleNamespace(emit=AsyncMock()))
    command = SimpleNamespace(
        run_id=run_id, user_id=user_id, tenant_id=uuid4(), tool_context=None,
        pipeline_request=SimpleNamespace(chat_turn_id=str(turn_id), sandbox_overrides={}),
    )
    await SandboxRuntimeRunner()._run(command=command, llm_client=AsyncMock(), session_factory=sessions)

    async with sessions() as db:
        previous_run = await db.get(SandboxRun, run_id)
        previous_turn = await db.get(ChatTurn, turn_id)
        assert previous_run.status == previous_turn.status == "failed"
        assert previous_run.finished_at is not None
        assert previous_turn.completed_at is not None
        assert previous_turn.pause_status is None
        await ChatTurnService(db).start_turn(chat_id=chat_id, user_id=user_id, runtime_run_id=uuid4())
        await db.commit()
