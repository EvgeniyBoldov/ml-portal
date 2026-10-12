"""Opt-in PostgreSQL checks; all synthetic records are rolled back."""
import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.runtime.events import RuntimeEvent, OrchestrationPhase
from app.services.agent_service import AgentService
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.services.runtime_event_logger import RuntimeEventLogger, RuntimeLogContext, RuntimeLoggingLevel

pytestmark = pytest.mark.skipif(os.getenv("SHADOW_WORKFLOW_PG") != "1", reason="requires opt-in PostgreSQL")


@pytest.mark.asyncio
async def test_default_type_catalog_filter_and_shadow_journal():
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                    regular = Agent(slug="shadow-test-regular-" + uuid4().hex, name="Test regular")
                    shadow = Agent(slug="shadow-test-shadow-" + uuid4().hex, name="Test shadow", agent_type="shadow")
                    session.add_all([regular, shadow])
                    await session.flush()
                    assert regular.agent_type == "regular"
                    versions = [AgentVersion(agent_id=agent.id, version=1, status="published") for agent in [regular, shadow]]
                    session.add_all(versions)
                    await session.flush()
                    for agent, version in zip([regular, shadow], versions):
                        agent.current_version_id = version.id
                    await session.flush()
                    service = AgentService(session)
                    catalog = await service.list_routable_agents_for_planner()
                    slugs = {item["slug"] for item in catalog}
                    assert regular.slug in slugs
                    assert shadow.slug not in slugs
                    assert shadow.slug not in {agent.slug for agent in await service.list_routable_agents()}
                    await service.update_agent(regular.id, agent_type="shadow")
                    assert regular.slug not in {item["slug"] for item in await service.list_routable_agents_for_planner()}
                    await service.update_agent(regular.id, agent_type="regular")
                    assert regular.slug in {item["slug"] for item in await service.list_routable_agents_for_planner()}

                    run_id, execution_id = uuid4(), uuid4()
                    journal = RuntimeEventLogger(session=session, context=RuntimeLogContext(
                        run_id=run_id, origin="shadow", level=RuntimeLoggingLevel.FULL,
                        entity_type="agent_execution", entity_id=str(execution_id)))
                    await journal.emit(RuntimeEvent.agent_start(
                        agent_execution_id=str(execution_id), parent_entity_id=str(run_id), agent_slug=shadow.slug), phase=OrchestrationPhase.AGENT)
                    await journal.emit(RuntimeEvent.agent_end(
                        agent_execution_id=str(execution_id), parent_entity_id=str(run_id), agent_slug=shadow.slug, status="completed"), phase=OrchestrationPhase.AGENT)
                    reader = RuntimeEventJournalService(session)
                    runs = await reader.list_agent_executions(limit=500)
                    assert str(execution_id) in {row.entity_id for row in runs}
                    events = await reader.list_agent_execution_events(str(execution_id))
                    assert {row.event_type for row in events} == {"agent_start", "agent_end"}
                    assert all(row.chat_id is None and row.origin == "shadow" for row in events)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shadow_service_with_real_preflight_rbac_config_and_journal(monkeypatch):
    """Only the outbound LLM is fake; all DB and runtime collaborators are real."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.rbac import RbacRule
    from app.models.user import Users
    from app.models.tenant import Tenants
    from app.models.runtime_observability import RuntimeExecutionEvent
    from app.schemas.shadow_agents import ShadowAgentRequest
    from app.services import shadow_agent_service as module

    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                factory = async_sessionmaker(connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
                monkeypatch.setattr(module, "get_session_factory", lambda: factory)
                async with factory() as session:
                    user = Users(login="shadow-test-" + uuid4().hex)
                    tenant = Tenants(name="shadow-test-" + uuid4().hex)
                    agent = Agent(slug="shadow-runtime-test-" + uuid4().hex, name="Shadow test", agent_type="shadow", logging_level="full", model="shadow-test-model")
                    session.add_all([user, tenant, agent])
                    await session.flush()
                    version = AgentVersion(agent_id=agent.id, version=1, status="published", mission="Summarize the supplied inputs as JSON.")
                    session.add(version)
                    await session.flush()
                    agent.current_version_id = version.id
                    session.add(RbacRule(level="user", owner_user_id=user.id, resource_type="agent", resource_id=agent.id, effect="allow"))
                    await session.flush()
                    client = SimpleNamespace(chat=AsyncMock(return_value={"choices": [{"message": {"content":
                        '{"completion":"fulfilled","structured_response":{"summary":"ok"},"needs":[]}'}}]}))
                    response = await module.ShadowAgentService(session, client).invoke(
                        ShadowAgentRequest(agent=agent.slug, data={"text": "x" * 9000}),
                        user_id=user.id, tenant_id=tenant.id, scopes=[], request_id="shadow-test-request")
                    assert response.result == {"summary": "ok"}
                    client.chat.assert_awaited_once()
                    assert "tools" not in client.chat.call_args.kwargs["params"]
                    events = (await session.execute(select(RuntimeExecutionEvent).where(
                        RuntimeExecutionEvent.user_id == user.id,
                        RuntimeExecutionEvent.origin == "shadow",
                    ).order_by(RuntimeExecutionEvent.sequence))).scalars().all()
                    assert events
                    assert all(event.chat_id is None and event.tenant_id == tenant.id for event in events)
                    assert len({event.run_id for event in events}) == 1
                    assert len([event for event in events if event.event_type == "agent_end"]) == 1
                    assert events[-1].event_type == "run_end"
                    assert events[-1].payload["status"] == "completed"
                    assert any(event.event_type == "llm_request" for event in events)
                    assert any(event.event_type == "preflight_completed" for event in events)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
