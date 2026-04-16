from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_stream_service import ChatStreamService


@pytest.fixture
def chats_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_chat_by_id = AsyncMock(return_value=SimpleNamespace(id="00000000-0000-0000-0000-000000000010", tenant_id="00000000-0000-0000-0000-000000000001", name="New Chat", owner_id="00000000-0000-0000-0000-000000000020"))
    return repo


@pytest.fixture
def messages_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_message = AsyncMock(side_effect=[
        SimpleNamespace(id="user-msg-1", created_at=None),
        SimpleNamespace(id="assistant-msg-1", created_at=None),
    ])
    repo.get_chat_messages = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_session, mock_redis, mock_llm_client, chats_repo, messages_repo) -> ChatStreamService:
    with patch("app.services.chat_stream_service.AgentRuntime"), patch("app.services.chat_stream_service.RunStore"):
        svc = ChatStreamService(
            session=mock_session,
            redis=mock_redis,
            llm_client=mock_llm_client,
            chats_repo=chats_repo,
            messages_repo=messages_repo,
        )
    return svc


class TestChatStreamServiceInvariants:
    @pytest.mark.asyncio
    async def test_cached_short_circuit_returns_single_cached_event(self, service: ChatStreamService):
        service.verify_chat_access = AsyncMock(return_value=True)
        service.check_turn_idempotency = AsyncMock(return_value=None)
        service.check_idempotency = AsyncMock(return_value={
            "user_message_id": "user-msg-1",
            "assistant_message_id": "assistant-msg-1",
        })

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                idempotency_key="idem-1",
            )
        ]

        assert events == [{
            "type": "cached",
            "user_message_id": "user-msg-1",
            "assistant_message_id": "assistant-msg-1",
        }]

    @pytest.mark.asyncio
    async def test_turn_idempotency_processing_returns_single_error(self, service: ChatStreamService):
        service.check_turn_idempotency = AsyncMock(return_value={"state": "processing"})

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                idempotency_key="idem-1",
            )
        ]

        assert events == [{"type": "error", "error": "Request with this idempotency key is already in progress"}]

    @pytest.mark.asyncio
    async def test_turn_idempotency_completed_returns_cached_event(self, service: ChatStreamService):
        service.check_turn_idempotency = AsyncMock(return_value={
            "state": "completed",
            "user_message_id": "user-msg-1",
            "assistant_message_id": "assistant-msg-1",
        })

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                idempotency_key="idem-1",
            )
        ]

        assert events == [{
            "type": "cached",
            "user_message_id": "user-msg-1",
            "assistant_message_id": "assistant-msg-1",
        }]

    @pytest.mark.asyncio
    async def test_turn_idempotency_conflict_returns_single_error(self, service: ChatStreamService):
        service.check_turn_idempotency = AsyncMock(return_value={"state": "conflict"})

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="different payload",
                idempotency_key="idem-1",
            )
        ]

        assert events == [{
            "type": "error",
            "error": "Idempotency key was already used with different request payload",
        }]

    @pytest.mark.asyncio
    async def test_final_flow_emits_single_final_without_error(self, service: ChatStreamService):
        service.verify_chat_access = AsyncMock(return_value=True)
        service.check_turn_idempotency = AsyncMock(return_value=None)
        service.check_idempotency = AsyncMock(return_value=None)
        service.context_service.load_chat_context_with_summary = AsyncMock(return_value=[])
        service.title_service.generate_chat_title = AsyncMock(return_value=None)
        service.chat_turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id="00000000-0000-0000-0000-000000000030"))
        service.chat_turn_service.attach_user_message = AsyncMock()
        service.chat_turn_service.complete_turn = AsyncMock()
        service.context_service.generate_and_store_summary = AsyncMock(return_value=None)
        service.agent_service.resolve_active_version = AsyncMock(return_value=SimpleNamespace(agent_id="agent-1", version=1))
        service.agent_service.agent_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(slug="rag-search"))

        async def fake_run_with_router(**kwargs):
            yield {"type": "delta", "content": "Hello"}
            yield {"type": "final_content", "content": "Hello", "sources": []}

        service._run_with_router = fake_run_with_router

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
                idempotency_key=None,
                model=None,
                agent_slug=None,
            )
        ]

        event_types = [event["type"] for event in events]
        assert event_types.count("final") == 1
        assert event_types.count("error") == 0
        assert event_types[-1] == "status"
        assert events[-1]["stage"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_response_emits_single_error(self, service: ChatStreamService):
        service.verify_chat_access = AsyncMock(return_value=True)
        service.check_turn_idempotency = AsyncMock(return_value=None)
        service.check_idempotency = AsyncMock(return_value=None)
        service.context_service.load_chat_context_with_summary = AsyncMock(return_value=[])
        service.title_service.generate_chat_title = AsyncMock(return_value=None)
        service.chat_turn_service.start_turn = AsyncMock(return_value=SimpleNamespace(id="00000000-0000-0000-0000-000000000030"))
        service.chat_turn_service.attach_user_message = AsyncMock()
        service.chat_turn_service.fail_turn = AsyncMock()
        service.agent_service.resolve_active_version = AsyncMock(return_value=SimpleNamespace(agent_id="agent-1", version=1))
        service.agent_service.agent_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(slug="rag-search"))

        async def fake_run_with_router(**kwargs):
            if False:
                yield {}

        service._run_with_router = fake_run_with_router

        events = [
            event
            async for event in service.send_message_stream(
                chat_id="00000000-0000-0000-0000-000000000010",
                user_id="00000000-0000-0000-0000-000000000020",
                content="hello",
            )
        ]

        errors = [event for event in events if event["type"] == "error"]
        assert len(errors) == 1
        assert errors[0]["error"] == "Empty response from agent"
