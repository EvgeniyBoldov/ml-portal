import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.runtime import RuntimeEvent
from app.api.v1.routers.sandbox import runs as sandbox_runs
from app.services.sandbox.turn_lifecycle import SandboxTurnLifecycleService
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


@pytest.mark.parametrize(
    ("reason", "expected_status"),
    [("failed", "failed"), ("completed", "completed"), ("budget_exceeded", "failed")],
)
def test_terminal_stop_does_not_pause_companion_turn(reason: str, expected_status: str) -> None:
    event = RuntimeEvent.stop(reason=reason, run_id=str(uuid4()), message="preflight failed")

    state = SandboxRuntimeRunner._terminal_state_for_event(event)

    assert state is not None
    assert state[0] == expected_status
    assert state[2] is None


def test_unrecognized_final_stop_reason_maps_to_sandbox_failure() -> None:
    event = RuntimeEvent.final(
        "", run_id=str(uuid4()), stop_reason="budget_exceeded",
    )

    assert SandboxRuntimeRunner._terminal_state_for_event(event) == (
        "failed", "budget_exceeded", None,
    )


@pytest.mark.parametrize("reason", ["waiting_input", "waiting_confirmation"])
def test_hitl_stop_pauses_companion_turn(reason: str) -> None:
    event = RuntimeEvent.stop(reason=reason, run_id=str(uuid4()), question="Need input")

    state = SandboxRuntimeRunner._terminal_state_for_event(event)

    assert state is not None
    assert state[0] == reason
    assert state[2] is not None
    assert state[2]["reason"] == reason


def test_error_after_pause_clears_pause_and_fails_turn() -> None:
    pause_event = RuntimeEvent.stop(reason="waiting_input", run_id=str(uuid4()), question="Need input")
    error_event = RuntimeEvent.error("Preflight failed", error_code="preflight_failed")

    assert SandboxRuntimeRunner._terminal_state_for_event(pause_event)[2] is not None
    terminal_state = SandboxRuntimeRunner._terminal_state_for_event(error_event)

    assert terminal_state == ("failed", "Preflight failed", None)


@pytest.mark.asyncio
async def test_setup_failure_terminalizes_only_its_sandbox_run_and_turn() -> None:
    run_id = uuid4()
    terminal_db = AsyncMock()
    lifecycle = AsyncMock()

    @asynccontextmanager
    async def session_factory():
        yield terminal_db

    with (
        patch("app.api.v1.routers.sandbox.runs.SandboxTurnLifecycleService", return_value=lifecycle),
    ):
        await sandbox_runs._fail_sandbox_setup(
            session_factory=session_factory, run_id=run_id, error="idempotency_processing",
        )

    lifecycle.fail_setup.assert_awaited_once_with(run_id=run_id, error="idempotency_processing")
    terminal_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_failure_rolls_back_stream_transaction_before_terminal_session() -> None:
    run_id = uuid4()
    terminal_db = AsyncMock()
    stream_db = AsyncMock()
    lifecycle = AsyncMock()

    @asynccontextmanager
    async def session_factory():
        assert stream_db.rollback.await_count == 1
        yield terminal_db

    with patch("app.api.v1.routers.sandbox.runs.SandboxTurnLifecycleService", return_value=lifecycle):
        await sandbox_runs._fail_sandbox_setup(
            session_factory=session_factory, stream_db=stream_db, run_id=run_id,
            error="idempotency_processing",
        )

    stream_db.rollback.assert_awaited_once()
    lifecycle.fail_setup.assert_awaited_once_with(run_id=run_id, error="idempotency_processing")
    terminal_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_stream_guard_closes_run_before_runner_ownership_and_emits_terminal_sse() -> None:
    run_id = uuid4()
    stream_db = AsyncMock()
    state = {"runner_started": False, "stream_db": stream_db}

    async def setup_failure():
        raise RuntimeError("setup failed")
        yield "unreachable"

    with patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup:
        frames = [
            frame async for frame in sandbox_runs._guard_sandbox_setup_stream(
                setup_failure(), session_factory=AsyncMock(), run_id=run_id, state=state,
            )
        ]

    fail_setup.assert_awaited_once()
    assert fail_setup.await_args.kwargs["stream_db"] is stream_db
    assert "event: error" in frames[0]
    assert "event: done" in frames[1]


@pytest.mark.asyncio
async def test_setup_stream_guard_preserves_runner_ownership_after_observer_error() -> None:
    run_id = uuid4()
    state = {"runner_started": True, "stream_db": AsyncMock()}

    async def observer_failure():
        raise RuntimeError("observer failed")
        yield "unreachable"

    with patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup:
        with pytest.raises(RuntimeError, match="observer failed"):
            async for _ in sandbox_runs._guard_sandbox_setup_stream(
                observer_failure(), session_factory=AsyncMock(), run_id=run_id, state=state,
            ):
                pass

    fail_setup.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_stream_guard_cancellation_terminalizes_before_runner_start() -> None:
    run_id = uuid4()
    state = {"runner_started": False, "stream_db": AsyncMock()}
    started = asyncio.Event()

    async def slow_setup():
        started.set()
        await asyncio.Event().wait()
        yield "unreachable"

    with patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup:
        async def consume():
            async for _ in sandbox_runs._guard_sandbox_setup_stream(
                slow_setup(), session_factory=AsyncMock(), run_id=run_id, state=state,
            ):
                pass

        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    fail_setup.assert_awaited_once()
    assert fail_setup.await_args.kwargs["run_id"] == run_id


@pytest.mark.asyncio
async def test_setup_stream_guard_disconnect_after_handoff_keeps_runner_owner() -> None:
    run_id = uuid4()
    state = {"runner_started": True, "stream_db": AsyncMock()}

    async def observation():
        yield "event: run_started\ndata: {}\n\n"
        await asyncio.Event().wait()

    with patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup:
        guarded = sandbox_runs._guard_sandbox_setup_stream(
            observation(), session_factory=AsyncMock(), run_id=run_id, state=state,
        )
        assert "run_started" in await guarded.__anext__()
        await guarded.aclose()

    fail_setup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("turn_status", "run_status", "expected_status"),
    [
        ("waiting_input", "failed", "failed"),
        ("waiting_input", "waiting_input", "waiting_input"),
        ("running", "running", "running"),
    ],
)
async def test_reconcile_only_closes_turn_when_its_sandbox_run_is_terminal(
    turn_status: str, run_status: str, expected_status: str,
) -> None:
    chat_id, run_id = uuid4(), uuid4()
    turn = SimpleNamespace(
        chat_id=chat_id, runtime_run_id=run_id, status=turn_status,
        pause_status="waiting_input" if turn_status == "waiting_input" else None,
        paused_action={"kind": "input"} if turn_status == "waiting_input" else None,
        paused_context={"question": "why"} if turn_status == "waiting_input" else None,
        paused_at=None, completed_at=None, error_message=None,
    )
    sandbox_run = SimpleNamespace(
        id=run_id, status=run_status,
        finished_at=None, error="preflight failed" if run_status == "failed" else None,
    )
    chat_result = MagicMock()
    chat_result.scalar_one_or_none.return_value = SimpleNamespace(id=chat_id)
    turns_result = MagicMock()
    turns_result.scalars.return_value.all.return_value = [turn]
    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [sandbox_run]
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[chat_result, turns_result, runs_result])

    reconciled = await SandboxTurnLifecycleService(session).reconcile_terminal_turns(chat_id)

    assert turn.status == expected_status
    assert reconciled == (1 if run_status == "failed" else 0)
    if run_status == "failed":
        assert turn.pause_status is None
        assert turn.paused_action is None
        assert turn.paused_context is None
        assert turn.error_message == "preflight failed"


@pytest.mark.asyncio
async def test_control_unsubscribe_failure_does_not_skip_terminal_persistence() -> None:
    run_id = uuid4()
    db = AsyncMock()
    sandbox_service = MagicMock()
    sandbox_service.get_run = AsyncMock(return_value=None)
    sandbox_service.finish_run = AsyncMock()
    control = MagicMock()
    control.subscribe = AsyncMock()
    control.unsubscribe = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    command = SimpleNamespace(
        run_id=run_id,
        user_id=uuid4(),
        tenant_id=uuid4(),
        pipeline_request=SimpleNamespace(chat_turn_id=None, sandbox_overrides={}),
    )

    @asynccontextmanager
    async def session_factory():
        yield db

    with (
        patch("app.services.sandbox.runtime_runner.RuntimeRunControlSubscriber", return_value=control),
        patch("app.services.sandbox.runtime_runner.SandboxService", return_value=sandbox_service),
    ):
        await SandboxRuntimeRunner()._run(
            command=command, llm_client=AsyncMock(), session_factory=session_factory,
        )

    sandbox_service.finish_run.assert_awaited_once_with(run_id, "completed", None)
    db.commit.assert_awaited_once()


async def _exercise_runner_event_sequence(events, *, cancel: bool = False):
    run_id, turn_id = uuid4(), uuid4()
    execution_db, terminal_db = AsyncMock(), AsyncMock()
    sandbox_service = MagicMock()
    sandbox_service.get_run = AsyncMock(return_value=SimpleNamespace(status="running"))
    sandbox_service.finish_run = AsyncMock()
    sandbox_service.pause_run = AsyncMock()
    turns = AsyncMock()
    turns.cancel_turn.return_value = None
    control = MagicMock()
    control.subscribe = AsyncMock()
    control.unsubscribe = AsyncMock()
    if cancel:
        control.wait_for_cancel = AsyncMock(return_value=None)
    else:
        async def never_cancel():
            await asyncio.Future()

        control.wait_for_cancel = never_cancel
    event_logger = MagicMock()
    event_logger.error = AsyncMock()
    event_logger.emit = AsyncMock()
    tail_bus = MagicMock()
    tail_bus.publish = AsyncMock()
    session_count = 0

    @asynccontextmanager
    async def session_factory():
        nonlocal session_count
        session_count += 1
        yield execution_db if session_count == 1 else terminal_db

    async def event_stream():
        for event in events:
            if isinstance(event, Exception):
                raise event
            yield event

    pipeline = MagicMock()
    pipeline.execute.return_value = event_stream()
    command = SimpleNamespace(
        run_id=run_id,
        user_id=uuid4(),
        tenant_id=uuid4(),
        pipeline_request=SimpleNamespace(
            chat_turn_id=str(turn_id), sandbox_overrides={"sandbox_branch_id": str(uuid4())},
        ),
        tool_context=SimpleNamespace(),
    )
    with (
        patch("app.services.sandbox.runtime_runner.RuntimeRunControlSubscriber", return_value=control),
        patch("app.services.sandbox.runtime_runner.SandboxService", return_value=sandbox_service),
        patch("app.services.sandbox.runtime_runner.ChatTurnService", return_value=turns),
        patch("app.services.sandbox.runtime_runner.RuntimePipeline", return_value=pipeline),
        patch("app.services.sandbox.runtime_runner.RuntimeTailEventBus", return_value=tail_bus),
        patch("app.services.sandbox.runtime_runner.RuntimeEventJournalFactory.create", return_value=event_logger),
    ):
        await SandboxRuntimeRunner()._run(
            command=command, llm_client=AsyncMock(), session_factory=session_factory,
        )
    return run_id, turn_id, sandbox_service, turns


@pytest.mark.asyncio
async def test_runner_error_then_terminal_failed_stop_fails_the_companion_turn() -> None:
    run_id, turn_id, sandbox_service, turns = await _exercise_runner_event_sequence([
        RuntimeEvent.error("preflight connection failed"),
        RuntimeEvent.stop(reason="failed", run_id=str(uuid4()), message="preflight failed"),
    ])

    sandbox_service.finish_run.assert_awaited_once_with(run_id, "failed", "preflight failed")
    turns.fail_turn.assert_awaited_once_with(str(turn_id), error_message="preflight failed")
    turns.pause_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_exception_after_pause_fails_instead_of_persisting_pause() -> None:
    run_id, turn_id, sandbox_service, turns = await _exercise_runner_event_sequence([
        RuntimeEvent.stop(reason="waiting_input", run_id=str(uuid4()), question="Need input"),
        RuntimeError("commit failed after pause"),
    ])

    sandbox_service.finish_run.assert_awaited_once_with(run_id, "failed", "Sandbox runtime execution failed")
    turns.fail_turn.assert_awaited_once_with(
        str(turn_id), error_message="Sandbox runtime execution failed",
    )
    turns.pause_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_cancel_closes_companion_turn_as_cancelled() -> None:
    run_id, turn_id, sandbox_service, turns = await _exercise_runner_event_sequence([], cancel=True)

    sandbox_service.finish_run.assert_awaited_once_with(run_id, "cancelled", "Cancelled by user")
    turns.cancel_turn.assert_awaited_once_with(str(turn_id), error_message="Cancelled by user")


@pytest.mark.asyncio
async def test_sandbox_turn_heartbeat_commits_active_lease_and_stops_after_terminal_status() -> None:
    run_id = uuid4()
    sessions = [AsyncMock(), AsyncMock()]
    turns = AsyncMock()
    turns.heartbeat_turn.side_effect = [True, False]
    session_index = 0

    @asynccontextmanager
    async def session_factory():
        nonlocal session_index
        session = sessions[session_index]
        session_index += 1
        yield session

    with (
        patch("app.services.sandbox.runtime_runner.asyncio.sleep", new_callable=AsyncMock) as sleep,
        patch("app.services.sandbox.runtime_runner.ChatTurnService", return_value=turns),
    ):
        sleep.side_effect = [None, None]
        await SandboxRuntimeRunner._heartbeat(run_id, session_factory)

    assert turns.heartbeat_turn.await_args_list[0].args == (run_id,)
    assert turns.heartbeat_turn.await_count == 2
    sessions[0].commit.assert_awaited_once()
    sessions[1].commit.assert_not_awaited()
