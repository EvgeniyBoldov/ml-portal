from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.builtins import memory_search
from app.runtime.memory.search import MemorySearchService


@pytest.mark.asyncio
async def test_tool_reads_native_documents_without_legacy_memory(monkeypatch):
    legacy = AsyncMock(side_effect=AssertionError("Legacy memory must not be queried"))
    monkeypatch.setattr(MemorySearchService, "search", legacy)
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(memory_search, "get_session_factory", lambda: lambda: session)
    native = AsyncMock(return_value={"backend": "hipporag", "document_count": 1, "index": "graph",
        "hits": [{"text": "Prepare a backup before changes", "score": 0.9,
                  "metadata": {"document_id": "doc1", "document_title": "Regulation"}}]})
    service = MagicMock(search_documents=native)
    monkeypatch.setattr(memory_search, "HippoRAGService", lambda _: service)
    result = await memory_search.MemorySearchTool().v1_0_0(
        ToolContext(tenant_id=uuid4(), user_id=uuid4()), {"query": "backup"})
    assert result.success
    assert result.delivery == "direct"
    assert result.data["count"] == 1
    assert result.data["items"][0]["text"] == "Prepare a backup before changes"
    assert result.data["items"][0]["source_references"][0]["document_id"] == "doc1"
    native.assert_awaited_once_with("backup", limit=8)
    legacy.assert_not_awaited()


def test_native_search_schema_does_not_expose_old_memory_filters():
    from app.runtime.memory.search_contract import HippoMemorySearchInput
    assert set(HippoMemorySearchInput.model_json_schema()["properties"]) == {"query", "limit"}
