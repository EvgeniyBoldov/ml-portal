from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from uuid import uuid4

from app.services.chat_turn_orchestrator import ChatTurnOrchestrator


@pytest.fixture
def orchestrator() -> ChatTurnOrchestrator:
    context_service = AsyncMock()
    persistence_service = AsyncMock()
    title_service = AsyncMock()
    turn_service = AsyncMock()
    turn_service.build_request_hash = MagicMock(return_value="request-hash")
    return ChatTurnOrchestrator(
        context_service=context_service,
        persistence_service=persistence_service,
        title_service=title_service,
        turn_service=turn_service,
    )


class TestChatTurnOrchestrator:
    @pytest.mark.asyncio
    async def test_execute_turn_emits_final_and_completed(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="New Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.complete_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.persistence_service.create_assistant_message = AsyncMock(return_value=SimpleNamespace(message_id="assistant-1", created_at="2026-01-01T12:00:01Z"))
        orchestrator.context_service.load_chat_context_with_summary = AsyncMock(return_value=[])
        orchestrator.title_service.generate_chat_title = AsyncMock(return_value=None)

        async def fake_run_with_router(**kwargs):
            yield {"type": "delta", "content": "Hello"}
            yield {"type": "final_content", "content": "Hello", "sources": []}

        store_idempotency = AsyncMock()
        bind_attachments = AsyncMock()
        process_generated_files = AsyncMock(return_value={"content": "Hello", "attachments": []})

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                attachment_ids=[],
                attachment_meta=[],
                attachment_prompt_context="",
                idempotency_key="idem-1",
                model=None,
                agent_slug=None,
                continuation_meta=None,
                run_with_router=fake_run_with_router,
                store_idempotency=store_idempotency,
                bind_attachments=bind_attachments,
                process_generated_files=process_generated_files,
            )
        ]

        event_types = [event["type"] for event in events]
        assert "final" in event_types
        assert event_types[-1] == "status"
        assert events[-1]["stage"] == "completed"
        store_idempotency.assert_awaited_once_with("idem-1", "user-1", "assistant-1")
        orchestrator.turn_service.attach_user_message.assert_awaited_once()
        orchestrator.turn_service.complete_turn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_turn_emits_empty_response_error_when_runtime_returns_nothing(self, orchestrator: ChatTurnOrchestrator):
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.fail_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.context_service.load_chat_context_with_summary = AsyncMock(return_value=[{"role": "user", "content": "prev"}])

        async def fake_run_with_router(**kwargs):
            if False:
                yield {}

        bind_attachments = AsyncMock()
        process_generated_files = AsyncMock(return_value={"content": "", "attachments": []})

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                attachment_ids=[],
                attachment_meta=[],
                attachment_prompt_context="",
                idempotency_key=None,
                model=None,
                agent_slug=None,
                continuation_meta=None,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=bind_attachments,
                process_generated_files=process_generated_files,
            )
        ]

        errors = [event for event in events if event["type"] == "error"]
        assert len(errors) == 1
        assert errors[0]["error"] == "Empty response from agent"
        orchestrator.turn_service.fail_turn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_turn_persists_pause_state_when_runtime_pauses(self, orchestrator: ChatTurnOrchestrator):
        turn_id = uuid4()
        chat = SimpleNamespace(tenant_id="00000000-0000-0000-0000-000000000001", name="Chat")
        orchestrator.turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id=turn_id))
        orchestrator.turn_service.attach_user_message = AsyncMock()
        orchestrator.turn_service.pause_turn = AsyncMock()
        orchestrator.persistence_service.create_user_message = AsyncMock(return_value=SimpleNamespace(message_id="user-1", created_at="2026-01-01T12:00:00Z"))
        orchestrator.context_service.load_chat_context_with_summary = AsyncMock(return_value=[])
        orchestrator.title_service.generate_chat_title = AsyncMock(return_value=None)

        async def fake_run_with_router(**kwargs):
            yield {"type": "run_paused", "reason": "waiting_input", "run_id": "00000000-0000-0000-0000-000000000040"}

        bind_attachments = AsyncMock()
        process_generated_files = AsyncMock(return_value={"content": "", "attachments": []})

        events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id="chat-1",
                user_id="user-1",
                content="hello",
                attachment_ids=[],
                attachment_meta=[],
                attachment_prompt_context="",
                idempotency_key=None,
                model=None,
                agent_slug=None,
                continuation_meta=None,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=bind_attachments,
                process_generated_files=process_generated_files,
            )
        ]

        assert all(event["type"] != "final" for event in events)
        orchestrator.turn_service.pause_turn.assert_awaited_once_with(
            turn_id,
            pause_status="waiting_input",
            agent_run_id="00000000-0000-0000-0000-000000000040",
            paused_action=None,
            paused_context=None,
        )
