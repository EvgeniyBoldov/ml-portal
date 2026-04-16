from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chat_title_service import ChatTitleService


@pytest.fixture
def chats_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_chat_by_id = AsyncMock(return_value=SimpleNamespace(name="New Chat"))
    return repo


@pytest.fixture
def service(mock_session, mock_llm_client, chats_repo) -> ChatTitleService:
    return ChatTitleService(mock_session, mock_llm_client, chats_repo)


class TestChatTitleService:
    @pytest.mark.asyncio
    async def test_generate_chat_title_persists_trimmed_title(self, service: ChatTitleService, mock_llm_client, chats_repo, mock_session):
        mock_llm_client.chat = AsyncMock(return_value={"content": '  "My Title"  '})

        result = await service.generate_chat_title("chat-1", "hello")

        assert result == "My Title"
        assert chats_repo.get_chat_by_id.return_value.name == "My Title"
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_chat_title_returns_none_for_too_short_title(self, service: ChatTitleService, mock_llm_client, mock_session):
        mock_llm_client.chat = AsyncMock(return_value={"content": 'ok'})

        result = await service.generate_chat_title("chat-1", "hello")

        assert result is None
        mock_session.flush.assert_not_awaited()
        mock_session.commit.assert_not_awaited()
