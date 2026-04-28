"""
Unit tests for AgentResolver.resolve() — three resolution branches.

Branch 1: agent_version_id provided → load AgentVersion then Agent.
Branch 2: agent_slug provided      → load Agent then resolve_published_version.
Branch 3: neither provided         → resolve_published_version(None) then load Agent by id.
"""
from __future__ import annotations

from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.agent_resolver import AgentResolver, AgentResolveResult
from app.agents.contracts import AvailableActions


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

def _make_agent(slug: str = "test-agent") -> MagicMock:
    agent = MagicMock()
    agent.id = uuid4()
    agent.slug = slug
    return agent


def _make_version(agent_id=None) -> MagicMock:
    ver = MagicMock()
    ver.id = uuid4()
    ver.agent_id = agent_id or uuid4()
    ver.compiled_prompt = "test prompt"
    return ver


def _make_available_actions() -> AvailableActions:
    return AvailableActions(operations=[], routable_agents=[], agent_prompt="")


def _make_resolver(session: Any = None) -> AgentResolver:
    return AgentResolver(session=session or AsyncMock())


# ---------------------------------------------------------------------------
# Branch 1: agent_version_id supplied
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_by_version_id_loads_version_then_agent():
    agent = _make_agent()
    version = _make_version(agent_id=agent.id)
    tenant_id = uuid4()

    resolver = _make_resolver()

    # session.execute → scalar_one_or_none returns version
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = version
    resolver.session.execute = AsyncMock(return_value=execute_result)

    resolver.agent_service.get_agent_with_versions_by_id = AsyncMock(return_value=agent)
    resolver.agent_service.list_routable_agents = AsyncMock(return_value=[])
    resolver.available_actions_builder.build = AsyncMock(return_value=_make_available_actions())

    result = await resolver.resolve(
        agent_slug=None,
        tenant_id=tenant_id,
        agent_version_id=version.id,
    )

    assert isinstance(result, AgentResolveResult)
    assert result.agent is agent
    assert result.agent_version is version
    resolver.agent_service.get_agent_with_versions_by_id.assert_awaited_once_with(version.agent_id)


@pytest.mark.asyncio
async def test_resolve_by_version_id_raises_when_version_not_found():
    tenant_id = uuid4()
    resolver = _make_resolver()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    resolver.session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(ValueError, match="not found"):
        await resolver.resolve(
            agent_slug=None,
            tenant_id=tenant_id,
            agent_version_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# Branch 2: agent_slug supplied (no version override)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_by_slug_loads_agent_then_published_version():
    agent = _make_agent(slug="chat-rag")
    version = _make_version(agent_id=agent.id)
    tenant_id = uuid4()

    resolver = _make_resolver()
    resolver.agent_service.get_agent_by_slug = AsyncMock(return_value=agent)
    resolver.agent_service.resolve_published_version = AsyncMock(return_value=version)
    resolver.agent_service.list_routable_agents = AsyncMock(return_value=[])
    resolver.available_actions_builder.build = AsyncMock(return_value=_make_available_actions())

    result = await resolver.resolve(agent_slug="chat-rag", tenant_id=tenant_id)

    assert result.agent is agent
    assert result.agent_version is version
    resolver.agent_service.get_agent_by_slug.assert_awaited_once_with("chat-rag")
    resolver.agent_service.resolve_published_version.assert_awaited_once_with(
        "chat-rag", tenant_id=tenant_id
    )


# ---------------------------------------------------------------------------
# Branch 3: neither slug nor version_id — resolves default published version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_no_slug_loads_published_version_then_agent():
    agent = _make_agent()
    version = _make_version(agent_id=agent.id)
    tenant_id = uuid4()

    resolver = _make_resolver()
    resolver.agent_service.resolve_published_version = AsyncMock(return_value=version)
    resolver.agent_service.get_agent_with_versions_by_id = AsyncMock(return_value=agent)
    resolver.agent_service.list_routable_agents = AsyncMock(return_value=[])
    resolver.available_actions_builder.build = AsyncMock(return_value=_make_available_actions())

    result = await resolver.resolve(agent_slug=None, tenant_id=tenant_id)

    assert result.agent is agent
    assert result.agent_version is version
    resolver.agent_service.resolve_published_version.assert_awaited_once_with(
        None, tenant_id=tenant_id
    )
    resolver.agent_service.get_agent_with_versions_by_id.assert_awaited_once_with(version.agent_id)


# ---------------------------------------------------------------------------
# Routable agents are excluded when include_routable_agents=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_skips_routable_agents_when_disabled():
    agent = _make_agent()
    version = _make_version(agent_id=agent.id)
    tenant_id = uuid4()

    resolver = _make_resolver()
    resolver.agent_service.get_agent_by_slug = AsyncMock(return_value=agent)
    resolver.agent_service.resolve_published_version = AsyncMock(return_value=version)
    resolver.agent_service.list_routable_agents = AsyncMock(return_value=[MagicMock()])
    resolver.available_actions_builder.build = AsyncMock(return_value=_make_available_actions())

    await resolver.resolve(
        agent_slug="chat-rag",
        tenant_id=tenant_id,
        include_routable_agents=False,
    )

    resolver.agent_service.list_routable_agents.assert_not_awaited()
    _, kwargs = resolver.available_actions_builder.build.call_args
    assert kwargs["routable_agents"] == []
