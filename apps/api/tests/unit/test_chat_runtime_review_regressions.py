from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.interfaces.llm import LLMErrorCode
from app.core.chat_lifecycle import ChatTurnStatus
from app.runtime.operation_errors import RuntimeErrorCode
from app.services import chat_runtime_runner as runner_module
from app.services import runtime_tail_event_bus as tail_bus_module
from app.services import chat_turn_orchestrator as orchestrator_module
from app.services.chat_runtime_runner import ChatRuntimeCommand, ChatRuntimeRunner
from app.services.chat_turn_orchestrator import ChatTurnOrchestrator
from app.services.runtime_tail_event_bus import RuntimeTailEventBus
from app.services.runtime_tail_event_bus import RuntimeRunControlSubscriber


@pytest.mark.parametrize(
    "code",
    [*(item.value for item in LLMErrorCode), *(item.value for item in RuntimeErrorCode)],
)
def test_error_normalizer_preserves_typed_catalog_codes(code: str) -> None:
    normalized = ChatTurnOrchestrator._normalize_runtime_error(code=code, raw_message="provider failure")

    assert normalized["code"] == code
    assert normalized["user_message"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("llm_rate_limited", "llm_rate_limited"),
        ("llm_context_window_exceeded", "llm_context_window_exceeded"),
        ("synthesis_file_failed", "synthesis_file_failed"),
        ("orchestrator_phase_timeout", "orchestrator_phase_timeout"),
        ("made_up_provider_code", "unknown_runtime_error"),
    ],
)
def test_error_normalizer_keeps_used_codes_and_only_falls_back_unknown(
    code: str, expected: str,
) -> None:
    assert ChatTurnOrchestrator._normalize_runtime_error(code=code, raw_message="")["code"] == expected


@pytest.mark.asyncio
async def test_tail_bus_closes_only_owned_client_when_publish_fails(monkeypatch):
    class Client:
        def __init__(self):
            self.closed = 0

        async def publish(self, *_args):
            raise OSError("redis down")

        async def aclose(self):
            self.closed += 1

    owned = Client()
    monkeypatch.setattr(tail_bus_module.aioredis, "from_url", lambda *_args, **_kwargs: owned)
    monkeypatch.setattr(tail_bus_module, "get_settings", lambda: SimpleNamespace(REDIS_URL="redis://unused"))
    with pytest.raises(OSError):
        await RuntimeTailEventBus().publish(stream_key="chat:run", payload={"type": "delta"})
    assert owned.closed == 1

    injected = Client()
    bus = RuntimeTailEventBus(redis_client=injected)
    with pytest.raises(OSError):
        await bus.publish(stream_key="chat:run", payload={"type": "delta"})
    assert injected.closed == 0


@pytest.mark.asyncio
async def test_control_subscriber_closes_resources_even_when_unsubscribe_and_delete_fail():
    calls: list[str] = []

    class PubSub:
        async def unsubscribe(self, *_args):
            calls.append("unsubscribe")
            raise OSError("unsubscribe failed")

        async def close(self):
            calls.append("pubsub_close")

    class Redis:
        async def delete(self, *_args):
            calls.append("delete")
            raise OSError("marker delete failed")

        async def aclose(self):
            calls.append("redis_close")

    subscriber = RuntimeRunControlSubscriber(run_id="run-1", persist_cancel_marker=True)
    subscriber._pubsub = PubSub()
    subscriber._redis = Redis()
    with pytest.raises(OSError):
        await subscriber.unsubscribe()

    assert calls == ["unsubscribe", "pubsub_close", "delete", "redis_close"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_subscribe", [False, True])
async def test_runner_start_closes_partial_control_subscription(monkeypatch, cancel_subscribe):
    calls: list[str] = []

    class PubSub:
        async def subscribe(self, *_args):
            if cancel_subscribe:
                raise asyncio.CancelledError
            raise OSError("Redis subscribe failed")

        async def unsubscribe(self, *_args):
            calls.append("unsubscribe")

        async def close(self):
            calls.append("pubsub_close")

    class Redis:
        def pubsub(self):
            return PubSub()

        async def delete(self, *_args):
            calls.append("marker_delete")

        async def aclose(self):
            calls.append("redis_close")

    class OwnerRedis:
        async def set(self, *_args, **_kwargs):
            raise AssertionError("owner key must not be set after failed subscribe")

    redis = Redis()
    monkeypatch.setattr(tail_bus_module.aioredis, "from_url", lambda *_args, **_kwargs: redis)
    monkeypatch.setattr(tail_bus_module, "get_settings", lambda: SimpleNamespace(REDIS_URL="redis://unused"))
    runner = ChatRuntimeRunner()
    command = ChatRuntimeCommand(
        run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(),
        content="hello", artifact_ids=[],
    )
    if cancel_subscribe:
        with pytest.raises(asyncio.CancelledError):
            await runner.start(
                command=command, llm_client=object(), redis_client=OwnerRedis(), session_factory=object(),
            )
    else:
        with pytest.raises(OSError, match="Redis subscribe failed"):
            await runner.start(
                command=command, llm_client=object(), redis_client=OwnerRedis(), session_factory=object(),
            )

    assert calls == ["unsubscribe", "pubsub_close", "marker_delete", "redis_close"]


@pytest.mark.asyncio
async def test_runner_control_waiter_failure_fails_turn_without_detached_execution(monkeypatch):
    started = asyncio.Event()
    execution_stopped = asyncio.Event()
    events: list[dict] = []
    persisted_status = {"value": ChatTurnStatus.RUNNING.value}

    class Control:
        async def wait_for_cancel(self):
            await started.wait()
            raise OSError("control Redis disconnected")

        async def unsubscribe(self):
            pass

    class Service:
        def __init__(self, **_kwargs):
            pass

        async def send_message_stream(self, **_kwargs):
            started.set()
            try:
                yield {"type": "stage", "activity": {"stage": "planning"}}
                await asyncio.Event().wait()
            finally:
                execution_stopped.set()
                persisted_status["value"] = ChatTurnStatus.CANCELLED.value

    class SessionContext:
        async def __aenter__(self):
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, *_args):
            pass

    class Repositories:
        def __init__(self, *_args):
            pass

        def get_chats_repository(self):
            return object()

        def get_chat_messages_repository(self):
            return object()

    class Turns:
        def __init__(self, _session):
            pass

        async def get_by_runtime_run_id(self, _run_id):
            return SimpleNamespace(id=uuid4(), status=persisted_status["value"])

        async def fail_turn(self, _turn_id, *, error_message):
            assert error_message == "chat_runtime_failed"
            persisted_status["value"] = ChatTurnStatus.FAILED.value

    class Bus:
        async def publish(self, *, stream_key, payload):
            events.append(payload)

    monkeypatch.setattr(runner_module, "ChatStreamService", Service)
    monkeypatch.setattr(runner_module, "AsyncRepositoryFactory", Repositories)
    monkeypatch.setattr(runner_module, "ChatTurnService", Turns)
    monkeypatch.setattr(runner_module, "CHAT_TURN_HEARTBEAT_SECONDS", 3600)

    runner = ChatRuntimeRunner()
    runner._event_bus = Bus()
    command = ChatRuntimeCommand(
        run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(),
        content="hello", artifact_ids=[],
    )
    await runner._run(
        command=command,
        llm_client=object(),
        redis_client=SimpleNamespace(set=AsyncMock(), delete=AsyncMock()),
        session_factory=SessionContext,
        control=Control(),
        ready=asyncio.Event(),
    )

    assert execution_stopped.is_set()
    assert persisted_status["value"] == ChatTurnStatus.FAILED.value
    assert not any(payload.get("event", {}).get("type") == "cancelled" for payload in events)
    assert any(payload.get("event", {}).get("code") == "chat_runtime_failed" for payload in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("optional_work_pending", [False, True])
async def test_control_channel_failure_does_not_rewrite_a_committed_final(monkeypatch, optional_work_pending):
    final_sent = asyncio.Event()
    control_failed = asyncio.Event()
    finish_optional = asyncio.Event()
    events = []

    class Control:
        async def wait_for_cancel(self):
            await final_sent.wait()
            control_failed.set()
            raise OSError("control channel lost after final")

        async def unsubscribe(self):
            pass

    class Service:
        def __init__(self, **_kwargs):
            pass

        async def send_message_stream(self, **_kwargs):
            yield {"type": "final", "message_id": "assistant", "content": "Observed answer"}
            if optional_work_pending:
                await finish_optional.wait()

    class Repositories:
        def __init__(self, *_args):
            pass

        def get_chats_repository(self):
            return object()

        def get_chat_messages_repository(self):
            return object()

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            pass

    class Bus:
        async def publish(self, *, stream_key, payload):
            events.append(payload)
            if payload.get("event", {}).get("type") == "final":
                final_sent.set()

    monkeypatch.setattr(runner_module, "ChatStreamService", Service)
    monkeypatch.setattr(runner_module, "AsyncRepositoryFactory", Repositories)
    runner = ChatRuntimeRunner()
    runner._event_bus = Bus()
    runner._heartbeat = AsyncMock()
    runner._fail_turn = AsyncMock()
    command = ChatRuntimeCommand(
        run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(), content="hello", artifact_ids=[],
    )
    run = asyncio.create_task(runner._run(
        command=command, llm_client=object(),
        redis_client=SimpleNamespace(delete=AsyncMock()),
        session_factory=SessionContext, control=Control(), ready=asyncio.Event(),
    ))
    await asyncio.wait_for(control_failed.wait(), timeout=1)
    await asyncio.sleep(0)
    finish_optional.set()
    await asyncio.wait_for(run, timeout=1)

    runner._fail_turn.assert_not_awaited()
    assert any(event.get("event", {}).get("type") == "final" for event in events)
    assert not any(event.get("event", {}).get("type") in {"error", "cancelled"} for event in events)
    assert not any(event.get("event", {}).get("status") == "failed" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["stage_read", "state_publish", "final_publish", "owner_cancel"])
async def test_optional_delivery_failure_does_not_reclassify_committed_outcome(monkeypatch, failure_point):
    events = []

    class Control:
        async def wait_for_cancel(self):
            await asyncio.Event().wait()

        async def unsubscribe(self):
            pass

    class Service:
        def __init__(self, **_kwargs):
            pass

        async def send_message_stream(self, **_kwargs):
            yield {"type": "state", "status": "completed"}
            yield {"type": "final", "message_id": "answer", "content": "Persisted answer"}

    class Repositories:
        def __init__(self, *_args):
            pass

        def get_chats_repository(self):
            return object()

        def get_chat_messages_repository(self):
            return object()

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            pass

    class Bus:
        async def publish(self, *, stream_key, payload):
            event_type = payload.get("event", {}).get("type")
            if failure_point == "owner_cancel" and event_type == "final":
                raise asyncio.CancelledError
            if (failure_point == "state_publish" and event_type == "state"
                    or failure_point == "final_publish" and event_type == "final"):
                raise OSError("terminal event delivery failed")
            events.append(payload)

    monkeypatch.setattr(runner_module, "ChatStreamService", Service)
    monkeypatch.setattr(runner_module, "AsyncRepositoryFactory", Repositories)
    runner = ChatRuntimeRunner()
    runner._event_bus = Bus()
    runner._heartbeat = AsyncMock()
    runner._fail_turn = AsyncMock()
    command = ChatRuntimeCommand(
        run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(), content="hello", artifact_ids=[],
    )
    execution = runner._run(
        command=command, llm_client=object(), session_factory=SessionContext,
        redis_client=SimpleNamespace(delete=AsyncMock(), get=AsyncMock(
            side_effect=OSError("optional stage read failed") if failure_point == "stage_read" else None,
            return_value=None,
        )), control=Control(), ready=asyncio.Event(),
    )
    if failure_point == "owner_cancel":
        with pytest.raises(asyncio.CancelledError):
            await execution
    else:
        await execution

    runner._fail_turn.assert_not_awaited()
    assert not any(event.get("event", {}).get("type") in {"error", "cancelled"} for event in events)
    assert not any(event.get("event", {}).get("status") == "failed" for event in events)
    assert events[-1]["type"] == "done"
    if failure_point not in {"final_publish", "owner_cancel"}:
        assert any(event.get("event", {}).get("type") == "final" for event in events)
    assert all(event.get("execution_id") == str(command.execution_id) for event in events)


@pytest.mark.asyncio
async def test_runner_unsubscribe_failure_does_not_skip_terminalization(monkeypatch):
    started = asyncio.Event()
    execution_cancelled = asyncio.Event()
    events: list[dict] = []

    class Control:
        async def wait_for_cancel(self):
            await started.wait()
            await asyncio.sleep(0)

        async def unsubscribe(self):
            raise OSError("unsubscribe failed")

    class Service:
        def __init__(self, **_kwargs):
            pass

        async def send_message_stream(self, **_kwargs):
            started.set()
            try:
                yield {"type": "stage", "activity": {"stage": "planning"}}
                await asyncio.Event().wait()
            finally:
                execution_cancelled.set()

    class SessionContext:
        async def __aenter__(self):
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, *_args):
            pass

    class Repositories:
        def __init__(self, *_args):
            pass

        def get_chats_repository(self):
            return object()

        def get_chat_messages_repository(self):
            return object()

    class Turns:
        def __init__(self, _session):
            pass

        async def get_by_runtime_run_id(self, _run_id):
            return None

    class Bus:
        async def publish(self, *, stream_key, payload):
            events.append(payload)

    monkeypatch.setattr(runner_module, "ChatStreamService", Service)
    monkeypatch.setattr(runner_module, "AsyncRepositoryFactory", Repositories)
    monkeypatch.setattr(runner_module, "ChatTurnService", Turns)
    monkeypatch.setattr(runner_module, "CHAT_TURN_HEARTBEAT_SECONDS", 3600)
    runner = ChatRuntimeRunner()
    runner._event_bus = Bus()
    command = ChatRuntimeCommand(
        run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(),
        content="hello", artifact_ids=[],
    )
    await runner._run(
        command=command, llm_client=object(),
        redis_client=SimpleNamespace(set=AsyncMock(), delete=AsyncMock()),
        session_factory=SessionContext, control=Control(), ready=asyncio.Event(),
    )

    assert execution_cancelled.is_set()
    assert any(payload.get("event", {}).get("type") == "cancelled" for payload in events)
    assert any(payload.get("type") == "done" for payload in events)


@pytest.mark.asyncio
async def test_compaction_configured_capacity_skips_optional_snapshot(monkeypatch):
    pending = asyncio.create_task(asyncio.Event().wait())
    monkeypatch.setattr(orchestrator_module, "_COMPACTION_DISPATCH_TASKS", {pending})
    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: SimpleNamespace(
        CHAT_CONTEXT_COMPACTION_DISPATCH_LIMIT=1,
    ))
    context_service = SimpleNamespace(load_snapshot=AsyncMock())
    orchestrator = ChatTurnOrchestrator(
        context_service=context_service, persistence_service=AsyncMock(), turn_service=AsyncMock(),
    )
    try:
        await orchestrator._dispatch_context_compaction(
            chat_id="chat", turn_id="turn", user_id="user", tenant_id="tenant",
            recent_dialogue=[], user_message_id=None, assistant_content="answer",
            assistant_message_id=None, run_id="run", terminal_state="completed",
            expected_revision=1,
        )
        context_service.load_snapshot.assert_not_awaited()
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_compaction_origin_revision_is_frozen_before_terminal_commit(monkeypatch):
    from app.services.chat_context_contracts import ChatContextSnapshot

    turn_id = uuid4()
    head = SimpleNamespace(revision=4, updated_through_turn_id=turn_id)
    order = []

    class Repository:
        def __init__(self, _session):
            pass

        async def get_head(self, **_kwargs):
            order.append("origin_read")
            return head

    async def commit():
        order.append("commit")
        head.revision = 5

    monkeypatch.setattr(orchestrator_module, "ChatContextRepository", Repository)
    orchestrator = ChatTurnOrchestrator(
        context_service=AsyncMock(),
        persistence_service=SimpleNamespace(create_assistant_message=AsyncMock(return_value=SimpleNamespace(
            message_id="assistant", created_at="now",
        ))),
        turn_service=SimpleNamespace(
            build_request_hash=lambda _value: "hash", start_turn=AsyncMock(return_value=SimpleNamespace(id=turn_id)),
            complete_turn=AsyncMock(), session=SimpleNamespace(commit=commit),
        ),
    )
    orchestrator._dispatch_context_compaction = AsyncMock()

    async def router(**_kwargs):
        yield {"type": "final_content", "content": "Observed answer", "sources": []}

    events = [event async for event in orchestrator.execute_turn(
        chat=SimpleNamespace(), chat_id="chat", user_id="user", tenant_id="tenant", content="question",
        artifact_ids=[], attachment_meta=[], attachment_contexts=[], idempotency_key=None,
        continuation_meta=None, persist_user_message=False, run_with_router=router,
        store_idempotency=AsyncMock(), bind_attachments=AsyncMock(), preloaded_context=[],
        preloaded_context_snapshot=ChatContextSnapshot(chat_id="chat", revision=3),
    )]

    assert any(event["type"] == "final" for event in events)
    assert order == ["origin_read", "commit"]
    assert orchestrator._dispatch_context_compaction.await_args.kwargs["expected_revision"] == 4
    assert head.revision == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("revision,source_turn", [(5, "origin-turn"), (4, "newer-turn")])
async def test_detached_compaction_does_not_rebase_old_dialogue_on_new_context(monkeypatch, revision, source_turn):
    from unittest.mock import MagicMock
    import app.core.db
    from app.services.chat_context_contracts import ChatContextSnapshot
    from app.workers.tasks_memory import compact_chat_context

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            pass

    class SnapshotService:
        def __init__(self, *_args):
            pass

        async def load_snapshot(self, **_kwargs):
            return ChatContextSnapshot(chat_id="chat", revision=revision, updated_through_turn_id=source_turn)

    publish = MagicMock()
    monkeypatch.setattr(app.core.db, "get_session_factory", lambda: SessionContext)
    monkeypatch.setattr(orchestrator_module, "ChatContextService", SnapshotService)
    monkeypatch.setattr(compact_chat_context, "delay", publish)

    await orchestrator_module._prepare_and_enqueue_context_compaction(dispatch={
        "chat_id": "chat", "chat_turn_id": "origin-turn", "user_id": "user", "tenant_id": "tenant",
        "expected_revision": 4, "dialogue": [{"role": "user", "content": "Old selection"}],
        "outcome": {"terminal_state": "completed"}, "valid_source_ids": ["turn:origin-turn"],
    }, dispatch_limit=1)

    publish.assert_not_called()


@pytest.mark.asyncio
async def test_context_compaction_broker_publish_runs_off_loop_and_is_detached(monkeypatch):
    from app.services.chat_context_contracts import ChatContextSnapshot
    from app.workers.tasks_memory import compact_chat_context

    started = threading.Event()
    release = threading.Event()

    def blocking_publish(_payload):
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(compact_chat_context, "delay", blocking_publish)
    session_closed = threading.Event()

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            session_closed.set()

    class SnapshotService:
        def __init__(self, *_args):
            pass

        async def load_snapshot(self, **_kwargs):
            return ChatContextSnapshot(chat_id="chat-1", revision=4, updated_through_turn_id="turn-1")

    monkeypatch.setattr(orchestrator_module, "ChatContextService", SnapshotService)
    import app.core.db
    monkeypatch.setattr(app.core.db, "get_session_factory", lambda: SessionContext)
    orchestrator = ChatTurnOrchestrator(
        context_service=AsyncMock(),
        persistence_service=AsyncMock(),
        turn_service=AsyncMock(),
    )

    await asyncio.wait_for(orchestrator._dispatch_context_compaction(
        chat_id="chat-1", turn_id="turn-1", user_id="user-1", tenant_id="tenant-1",
        recent_dialogue=[{"role": "user", "content": "hello"}], user_message_id="message-1",
        assistant_content="answer", assistant_message_id="assistant-1", run_id="run-1",
        terminal_state="completed",
        expected_revision=4,
    ), timeout=1)
    assert await asyncio.to_thread(started.wait, 1)
    assert session_closed.is_set()
    assert any(not task.done() for task in orchestrator_module._COMPACTION_DISPATCH_TASKS)
    release.set()
    await asyncio.gather(*list(orchestrator_module._COMPACTION_DISPATCH_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_resume_waits_for_previous_owner_cleanup_before_starting_new_task(monkeypatch):
    from app.services.chat_runtime_runner import chat_run_owner_key

    old_started = asyncio.Event()
    release_old = asyncio.Event()
    resumed_started = asyncio.Event()
    observed_commands: list[ChatRuntimeCommand] = []

    class Control:
        async def subscribe(self):
            pass

        async def unsubscribe(self):
            pass

    class Redis:
        def __init__(self):
            self.values: dict[str, str] = {}

        async def set(self, key, value, **_kwargs):
            self.values[key] = value

        async def delete(self, key):
            self.values.pop(key, None)

    runner = ChatRuntimeRunner()
    monkeypatch.setattr(runner_module, "RuntimeRunControlSubscriber", lambda **_kwargs: Control())

    async def run_owner(**kwargs):
        command = kwargs["command"]
        observed_commands.append(command)
        if command.resumed_turn_id is None:
            old_started.set()
            kwargs["ready"].set()
            await release_old.wait()
            await kwargs["redis_client"].delete(chat_run_owner_key(str(command.run_id)))
        else:
            resumed_started.set()
            kwargs["ready"].set()

    monkeypatch.setattr(runner, "_run", run_owner)
    redis = Redis()
    run_id, chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4(), uuid4()
    old_command = ChatRuntimeCommand(
        run_id=run_id, chat_id=chat_id, user_id=user_id, tenant_id=tenant_id,
        content="first", artifact_ids=[],
    )
    old_task = await runner.start(
        command=old_command, llm_client=object(), redis_client=redis, session_factory=object(),
    )
    await old_started.wait()
    resume_command = ChatRuntimeCommand(
        run_id=run_id, chat_id=chat_id, user_id=user_id, tenant_id=tenant_id,
        content="answer", artifact_ids=[], resumed_turn_id=uuid4(),
    )
    resumed_start = asyncio.create_task(runner.start(
        command=resume_command, llm_client=object(), redis_client=redis, session_factory=object(),
    ))
    await asyncio.sleep(0)
    assert not resumed_started.is_set()

    release_old.set()
    resumed_task = await resumed_start
    await resumed_task

    assert old_task.done()
    assert resumed_started.is_set()
    assert observed_commands == [old_command, resume_command]
    owner = __import__("json").loads(redis.values[chat_run_owner_key(str(run_id))])
    assert owner == {"chat_id": str(chat_id), "user_id": str(user_id)}


@pytest.mark.asyncio
async def test_cancelling_resume_wait_does_not_cancel_previous_owner(monkeypatch):
    old_started = asyncio.Event()
    release_old = asyncio.Event()

    class Control:
        async def subscribe(self):
            pass

        async def unsubscribe(self):
            pass

    class Redis:
        async def set(self, *_args, **_kwargs):
            pass

    runner = ChatRuntimeRunner()
    monkeypatch.setattr(runner_module, "RuntimeRunControlSubscriber", lambda **_kwargs: Control())

    async def run_owner(**kwargs):
        old_started.set()
        kwargs["ready"].set()
        await release_old.wait()

    monkeypatch.setattr(runner, "_run", run_owner)
    run_id, chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4(), uuid4()
    old_task = await runner.start(
        command=ChatRuntimeCommand(
            run_id=run_id, chat_id=chat_id, user_id=user_id, tenant_id=tenant_id,
            content="first", artifact_ids=[],
        ),
        llm_client=object(), redis_client=Redis(), session_factory=object(),
    )
    await old_started.wait()
    resume_task = asyncio.create_task(runner.start(
        command=ChatRuntimeCommand(
            run_id=run_id, chat_id=chat_id, user_id=user_id, tenant_id=tenant_id,
            content="answer", artifact_ids=[], resumed_turn_id=uuid4(),
        ),
        llm_client=object(), redis_client=Redis(), session_factory=object(),
    ))
    await asyncio.sleep(0)
    resume_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await resume_task
    assert not old_task.cancelled()
    release_old.set()
    await old_task


@pytest.mark.asyncio
async def test_final_event_is_yielded_before_optional_compaction_snapshot(monkeypatch):
    from app.services.chat_context_contracts import ChatContextSnapshot

    context_service = SimpleNamespace(load_snapshot=AsyncMock())
    context_service.load_snapshot.side_effect = AssertionError("optional compaction must happen after final yield")
    persistence = SimpleNamespace(create_assistant_message=AsyncMock(return_value=SimpleNamespace(
        message_id="assistant-1", created_at="2026-11-18T00:00:00Z",
    )))
    turn_service = SimpleNamespace(
        build_request_hash=lambda _content: "hash",
        start_turn=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        complete_turn=AsyncMock(),
        attach_assistant_message=AsyncMock(),
        session=SimpleNamespace(commit=AsyncMock()),
    )
    orchestrator = ChatTurnOrchestrator(
        context_service=context_service, persistence_service=persistence, turn_service=turn_service,
    )

    async def run_with_router(**_kwargs):
        yield {"type": "final_content", "content": "ответ", "sources": []}

    stream = orchestrator.execute_turn(
        chat=SimpleNamespace(), chat_id="chat-1", user_id="user-1", tenant_id="tenant-1",
        content="вопрос", artifact_ids=[], attachment_meta=[], attachment_contexts=[],
        idempotency_key=None, continuation_meta=None, persist_user_message=False,
        run_with_router=run_with_router, store_idempotency=AsyncMock(), bind_attachments=AsyncMock(),
        preloaded_context=[], preloaded_context_snapshot=ChatContextSnapshot(chat_id="chat-1"),
    )

    final_event = None
    async for event in stream:
        if event.get("type") == "final":
            final_event = event
            break
    assert final_event is not None
    context_service.load_snapshot.assert_not_awaited()
    await stream.aclose()
