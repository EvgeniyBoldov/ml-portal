from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.chat_context_service import ChatContextService
from app.services.chat_context_contracts import ChatContextApplyReceipt


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
    async def test_snapshot_requests_bounds_per_kind_not_one_global_limit(self, service: ChatContextService) -> None:
        repository = AsyncMock()
        repository.get_head = AsyncMock(return_value=None)
        repository.active_items_by_kind = AsyncMock(return_value=[])

        with patch("app.services.chat_context_service.ChatContextRepository", return_value=repository):
            await service.load_snapshot(chat_id=str(uuid4()))

        requested = repository.active_items_by_kind.await_args.kwargs["kind_limits"]
        assert requested["scope"] == 1
        assert requested["goal"] == 1
        assert requested["recent_anchor"] == 1
        assert "limit" not in repository.active_items_by_kind.await_args.kwargs

    @pytest.mark.asyncio
    async def test_snapshot_omits_unavailable_artifact_without_mutating_context(self, service: ChatContextService) -> None:
        artifact_id = str(uuid4())
        repository = AsyncMock()
        repository.get_head = AsyncMock(return_value=None)
        repository.active_items_by_kind = AsyncMock(return_value=[SimpleNamespace(
            kind="artifact_ref", item_key=artifact_id, payload={"artifact_id": artifact_id},
        )])
        references = AsyncMock()
        references.resolve_many = AsyncMock(return_value={})

        with patch("app.services.chat_context_service.ChatContextRepository", return_value=repository), \
             patch("app.services.chat_context_service.ChatArtifactReferenceService", return_value=references):
            snapshot = await service.load_snapshot(
                chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=str(uuid4()),
            )

        assert snapshot.artifacts == []
        assert snapshot.revision == 0
        assert snapshot.uncertainties[0]["code"] == "unavailable_artifact"
        assert all("close_unavailable_artifacts" not in str(call) for call in repository.mock_calls)

    @pytest.mark.asyncio
    async def test_cancel_closes_only_the_goal_owned_by_the_cancelled_turn(self, service: ChatContextService) -> None:
        chat_id = str(uuid4())
        turn_id = str(uuid4())
        repository = AsyncMock()
        repository.get_head = AsyncMock(return_value=SimpleNamespace(revision=4))
        repository.active_items = AsyncMock(return_value=[SimpleNamespace(
            kind="open_loop", item_key="blocked:run-1", source_turn_id=turn_id,
        )])
        repository.active_item = AsyncMock(return_value=SimpleNamespace(source_turn_id=turn_id))
        reconciler = AsyncMock()
        reconciler.apply = AsyncMock(return_value=ChatContextApplyReceipt(revision=5, applied_count=2))

        with patch("app.services.chat_context_service.ChatContextRepository", return_value=repository), \
             patch("app.services.chat_context_service.ChatContextReconciler", return_value=reconciler):
            receipt = await service.cancel_turn_context(chat_id=chat_id, chat_turn_id=turn_id)

        operations = reconciler.apply.await_args.kwargs["operations"]
        assert receipt.applied_count == 2
        assert {(item.kind, item.item_key) for item in operations} == {
            ("open_loop", "blocked:run-1"), ("goal", "active_goal"),
        }
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
    async def test_load_chat_context_filters_non_conversational_roles(self, service: ChatContextService, messages_repo: AsyncMock):
        messages_repo.get_recent_chat_messages.return_value = [
            SimpleNamespace(role="system", content={"text": "runtime internal"}),
            SimpleNamespace(role="user", content={"text": "question"}),
            SimpleNamespace(role="assistant", content={"text": "answer"}),
            SimpleNamespace(role="tool", content={"text": "operation payload"}),
        ]

        result = await service.load_chat_context(str(uuid4()), limit=10)

        assert result == [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]

    @pytest.mark.asyncio
    async def test_load_chat_context_preserves_attachment_meta(self, service: ChatContextService, messages_repo: AsyncMock):
        messages_repo.get_recent_chat_messages.return_value = [
            SimpleNamespace(
                role="user",
                content={"text": "question"},
                meta={"attachments": [{"id": "att-1", "file_name": "file.txt"}]},
            ),
        ]

        result = await service.load_chat_context(str(uuid4()), limit=1)

        assert result == [
            {
                "role": "user",
                "content": "question",
                "meta": {"attachments": [{"id": "att-1", "file_name": "file.txt"}]},
            }
        ]
