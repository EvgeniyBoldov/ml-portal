from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.builtins.file_delete import FileDeleteTool
from app.agents.context import ToolContext


def _session_manager(session: AsyncMock):
    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return _SessionManager


def _context():
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())


@pytest.mark.asyncio
async def test_file_delete_commits_after_s3_and_db_delete(monkeypatch):
    attachment_id = uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        file_name="report.txt",
        storage_bucket="chat-bucket",
        storage_key="chat/report.txt",
    )
    session.execute.return_value = result
    delete_object = AsyncMock(return_value=True)

    monkeypatch.setattr(
        "app.agents.builtins.file_delete.get_session_factory",
        lambda: _session_manager(session),
    )
    monkeypatch.setattr("app.agents.builtins.file_delete.s3_manager.delete_object", delete_object)

    result = await FileDeleteTool().v1_0_0(
        _context(),
        {"file_id": f"chatatt_{attachment_id}"},
    )

    assert result.success is True
    session.delete.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    delete_object.assert_awaited_once_with("chat-bucket", "chat/report.txt")


@pytest.mark.asyncio
async def test_file_delete_removes_db_row_when_s3_reports_missing(monkeypatch):
    attachment_id = uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        file_name="missing.txt",
        storage_bucket="chat-bucket",
        storage_key="chat/missing.txt",
    )
    session.execute.return_value = result

    monkeypatch.setattr(
        "app.agents.builtins.file_delete.get_session_factory",
        lambda: _session_manager(session),
    )
    monkeypatch.setattr(
        "app.agents.builtins.file_delete.s3_manager.delete_object",
        AsyncMock(return_value=False),
    )

    result = await FileDeleteTool().v1_0_0(
        _context(),
        {"file_id": f"chatatt_{attachment_id}"},
    )

    assert result.success is True
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_file_delete_rejects_missing_attachment_without_commit(monkeypatch):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    monkeypatch.setattr(
        "app.agents.builtins.file_delete.get_session_factory",
        lambda: _session_manager(session),
    )

    result = await FileDeleteTool().v1_0_0(
        _context(),
        {"file_id": f"chatatt_{uuid4()}"},
    )

    assert result.success is False
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
