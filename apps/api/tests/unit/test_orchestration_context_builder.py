from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.orchestration_context_builder import OrchestrationContextBuilder


@pytest.mark.asyncio
async def test_builder_resolves_effective_agent_and_snapshot():
    snapshot_service = SimpleNamespace()
    snapshot_service.build_snapshot = AsyncMock(
        return_value=SimpleNamespace(routable_agents=[], denied_routable_agents=[], effective_permissions={})
    )
    builder = OrchestrationContextBuilder(snapshot_service)

    agent_service = SimpleNamespace(
        get_default_agent_slug=AsyncMock(return_value="triage"),
    )

    async def _load_config():
        return {"triage_fail_open": True}

    ctx = await builder.build(
        request_text="ping",
        user_id=uuid4(),
        tenant_id=uuid4(),
        requested_agent_slug="assistant",
        default_slugs={"assistant", None},
        sandbox_overrides={"platform": {"planner_fail_open": False}},
        agent_service=agent_service,
        load_platform_config=_load_config,
    )

    assert ctx.effective_agent_slug == "triage"
    assert ctx.platform_config["triage_fail_open"] is True
    assert ctx.platform_config["planner_fail_open"] is False
