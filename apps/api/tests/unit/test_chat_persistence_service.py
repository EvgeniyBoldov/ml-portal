from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chat_persistence_service import ChatPersistenceService


@pytest.fixture
def messages_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_message = AsyncMock()
    return repo


@pytest.fixture
def service(mock_session, messages_repo) -> ChatPersistenceService:
    return ChatPersistenceService(mock_session, messages_repo)


class TestChatPersistenceService:
    @pytest.mark.asyncio
    async def test_create_user_message_returns_normalized_payload(self, service: ChatPersistenceService, messages_repo: AsyncMock, mock_session):
        created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        messages_repo.create_message.return_value = SimpleNamespace(id="msg-1", created_at=created_at)

        result = await service.create_user_message("chat-1", "hello")

        assert result.message_id == "msg-1"
        assert result.created_at == "2026-01-01T12:00:00Z"
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_assistant_message_includes_rag_sources_in_meta(self, service: ChatPersistenceService, messages_repo: AsyncMock):
        created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        messages_repo.create_message.return_value = SimpleNamespace(id="msg-2", created_at=created_at)

        result = await service.create_assistant_message("chat-1", "answer", rag_sources=[{"id": "src-1"}])

        assert result.message_id == "msg-2"
        messages_repo.create_message.assert_awaited_once_with(
            chat_id="chat-1",
            role="assistant",
            content={"text": "answer"},
            meta={"rag_sources": [{"id": "src-1"}]},
        )
