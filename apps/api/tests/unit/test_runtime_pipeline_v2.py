from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.logging import LoggingLevel
from app.agents.runtime_graph import RuntimeExecutionGraph
from app.agents.runtime.pipeline import RuntimePipeline


@pytest.fixture
def runtime() -> MagicMock:
    runtime = MagicMock()

    async def _run_agent_with_tools(**kwargs):
        yield RuntimeEvent.final("done", [])

    runtime.run_agent_with_tools = _run_agent_with_tools
    runtime.run_direct = _run_agent_with_tools
    return runtime


@pytest.fixture
def pipeline(mock_session, mock_llm_client, runtime) -> RuntimePipeline:
    p = RuntimePipeline(
        session=mock_session,
        llm_client=mock_llm_client,
        runtime=runtime,
    )
    p.logging_resolver.resolve_logging_level = AsyncMock(return_value=LoggingLevel.BRIEF)
    p._load_platform_config = AsyncMock(return_value={})
    return p


@pytest.mark.asyncio
async def test_pipeline_returns_clarify_stop(pipeline: RuntimePipeline):
    exec_request = SimpleNamespace(
        agent_slug="rag-search",
        mode=SimpleNamespace(value="full"),
        resolved_operations=[],
        execution_graph=RuntimeExecutionGraph(),
        effective_permissions=None,
        available_actions=SimpleNamespace(agents=[]),
        agent_version=None,
    )

    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock(return_value=exec_request)

    async def fake_triage(*args, **kwargs):
        return {
            "type": "clarify",
            "confidence": 0.8,
            "answer": None,
            "clarify_prompt": "Уточни, какой регламент сравнивать",
            "goal": None,
            "inputs": {},
        }

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight

    with patch.object(RuntimePipeline, "_run_triage", new=fake_triage):
        events = [
            event
            async for event in pipeline.execute(
                request_text="сравни регламенты",
                user_id=uuid4(),
                tenant_id=uuid4(),
                messages=[{"role": "user", "content": "сравни регламенты"}],
                ctx=SimpleNamespace(extra={}),
                agent_slug=None,
                model=None,
            )
        ]

    event_types = [event.type for event in events]
    assert RuntimeEventType.WAITING_INPUT in event_types
    assert RuntimeEventType.STOP in event_types
    assert any(event.data.get("question") == "Уточни, какой регламент сравнивать" for event in events)


@pytest.mark.asyncio
async def test_pipeline_builds_outline_for_orchestrate(pipeline: RuntimePipeline):
    exec_request = SimpleNamespace(
        agent_slug="rag-search",
        mode=SimpleNamespace(value="full"),
        resolved_operations=[SimpleNamespace(operation_slug="instance.docs.rag.search")],
        execution_graph=RuntimeExecutionGraph(),
        effective_permissions=None,
        available_actions=SimpleNamespace(
            agents=[SimpleNamespace(agent_slug="rag-search"), SimpleNamespace(agent_slug="analyst")]
        ),
        agent_version=None,
    )

    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock(return_value=exec_request)

    async def fake_triage(*args, **kwargs):
        return {
            "type": "orchestrate",
            "confidence": 0.9,
            "answer": None,
            "clarify_prompt": None,
            "goal": "сравнить регламенты по RAG",
            "inputs": {},
        }

    ctx = SimpleNamespace(extra={})

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight

    with patch.object(RuntimePipeline, "_run_triage", new=fake_triage):
        events = [
            event
            async for event in pipeline.execute(
                request_text="сравни регламенты в rag",
                user_id=uuid4(),
                tenant_id=uuid4(),
                messages=[{"role": "user", "content": "сравни регламенты в rag"}],
                ctx=ctx,
                agent_slug=None,
                model=None,
            )
        ]

    assert "execution_outline" in ctx.extra
    outline = ctx.extra["execution_outline"]
    phase_ids = [phase["phase_id"] for phase in outline["phases"]]
    assert "search_and_retrieve" in phase_ids
    assert "compare_findings" in phase_ids
    assert "finalize" in phase_ids
    assert any(event.type == RuntimeEventType.STATUS and event.data.get("stage") == "outline_ready" for event in events)
