from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chats_service import ChatsService


class _ChatResult:
    def __init__(self, chat):
        self._chat = chat

    def scalar_one_or_none(self):
        return self._chat


class _AttachmentsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_delete_chat_uses_folder_cleanup(monkeypatch):
    session = AsyncMock()
    chat_id = uuid4()
    owner_id = uuid4()
    chat = SimpleNamespace(id=chat_id, owner_id=owner_id)
    attachment = SimpleNamespace(
        id=uuid4(),
        storage_bucket="chat-bucket",
        storage_key=f"chats/{chat_id}/attachments/1/file.txt",
    )

    session.execute = AsyncMock(side_effect=[_ChatResult(chat), _AttachmentsResult([attachment])])
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    delete_folder = AsyncMock(return_value=True)
    delete_object = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.chats_service.s3_manager.delete_folder", delete_folder)
    monkeypatch.setattr("app.services.chats_service.s3_manager.delete_object", delete_object)

    svc = ChatsService(session)
    ok = await svc.delete_chat(chat_id=chat_id, owner_id=owner_id)

    assert ok is True
    delete_folder.assert_awaited_once_with("chat-bucket", f"chats/{chat_id}/")
    delete_object.assert_not_awaited()
    session.delete.assert_awaited_once_with(chat)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_chat_falls_back_to_object_cleanup(monkeypatch):
    session = AsyncMock()
    chat_id = uuid4()
    owner_id = uuid4()
    chat = SimpleNamespace(id=chat_id, owner_id=owner_id)
    attachment = SimpleNamespace(
        id=uuid4(),
        storage_bucket="chat-bucket",
        storage_key=f"chats/{chat_id}/attachments/1/file.txt",
    )

    session.execute = AsyncMock(side_effect=[_ChatResult(chat), _AttachmentsResult([attachment])])
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    delete_folder = AsyncMock(side_effect=RuntimeError("boom"))
    delete_object = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.chats_service.s3_manager.delete_folder", delete_folder)
    monkeypatch.setattr("app.services.chats_service.s3_manager.delete_object", delete_object)

    svc = ChatsService(session)
    ok = await svc.delete_chat(chat_id=chat_id, owner_id=owner_id)

    assert ok is True
    delete_folder.assert_awaited_once()
    delete_object.assert_awaited_once_with("chat-bucket", attachment.storage_key)
    session.delete.assert_awaited_once_with(chat)
    session.flush.assert_awaited_once()
