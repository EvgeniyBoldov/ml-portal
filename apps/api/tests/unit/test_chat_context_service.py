from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.chat_context_service import ChatContextService


@pytest.fixture
def messages_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_chat_messages = AsyncMock()
    repo.get_recent_chat_messages = AsyncMock()
    return repo


@pytest.fixture
def service(mock_session, mock_llm_client, messages_repo) -> ChatContextService:
    return ChatContextService(mock_session, mock_llm_client, messages_repo)


class TestChatContextService:
    @pytest.mark.asyncio
    async def test_load_chat_context_normalizes_text_and_json_content(self, service: ChatContextService, messages_repo: AsyncMock):
        messages_repo.get_recent_chat_messages.return_value = [
            SimpleNamespace(role="user", content={"text": "hello"}),
            SimpleNamespace(role="assistant", content={"foo": "bar"}),
        ]

        result = await service.load_chat_context(str(uuid4()), limit=2)

        assert result == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": '{"foo": "bar"}'},
        ]

    @pytest.mark.asyncio
    async def test_load_chat_context_with_summary_uses_summary_plus_recent(self, service: ChatContextService):
        service.get_latest_summary_text = AsyncMock(return_value="short summary")
        service.load_chat_context = AsyncMock(return_value=[{"role": "user", "content": "recent"}])

        result = await service.load_chat_context_with_summary(str(uuid4()), recent_limit=3)

        assert result == [
            {"role": "system", "content": "Conversation summary so far:\nshort summary"},
            {"role": "user", "content": "recent"},
        ]

    @pytest.mark.asyncio
    async def test_load_chat_context_with_summary_falls_back_to_raw_messages(self, service: ChatContextService):
        service.get_latest_summary_text = AsyncMock(return_value=None)
        service.load_chat_context = AsyncMock(side_effect=[
            [{"role": "user", "content": "ignored"}],
            [{"role": "user", "content": "fallback-1"}, {"role": "assistant", "content": "fallback-2"}],
        ])

        result = await service.load_chat_context_with_summary(str(uuid4()), recent_limit=3)

        assert result == [
            {"role": "user", "content": "fallback-1"},
            {"role": "assistant", "content": "fallback-2"},
        ]

    @pytest.mark.asyncio
    async def test_store_summary_passes_message_count_and_tenant(self, service: ChatContextService, mock_session):
        chat_id = uuid4()
        tenant_id = uuid4()
        service.load_chat_context = AsyncMock(return_value=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])

        summary_service = AsyncMock()
        summary_service.create_or_update_summary = AsyncMock()

        with patch("app.services.chat_context_service.ChatSummaryService", return_value=summary_service):
            await service.store_summary(chat_id=chat_id, summary="summary", tenant_id=tenant_id)

        summary_service.create_or_update_summary.assert_awaited_once_with(
            chat_id=chat_id,
            summary_text="summary",
            message_count=2,
            tenant_id=tenant_id,
            summary_metadata=None,
        )
