from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    repo.get_recent_chat_messages = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_session, mock_redis, mock_llm_client, chats_repo, messages_repo) -> ChatStreamService:
    svc = ChatStreamService(
        session=mock_session,
        redis=mock_redis,
        llm_client=mock_llm_client,
        chats_repo=chats_repo,
        messages_repo=messages_repo,
    )
    svc.attachment_service.build_runtime_attachment_contexts = AsyncMock(return_value=[])
    svc.attachment_service.build_runtime_attachment_contexts_from_meta = AsyncMock(return_value=[])
    return svc


class TestChatStreamServiceInvariants:
    def test_idempotency_cache_key_is_scoped_to_chat_and_user(self, service: ChatStreamService):
        first = service._scoped_idempotency_key(
            idempotency_key="same", chat_id="chat-a", user_id="user-a",
        )
        assert first != service._scoped_idempotency_key(
            idempotency_key="same", chat_id="chat-b", user_id="user-a",
        )
        assert first != service._scoped_idempotency_key(
            idempotency_key="same", chat_id="chat-a", user_id="user-b",
        )

    def test_extract_attachment_meta_from_messages_collects_history_refs(self, service: ChatStreamService):
        messages = [
            {"role": "user", "content": "first", "meta": {"attachments": [{"id": "att-1"}, {"id": "att-2"}]}},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third", "meta": {"attachments": [{"id": "att-3"}]}},
        ]

        assert service._extract_attachment_meta_from_messages(messages) == [
            {"id": "att-1"},
            {"id": "att-2"},
            {"id": "att-3"},
        ]


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

        assert events == [{
            "type": "error",
            "error": "Request with this idempotency key is already in progress",
            "code": "idempotency_processing",
        }]

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
            "code": "idempotency_conflict",
        }]

