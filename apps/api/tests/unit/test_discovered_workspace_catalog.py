from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.agents.runtime.result_workspace_tools import WORKSPACE_TOOLS
from app.api.v1.routers.admin import discovered_tools
from app.schemas.discovered_tools import DiscoveredToolUpdateRequest


@pytest.mark.asyncio
async def test_runtime_workspace_list_and_detail_are_read_only_without_discovery_rows(monkeypatch):
    discovery = Mock(list_all=AsyncMock(return_value=[]), source_types_for=AsyncMock(return_value={}))
    monkeypatch.setattr(discovered_tools, "ToolDiscoveryService", lambda _: discovery)
    db = Mock()

    async def list_tools(**filters):
        return await discovered_tools.list_discovered_tools(
            **({"source": None, "provider_instance_id": None, "domain": None, "is_active": None} | filters),
            db=db, _=None,
        )

    items = await list_tools()
    assert {item.slug for item in items} == {*WORKSPACE_TOOLS, "result.analyze"}
    assert all(item.runtime_managed and item.source_types == ["system"] for item in items)
    assert await list_tools(source="mcp") == []
    assert await list_tools(is_active=False) == []

    reader = next(item for item in items if item.slug == "result.read")
    detail = await discovered_tools.get_discovered_tool(reader.id, db=db, _=None)
    assert detail.slug == "result.read"
    assert "result_id" in detail.input_schema["properties"]
    with pytest.raises(HTTPException) as error:
        await discovered_tools.update_discovered_tool(
            reader.id, DiscoveredToolUpdateRequest(result_delivery="store"), db=db, _=None,
        )
    assert error.value.status_code == 409
    db.execute.assert_not_called()
