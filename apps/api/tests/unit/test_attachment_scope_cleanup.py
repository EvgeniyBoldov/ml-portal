from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chat_attachment_service import ChatAttachmentService
from app.services.chats_service import ChatsService
from app.services.sandbox_service import SandboxService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


@pytest.mark.asyncio
async def test_delete_chat_allows_internal_when_flag_is_set(monkeypatch):
    session = AsyncMock()
    chat_id = uuid4()
    owner_id = uuid4()
    chat = SimpleNamespace(id=chat_id, owner_id=owner_id, name=f"__sandbox_uploads__:{uuid4()}")
    attachment = SimpleNamespace(
        id=uuid4(),
        storage_bucket="chat-bucket",
        storage_key=f"chats/{chat_id}/attachments/1/file.txt",
    )

    session.execute = AsyncMock(side_effect=[_ScalarResult(chat), _ScalarResult([attachment])])
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    delete_folder = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.chats_service.s3_manager.delete_folder", delete_folder)

    svc = ChatsService(session)
    ok = await svc.delete_chat(chat_id=chat_id, owner_id=owner_id, allow_internal=True)

    assert ok is True
    delete_folder.assert_awaited_once_with("chat-bucket", f"chats/{chat_id}/")
    session.delete.assert_awaited_once_with(chat)


@pytest.mark.asyncio
async def test_sandbox_delete_session_removes_hidden_upload_chat(monkeypatch):
    session_id = uuid4()
    owner_id = uuid4()
    sandbox_session = SimpleNamespace(id=session_id, owner_id=owner_id)
    hidden_chat = SimpleNamespace(id=uuid4(), owner_id=owner_id, name=f"__sandbox_uploads__:{session_id}")

    session = AsyncMock()
    delete_hidden_chat = AsyncMock(return_value=True)
    delete_session_row = AsyncMock()

    monkeypatch.setattr(
        "app.services.sandbox_service.ChatsService",
        lambda _session: SimpleNamespace(delete_chat=delete_hidden_chat),
    )

    svc = SandboxService(session)
    svc.sessions.get_by_id = AsyncMock(return_value=sandbox_session)
    svc.sessions.delete = delete_session_row
    session.execute = AsyncMock(return_value=_ScalarResult(hidden_chat))

    ok = await svc.delete_session(session_id)

    assert ok is True
    delete_hidden_chat.assert_awaited_once_with(
        chat_id=hidden_chat.id,
        owner_id=owner_id,
        allow_internal=True,
    )
    delete_session_row.assert_awaited_once_with(sandbox_session)


@pytest.mark.asyncio
async def test_cleanup_expired_detached_attachments_deletes_s3_and_rows(monkeypatch):
    session = AsyncMock()
    older_than = datetime.now(timezone.utc) - timedelta(hours=24)
    row = SimpleNamespace(
        id=uuid4(),
        storage_bucket="chat-bucket",
        storage_key="artifacts/generated/user/file.txt",
    )

    service = ChatAttachmentService(session)
    service._fetch_rows = AsyncMock(return_value=[row])
    session.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    session.flush = AsyncMock()

    delete_object = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.chat_attachment_service.s3_manager.delete_object", delete_object)

    deleted = await service.cleanup_expired_detached_attachments(older_than=older_than)

    assert deleted == 1
    delete_object.assert_awaited_once_with("chat-bucket", "artifacts/generated/user/file.txt")
    session.flush.assert_awaited_once()
