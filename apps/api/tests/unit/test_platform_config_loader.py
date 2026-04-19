from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.runtime.platform_config import PlatformConfigLoader, PolicyLimits


@pytest.mark.asyncio
async def test_platform_config_loader_happy_path_builds_snapshot():
    with patch(
        "app.services.runtime_config_service.RuntimeConfigService.get_pipeline_config",
        new=AsyncMock(return_value={"policy": {"max_steps": 7, "max_wall_time_ms": 3333}}),
    ), patch(
        "app.services.agent_service.AgentService.list_routable_agents",
        new=AsyncMock(
            return_value=[
                SimpleNamespace(slug="ops", description="Operations"),
                SimpleNamespace(slug="analyst", description="Analytics"),
            ]
        ),
    ):
        snapshot = await PlatformConfigLoader(SimpleNamespace()).load()

    assert snapshot.policy == PolicyLimits(max_steps=7, max_wall_time_ms=3333)
    assert snapshot.routable_agents == [
        {"slug": "ops", "description": "Operations"},
        {"slug": "analyst", "description": "Analytics"},
    ]
    assert snapshot.available_agents_for_planner("pinned-agent") == [
        {"slug": "pinned-agent", "description": ""}
    ]


@pytest.mark.asyncio
async def test_platform_config_loader_degrades_when_config_unavailable():
    with patch(
        "app.services.runtime_config_service.RuntimeConfigService.get_pipeline_config",
        new=AsyncMock(side_effect=RuntimeError("config down")),
    ), patch(
        "app.services.agent_service.AgentService.list_routable_agents",
        new=AsyncMock(return_value=[SimpleNamespace(slug="ops", description="Ops")]),
    ):
        snapshot = await PlatformConfigLoader(SimpleNamespace()).load()

    assert snapshot.config == {}
    assert snapshot.policy == PolicyLimits()  # defaults
    assert snapshot.routable_agents == [{"slug": "ops", "description": "Ops"}]


@pytest.mark.asyncio
async def test_platform_config_loader_degrades_when_agents_unavailable():
    with patch(
        "app.services.runtime_config_service.RuntimeConfigService.get_pipeline_config",
        new=AsyncMock(return_value={"policy": {"max_steps": 4}}),
    ), patch(
        "app.services.agent_service.AgentService.list_routable_agents",
        new=AsyncMock(side_effect=RuntimeError("agents down")),
    ):
        snapshot = await PlatformConfigLoader(SimpleNamespace()).load()

    assert snapshot.policy.max_steps == 4
    assert snapshot.routable_agents == []
