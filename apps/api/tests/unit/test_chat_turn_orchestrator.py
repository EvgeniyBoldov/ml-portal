from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
import pytest
from uuid import uuid4

from app.services.chat_turn_orchestrator import ChatTurnOrchestrator


@pytest.fixture
def orchestrator() -> ChatTurnOrchestrator:
    context_service = AsyncMock()
    persistence_service = AsyncMock()
    turn_service = AsyncMock()
    turn_service.build_request_hash = MagicMock(return_value="request-hash")
    turn_service.attach_assistant_message = AsyncMock()
    return ChatTurnOrchestrator(
        context_service=context_service,
        persistence_service=persistence_service,
        turn_service=turn_service,
    )


class TestChatTurnOrchestrator:
    @pytest.mark.asyncio
    async def test_execute_turn_reuses_resumed_turn_instead_of_creating_duplicate(self, orchestrator: ChatTurnOrchestrator):
        turn_id = uuid4()
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock()
        orchestrator.turn_service.complete_turn = AsyncMock()
        orchestrator.persistence_service.create_assistant_message = AsyncMock(
            return_value=SimpleNamespace(message_id="assistant-1", created_at="2026-01-01T12:00:01Z")
        )
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            assert kwargs["runtime_run_id"] == "00000000-0000-0000-0000-000000000040"
            yield {"type": "final_content", "content": "Продолжаю", "sources": []}

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="Уточнение пользователя",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta={"resumed_from_run_id": "00000000-0000-0000-0000-000000000040"},
                resumed_turn_id=str(turn_id),
                persist_user_message=False,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=AsyncMock(),
            )
        ]

        assert any(event["type"] == "final" for event in events)
        orchestrator.turn_service.start_turn.assert_not_awaited()
        orchestrator.turn_service.complete_turn.assert_awaited_once_with(turn_id, assistant_message_id="assistant-1")

    @pytest.mark.asyncio
    async def test_execute_turn_skips_user_message_persistence_for_resume_flow(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.complete_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock()
        orchestrator.persistence_service.create_assistant_message = AsyncMock(
            return_value=SimpleNamespace(message_id="assistant-1", created_at="2026-01-01T12:00:01Z")
        )
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            yield {"type": "final_content", "content": "Продолжаю", "sources": []}

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="Подтверждаю.",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta={"resume_checkpoint": {"resume_action": "confirm"}},
                persist_user_message=False,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=AsyncMock(),
            )
        ]

        assert all(event["type"] != "user_message" for event in events)
        orchestrator.persistence_service.create_user_message.assert_not_awaited()
        orchestrator.turn_service.attach_user_message.assert_not_awaited()
        orchestrator.persistence_service.create_assistant_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_during_pre_runtime_setup_cancels_persisted_turn(self, orchestrator: ChatTurnOrchestrator):
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.cancel_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(
            return_value=SimpleNamespace(message_id="user-1", created_at="now")
        )
        stream = orchestrator.execute_turn(
            chat=SimpleNamespace(), chat_id="chat-1", user_id="user-1", content="hello",
            artifact_ids=[], attachment_meta=[], attachment_contexts=[], idempotency_key="idem",
            continuation_meta=None, persist_user_message=True, run_with_router=AsyncMock(),
            store_idempotency=AsyncMock(), bind_attachments=AsyncMock(),
        )
        while (await anext(stream))["type"] != "user_message":
            pass
        await stream.aclose()
        orchestrator.turn_service.cancel_turn.assert_awaited_once()
        orchestrator.turn_service.fail_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_turn_emits_final_and_completed(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="New Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.complete_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.persistence_service.create_assistant_message = AsyncMock(return_value=SimpleNamespace(message_id="assistant-1", created_at="2026-01-01T12:00:01Z"))
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            yield {"type": "delta", "content": "Hello"}
            yield {
                "type": "final_content",
                "content": "Hello",
                "sources": [{"source_name": "Doc"}],
                "attachments": [{"artifact_id": "artifact-1", "file_name": "report.txt"}],
            }

        store_idempotency = AsyncMock()
        bind_attachments = AsyncMock()
        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key="idem-1",
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=store_idempotency,
                bind_attachments=bind_attachments,
            )
        ]

        event_types = [event["type"] for event in events]
        assert "final" in event_types
        assert event_types[-1] == "final"
        state_event = next(event for event in events if event.get("type") == "state")
        assert state_event["status"] == "completed"
        assert any(event.get("activity", {}).get("stage") == "finalizing" for event in events if event.get("type") == "stage")
        final_event = next(event for event in events if event["type"] == "final")
        assert final_event["attachments"][0]["artifact_id"] == "artifact-1"
        store_idempotency.assert_awaited_once_with(
            "idem-1", "user-1", "assistant-1", chat_id="chat-1", user_id="user-1",
            request_hash="request-hash",
        )
        orchestrator.turn_service.attach_user_message.assert_awaited_once()
        orchestrator.turn_service.complete_turn.assert_awaited_once()
        orchestrator.persistence_service.create_assistant_message.assert_awaited_once_with(
            chat_id="chat-1",
            content="Hello",
            rag_sources=[{"source_name": "Doc"}],
            attachments=[{"artifact_id": "artifact-1", "file_name": "report.txt"}],
            extra_meta=None,
        )

    @pytest.mark.asyncio
    async def test_execute_turn_emits_empty_response_error_when_runtime_returns_nothing(self, orchestrator: ChatTurnOrchestrator, caplog):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.fail_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[{"role": "user", "content": "prev"}])

        async def fake_run_with_router(**kwargs):
            if False:
                yield {}

        bind_attachments = AsyncMock()
        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=bind_attachments,
            )
        ]

        errors = [event for event in events if event["type"] == "error"]
        assert len(errors) == 1
        assert errors[0]["error"] == "Empty response from agent"
        diagnostic = next(record for record in caplog.records if record.message == "chat_turn_empty_agent_response")
        assert diagnostic.chat_id == "00000000-0000-0000-0000-000000000010"
        assert diagnostic.runtime_event_types == []
        orchestrator.turn_service.fail_turn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_turn_persists_pause_state_when_runtime_pauses(self, orchestrator: ChatTurnOrchestrator):
        turn_id = uuid4()
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=turn_id))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.pause_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            yield {"type": "run_paused", "reason": "waiting_input", "run_id": "00000000-0000-0000-0000-000000000040"}

        bind_attachments = AsyncMock()
        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=bind_attachments,
            )
        ]

        assert all(event["type"] != "final" for event in events)
        orchestrator.turn_service.pause_turn.assert_awaited_once_with(
            turn_id,
            pause_status="waiting_input",
            runtime_run_id="00000000-0000-0000-0000-000000000040",
            paused_action={"pause_id": ANY},
            paused_context={"pause_id": ANY},
        )
        # The request/turn is committed before the long-running stream, then
        # the pause checkpoint is committed before its resumable SSE frame.
        assert orchestrator.turn_service.session.commit.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_execute_turn_persists_failed_assistant_message_on_runtime_error(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.fail_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.persistence_service.create_assistant_message = AsyncMock(return_value=SimpleNamespace(message_id="assistant-failed-1", created_at="2026-01-01T12:00:01Z"))
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            yield {"type": "error", "error": "budget exceeded in planner", "code": "planner_failed", "run_id": "11111111-1111-1111-1111-111111111111"}

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=AsyncMock(),
            )
        ]

        assert any(event["type"] == "error" for event in events)
        orchestrator.persistence_service.create_assistant_message.assert_awaited_once()
        kwargs = orchestrator.persistence_service.create_assistant_message.await_args.kwargs
        assert kwargs["content"]
        assert "traceback" not in kwargs["content"].lower()
        assert kwargs["extra_meta"]["runtime_status"] == "failed"
        assert kwargs["extra_meta"]["runtime_run_id"] == "11111111-1111-1111-1111-111111111111"

    @pytest.mark.asyncio
    async def test_execute_turn_stops_completed_path_after_terminal_error(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        turn_id = uuid4()
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=turn_id))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.complete_turn = AsyncMock()
        orchestrator.turn_service.fail_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(
            return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z")
        )
        orchestrator.persistence_service.create_assistant_message = AsyncMock(
            return_value=SimpleNamespace(message_id="assistant-failed-1", created_at="2026-01-01T12:00:01Z")
        )
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        # Runtime emits terminal error first; orchestrator must not go through normal final/completed path.
        async def fake_run_with_router(**kwargs):
            yield {"type": "error", "error": "budget exhausted", "code": "budget_exceeded", "run_id": "run-1"}
            yield {"type": "final_content", "content": "late-content", "sources": []}

        store_idempotency = AsyncMock()
        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key="idem-1",
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=store_idempotency,
                bind_attachments=AsyncMock(),
            )
        ]

        event_types = [event["type"] for event in events]
        assert "final" not in event_types
        assert not any(event.get("status") == "completed" for event in events if event.get("type") == "state")
        orchestrator.turn_service.complete_turn.assert_not_awaited()
        store_idempotency.assert_not_awaited()
        orchestrator.turn_service.fail_turn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_turn_persists_sanitized_budget_failure_message(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.attach_assistant_message = AsyncMock()
        orchestrator.turn_service.fail_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(
            return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z")
        )
        orchestrator.persistence_service.create_assistant_message = AsyncMock(
            return_value=SimpleNamespace(message_id="assistant-failed-1", created_at="2026-01-01T12:00:01Z")
        )
        orchestrator.context_service.load_chat_context = AsyncMock(return_value=[])

        async def fake_run_with_router(**kwargs):
            yield {
                "type": "error",
                "error": "Traceback: budget_policy max_steps exceeded with internal stack",
                "code": "budget_exceeded",
                "run_id": "11111111-1111-1111-1111-111111111111",
            }

        _ = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                artifact_ids=[],
                attachment_meta=[],
                attachment_contexts=[],
                idempotency_key=None,
                continuation_meta=None,
                persist_user_message=True,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=AsyncMock(),
            )
        ]

        kwargs = orchestrator.persistence_service.create_assistant_message.await_args.kwargs
        assert kwargs["content"] == "Достигнут лимит выполнения запроса. Попробуйте сузить запрос."
        assert "traceback" not in kwargs["content"].lower()
        assert kwargs["extra_meta"]["runtime_status"] == "failed"
        assert kwargs["extra_meta"]["runtime_error_code"] == "budget_exceeded"


@pytest.mark.asyncio
async def test_partial_final_preserves_failed_turn_and_answer(orchestrator):
    turn_id = uuid4()
    orchestrator.turn_service.start_turn.return_value = SimpleNamespace(id=turn_id)
    orchestrator.persistence_service.create_assistant_message.return_value = SimpleNamespace(
        message_id="partial-answer", created_at="2026-01-01T12:00:01Z")
    orchestrator.context_service.load_chat_context.return_value = []

    async def run(**kwargs):
        yield {"type": "final_content", "content": "Получена только часть данных.",
               "sources": [], "stop_reason": "failed"}

    events = [event async for event in orchestrator.execute_turn(
        chat=SimpleNamespace(tenant_id=None, name="Chat"), chat_id="chat-1", user_id="user-1",
        content="hello", artifact_ids=[], attachment_meta=[], attachment_contexts=[],
        idempotency_key=None, continuation_meta=None,
        persist_user_message=False, run_with_router=run, store_idempotency=AsyncMock(),
        bind_attachments=AsyncMock())]

    orchestrator.turn_service.complete_turn.assert_not_awaited()
    orchestrator.turn_service.attach_assistant_message.assert_awaited_once_with(turn_id, "partial-answer")
    orchestrator.turn_service.fail_turn.assert_awaited_once_with(turn_id, error_message="runtime_execution_failed")
    meta = orchestrator.persistence_service.create_assistant_message.await_args.kwargs["extra_meta"]
    assert meta["runtime_status"] == "failed"
    final = next(event for event in events if event["type"] == "final")
    assert final["content"] == "Получена только часть данных."
    assert final["stop_reason"] == "failed"
    state_event = next(event for event in events if event.get("type") == "state")
    assert state_event["status"] == "failed"
    assert events[-1]["type"] == "final"
    assert not any(event["type"] == "error" for event in events)


@pytest.mark.asyncio
async def test_finalization_failure_rolls_back_and_never_emits_final(orchestrator):
    turn_id = uuid4()
    orchestrator.context_service.load_chat_context.return_value = []
    orchestrator.persistence_service.create_assistant_message.side_effect = RuntimeError("PRIVATE_WRITE_ERROR")

    async def response(**kwargs):
        yield {"type": "final_content", "content": "Prepared answer", "attachments": []}

    events = [event async for event in orchestrator.execute_turn(
        chat=SimpleNamespace(name="Test"), chat_id=str(uuid4()), user_id=str(uuid4()), tenant_id=str(uuid4()),
        content="test", artifact_ids=[], attachment_meta=[], attachment_contexts=[], idempotency_key=None,
        continuation_meta={}, persist_user_message=False,
        resumed_turn_id=str(turn_id), run_with_router=response, store_idempotency=AsyncMock(), bind_attachments=AsyncMock())]
    assert not any(event["type"] == "final" for event in events)
    assert any(event.get("code") == "chat_finalization_failed" for event in events)
    assert "PRIVATE_WRITE_ERROR" not in str(events)
    orchestrator.turn_service.session.rollback.assert_awaited_once()
    orchestrator.turn_service.fail_turn.assert_awaited_once_with(turn_id, error_message="chat_finalization_failed")
