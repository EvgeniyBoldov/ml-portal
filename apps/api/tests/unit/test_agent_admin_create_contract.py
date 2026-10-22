from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.agent import Agent
from app.services import agent_service as module
from app.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_create_agent_persists_all_execution_settings(monkeypatch):
    created = []

    class AgentRepo:
        def __init__(self, _session):
            pass

        async def get_by_slug(self, _slug):
            return None

        async def create(self, agent):
            agent.id = uuid4()
            created.append(agent)
            return agent

    class Rbac:
        def __init__(self, _session):
            pass

        async def ensure_platform_deny(self, *_args):
            return None

    monkeypatch.setattr(module, "AgentRepository", AgentRepo)
    monkeypatch.setattr(module, "RbacService", Rbac)
    service = AgentService(SimpleNamespace())

    agent = await service.create_agent(
        slug="agent-contract-test",
        name="Contract test",
        model="llm.test",
        temperature=0.35,
        requires_confirmation_for_write=True,
        risk_level="high",
    )

    assert len(created) == 1
    assert isinstance(agent, Agent)
    assert agent.model == "llm.test"
    assert agent.temperature == 0.35
    assert agent.requires_confirmation_for_write is True
    assert agent.risk_level == "high"
