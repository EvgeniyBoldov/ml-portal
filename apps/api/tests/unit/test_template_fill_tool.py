from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.template_fill import TemplateFillTool
from app.agents.context import ToolContext


@pytest.mark.asyncio
async def test_template_fill_returns_structured_validation_failure(monkeypatch):
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    collection = SimpleNamespace(collection_type="template")
    row = {
        "status": "ready",
        "file": {
            "s3_key": "templates/example.xlsx",
            "bucket": "bucket",
            "filename": "example.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        "template_schema": {
            "contract_version": "1.0",
            "format": "excel",
            "fields": [
                {"key": "author", "kind": "object", "label": "Author", "fields": [
                    {"key": "name", "kind": "scalar", "label": "Name", "type": "string", "required": True}
                ]}
            ],
        },
    }

    monkeypatch.setattr("app.agents.builtins.template_fill.get_session_factory", lambda: _SessionManager)
    collection_service = SimpleNamespace(
        get_by_id=AsyncMock(return_value=collection),
        get_by_slug=AsyncMock(return_value=collection),
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.CollectionService",
        lambda session: collection_service,
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.CollectionRowService",
        lambda session: SimpleNamespace(get_row_by_id=AsyncMock(return_value=row)),
    )
    monkeypatch.setattr("app.agents.builtins.template_fill.s3_manager.get_object", AsyncMock(return_value=b"fake"))

    tool = TemplateFillTool()
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())

    result = await tool.v1_0_0(
        ctx,
        {
            "collection_slug": "template",
            "row_id": str(uuid4()),
            "values": {"author.name": "Alice"},
        },
    )

    assert result.success is False
    assert "does not match the template schema" in result.error.lower()
    assert result.metadata["validation_summary"]["valid"] is False
    assert result.metadata["validation_errors"]
    assert any(item["path"] == "author" or item["path"] == "author.name" for item in result.metadata["validation_errors"])
    assert "retry" in result.metadata["retry_hint"].lower() or "repeat" in result.metadata["retry_hint"].lower()
    collection_service.get_by_slug.assert_awaited_once_with("template")


@pytest.mark.asyncio
async def test_template_fill_persists_custom_named_artifact(monkeypatch):
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    collection = SimpleNamespace(collection_type="template")
    row = {
        "status": "ready",
        "file": {
            "s3_key": "templates/example.xlsx",
            "bucket": "bucket",
            "filename": "example.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        "template_schema": {
            "contract_version": "1.0",
            "format": "excel",
            "fields": [
                {"key": "name", "kind": "scalar", "label": "Name", "type": "string", "required": True}
            ],
        },
    }
    artifact = SimpleNamespace(
        artifact_id="11111111-1111-1111-1111-111111111111",
        file_name="result.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=6,
    )
    fill_result = SimpleNamespace(
        success=True,
        content=b"result",
        filled_scalars=["name"],
        filled_tables=[],
        missing_scalars=[],
        missing_tables=[],
    )

    monkeypatch.setattr("app.agents.builtins.template_fill.get_session_factory", lambda: _SessionManager)
    collection_service = SimpleNamespace(
        get_by_id=AsyncMock(return_value=collection),
        get_by_slug=AsyncMock(return_value=collection),
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.CollectionService",
        lambda session: collection_service,
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.CollectionRowService",
        lambda session: SimpleNamespace(get_row_by_id=AsyncMock(return_value=row)),
    )
    monkeypatch.setattr("app.agents.builtins.template_fill.s3_manager.get_object", AsyncMock(return_value=b"workbook"))
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.TemplateFillEngine",
        lambda contract: SimpleNamespace(fill=lambda *args, **kwargs: fill_result),
    )
    write = AsyncMock(return_value=artifact)
    monkeypatch.setattr(
        "app.agents.builtins.template_fill.ArtifactWriter",
        lambda _session: SimpleNamespace(write=write),
    )

    result = await TemplateFillTool().v1_0_0(
        ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4()),
        {
            "collection_slug": "template",
            "row_id": str(uuid4()),
            "values": {"name": "Alice"},
            "filename": "result.xlsx",
        },
    )

    assert result.success is True
    assert result.data["artifact_id"] == artifact.artifact_id
    assert write.await_args.kwargs["filename"] == "result.xlsx"
    assert write.await_args.kwargs["content"] == b"result"
    session.commit.assert_awaited_once()
    collection_service.get_by_slug.assert_awaited_once_with("template")
