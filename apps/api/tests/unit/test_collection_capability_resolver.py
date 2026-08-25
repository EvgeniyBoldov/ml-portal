from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.capability_resolver import CollectionCapabilityResolver


@pytest.mark.asyncio
async def test_provider_discovered_tools_become_collection_capabilities_without_name_mapping():
    tool_loader = SimpleNamespace(
        load_discovered_tools_for_collection=AsyncMock(
            return_value=[
                SimpleNamespace(source="mcp", slug="jira_search_issues"),
                SimpleNamespace(source="mcp", slug="jira_get_issue"),
                SimpleNamespace(source="local", slug="collection.info"),
            ]
        )
    )
    resolver = CollectionCapabilityResolver(tool_loader)

    candidates = await resolver.resolve_for_collection(
        collection=SimpleNamespace(collection_type="api"),
        instance=SimpleNamespace(),
        provider=SimpleNamespace(),
    )

    assert [candidate.canonical_op_slug for candidate in candidates] == [
        "jira_search_issues",
        "jira_get_issue",
        "collection.info",
    ]
