from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
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
async def test_file_delete_commits_reference_removal(monkeypatch):
    session = AsyncMock()
    delete_reference = AsyncMock(
        return_value={"deleted": True, "artifact_id": str(uuid4()), "file_name": "report.txt"}
    )
    monkeypatch.setattr("app.agents.builtins.file_delete.get_session_factory", lambda: _session_manager(session))
    monkeypatch.setattr(
        "app.services.chat_artifact_reference_service.ChatArtifactReferenceService.delete_reference",
        delete_reference,
    )

    result = await FileDeleteTool().v1_0_0(
        _context(),
        {"artifact_id": str(uuid4())},
    )

    assert result.success is True
    delete_reference.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_file_delete_returns_safe_error_on_lifecycle_failure(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr("app.agents.builtins.file_delete.get_session_factory", lambda: _session_manager(session))
    monkeypatch.setattr(
        "app.services.chat_artifact_reference_service.ChatArtifactReferenceService.delete_reference",
        AsyncMock(side_effect=ValueError("storage deletion failed")),
    )

    result = await FileDeleteTool().v1_0_0(
        _context(),
        {"artifact_id": str(uuid4())},
    )

    assert result.success is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_file_delete_rejects_missing_chat_context():
    result = await FileDeleteTool().v1_0_0(
        ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=None),
        {"artifact_id": str(uuid4())},
    )
    assert result.success is False
