from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.file_generate import FileGenerateTool
from app.agents.context import ToolContext


@pytest.mark.asyncio
async def test_file_generate_commits_created_attachment(monkeypatch):
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    attachment_payload = {
        "id": str(uuid4()),
        "file_id": f"chatatt_{uuid4()}",
        "storage_uri": "s3://chat-bucket/chats/example/generated/example.txt",
        "file_name": "example.txt",
        "size_bytes": 5,
    }
    create_generated_attachment = AsyncMock(return_value=attachment_payload)

    service_instance = SimpleNamespace(create_generated_attachment=create_generated_attachment)

    monkeypatch.setattr(
        "app.core.db.get_session_factory",
        lambda: _SessionManager,
    )
    monkeypatch.setattr(
        "app.services.chat_attachment_service.ChatAttachmentService",
        lambda _session: service_instance,
    )

    tool = FileGenerateTool()
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
    )

    result = await tool.v1_0_0(
        ctx,
        {
            "filename": "example.txt",
            "content": "hello",
            "format": "txt",
        },
    )

    assert result.success is True
    assert result.data["storage_uri"] == "s3://chat-bucket/chats/example/generated/example.txt"
    create_generated_attachment.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_file_generate_allows_detached_artifact_without_chat(monkeypatch):
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    attachment_payload = {
        "id": str(uuid4()),
        "file_id": f"chatatt_{uuid4()}",
        "storage_uri": "s3://chat-bucket/artifacts/generated/user/example.txt",
        "file_name": "example.txt",
        "size_bytes": 5,
    }
    create_generated_attachment = AsyncMock(return_value=attachment_payload)

    service_instance = SimpleNamespace(create_generated_attachment=create_generated_attachment)

    monkeypatch.setattr("app.core.db.get_session_factory", lambda: _SessionManager)
    monkeypatch.setattr(
        "app.services.chat_attachment_service.ChatAttachmentService",
        lambda _session: service_instance,
    )

    tool = FileGenerateTool()
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=None,
    )

    result = await tool.v1_0_0(
        ctx,
        {
            "filename": "example.txt",
            "content": "hello",
            "format": "txt",
        },
    )

    assert result.success is True
    create_generated_attachment.assert_awaited_once()
    assert create_generated_attachment.await_args.kwargs["chat_id"] is None
    session.commit.assert_awaited_once()
