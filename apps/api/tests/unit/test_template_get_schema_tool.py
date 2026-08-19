from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.template_fill import TemplateFillTool
from app.agents.builtins.template_get_schema import TemplateGetSchemaTool
from app.agents.builtins.template_list import TemplateListTool
from app.agents.context import ToolContext


@pytest.mark.asyncio
async def test_template_schema_uses_collection_slug_not_legacy_collection_id(monkeypatch) -> None:
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    collection = SimpleNamespace(collection_type="template")
    row = {
        "id": uuid4(),
        "title": "Connectivity request",
        "template_schema": {"contract_version": "1.0", "format": "excel", "fields": []},
    }
    collection_service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=collection),
        get_by_id=AsyncMock(),
    )
    row_service = SimpleNamespace(get_row_by_id=AsyncMock(return_value=row))

    monkeypatch.setattr(
        "app.agents.builtins.template_get_schema.get_session_factory",
        lambda: _SessionManager,
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_get_schema.CollectionService",
        lambda _: collection_service,
    )
    monkeypatch.setattr(
        "app.agents.builtins.template_get_schema.CollectionRowService",
        lambda _: row_service,
    )

    tool = TemplateGetSchemaTool()
    result = await tool.v1_0_0(
        ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4()),
        {"collection_slug": "template", "row_id": str(uuid4())},
    )

    assert result.success is False
    assert "schema is not available" in result.error.lower()
    collection_service.get_by_slug.assert_awaited_once_with("template")
    collection_service.get_by_id.assert_not_awaited()
    assert tool.validate_args({"collection_slug": "template", "row_id": str(uuid4())}) is None


def test_all_template_tools_publish_collection_slug_contract() -> None:
    tools_and_args = [
        (TemplateListTool(), {"collection_slug": "template"}),
        (TemplateGetSchemaTool(), {"collection_slug": "template", "row_id": str(uuid4())}),
        (
            TemplateFillTool(),
            {"collection_slug": "template", "row_id": str(uuid4()), "values": {}},
        ),
    ]

    for tool, args in tools_and_args:
        schema = tool.get_latest_version().input_schema
        assert tool.validate_args(args) is None
        assert "collection_slug" in schema["required"]
        assert "collection_id" not in schema["properties"]
