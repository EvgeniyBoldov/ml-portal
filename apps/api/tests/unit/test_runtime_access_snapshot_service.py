from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.runtime_access_snapshot_service import RuntimeAccessSnapshotService


@pytest.mark.asyncio
async def test_runtime_access_snapshot_service_builds_permissions_and_agents() -> None:
    perms = SimpleNamespace(
        agent_permissions={},
        tool_permissions={},
        collection_permissions={},
        denied_reasons={},
        default_tool_allow=True,
        default_collection_allow=True,
    )
    agent_a = SimpleNamespace(slug="a")
    agent_b = SimpleNamespace(slug="b")

    resolver = MagicMock()
    resolver.resolve_effective_permissions = AsyncMock(return_value=perms)
    resolver.filter_agents_by_slug = MagicMock(return_value=([agent_a], ["b"]))

    agent_service = MagicMock()
    agent_service.list_routable_agents = AsyncMock(return_value=[agent_a, agent_b])

    service = RuntimeAccessSnapshotService(resolver)
    snapshot = await service.build_snapshot(
        user_id=uuid4(),
        tenant_id=uuid4(),
        runtime_config={"default_tool_allow": True, "default_collection_allow": False},
        agent_service=agent_service,
    )

    assert snapshot.effective_permissions is perms
    assert snapshot.routable_agents == [agent_a]
    assert snapshot.denied_routable_agents == ["b"]
    resolver.resolve_effective_permissions.assert_awaited_once()
    agent_service.list_routable_agents.assert_awaited_once()
