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

    async def _run_sequential_planner(**kwargs):
        if False:
            yield RuntimeEvent(RuntimeEventType.STATUS, {"stage": "noop"})

    runtime.run_agent_with_tools = _run_agent_with_tools
    runtime.run_direct = _run_agent_with_tools
    runtime.run_sequential_planner = _run_sequential_planner
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
    triage_events = [event for event in events if event.data.get("orchestration_envelope")]
    assert triage_events
    assert all(event.data["orchestration_envelope"]["phase"] == "triage" for event in triage_events)


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
    planner_stage = next(
        (
            event
            for event in events
            if event.type == RuntimeEventType.STATUS and event.data.get("stage") == "executing_planner"
        ),
        None,
    )
    assert planner_stage is not None
    assert planner_stage.data.get("orchestration_envelope", {}).get("phase") == "planner"


@pytest.mark.asyncio
async def test_pipeline_uses_single_routable_agents_snapshot_for_triage_and_preflight(
    pipeline: RuntimePipeline,
):
    exec_request = SimpleNamespace(
        agent_slug="rag-search",
        mode=SimpleNamespace(value="full"),
        resolved_operations=[],
        execution_graph=RuntimeExecutionGraph(),
        effective_permissions=None,
        available_actions=SimpleNamespace(agents=[]),
        agent_version=None,
    )
    agent_a = SimpleNamespace(slug="rag-search", name="RAG", description="RAG", tags=[])
    agent_b = SimpleNamespace(slug="analyst", name="Analyst", description="Analyst", tags=[])

    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[agent_a, agent_b])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock(return_value=exec_request)

    triage_mock = AsyncMock(return_value={
        "type": "orchestrate",
        "confidence": 0.9,
        "answer": None,
        "clarify_prompt": None,
        "goal": "go",
        "inputs": {},
    })

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(
        return_value=SimpleNamespace(
            agent_permissions={},
            tool_permissions={},
            collection_permissions={},
            denied_reasons={},
            default_tool_allow=True,
            default_collection_allow=True,
        )
    )
    pipeline.runtime_rbac_resolver.filter_agents_by_slug = MagicMock(
        return_value=([agent_a, agent_b], [])
    )
    pipeline._run_triage = triage_mock

    _ = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    agent_service.list_routable_agents.assert_awaited_once()
    triage_call = triage_mock.await_args
    assert triage_call.kwargs["routable_agents"] == [agent_a, agent_b]
    preflight_call = preflight.prepare.await_args
    assert preflight_call.kwargs["routable_agents_override"] == [agent_a, agent_b]


@pytest.mark.asyncio
async def test_pipeline_triage_fail_open_falls_back_to_orchestrate(
    pipeline: RuntimePipeline,
):
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

    async def triage_raises(*args, **kwargs):
        raise RuntimeError("triage boom")

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_raises

    _ = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    preflight.prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_triage_fail_closed_returns_error_without_preflight(
    pipeline: RuntimePipeline,
):
    pipeline._load_platform_config = AsyncMock(return_value={"triage_fail_open": False})
    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock()

    async def triage_raises(*args, **kwargs):
        raise RuntimeError("triage boom")

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_raises

    events = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    preflight.prepare.assert_not_awaited()
    assert any(event.type == RuntimeEventType.ERROR and "Triage failed" in str(event.data.get("error")) for event in events)


@pytest.mark.asyncio
async def test_pipeline_preflight_fail_open_returns_degraded_final(
    pipeline: RuntimePipeline,
):
    pipeline._load_platform_config = AsyncMock(return_value={"preflight_fail_open": True})
    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock(side_effect=RuntimeError("preflight boom"))

    triage_mock = AsyncMock(return_value={
        "type": "orchestrate",
        "confidence": 0.9,
        "answer": None,
        "clarify_prompt": None,
        "goal": "go",
        "inputs": {},
    })

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_mock

    events = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    assert any(event.type == RuntimeEventType.STATUS and event.data.get("stage") == "preflight_degraded" for event in events)
    assert any(event.type == RuntimeEventType.FINAL for event in events)


@pytest.mark.asyncio
async def test_pipeline_preflight_fail_closed_returns_error(
    pipeline: RuntimePipeline,
):
    pipeline._load_platform_config = AsyncMock(return_value={"preflight_fail_open": False})
    agent_service = MagicMock()
    agent_service.get_default_agent_slug = AsyncMock(return_value="rag-search")
    agent_service.list_routable_agents = AsyncMock(return_value=[])
    agent_service.get_agent_by_slug = AsyncMock(return_value=SimpleNamespace(logging_level="brief"))

    preflight = MagicMock()
    preflight.prepare = AsyncMock(side_effect=RuntimeError("preflight boom"))

    triage_mock = AsyncMock(return_value={
        "type": "orchestrate",
        "confidence": 0.9,
        "answer": None,
        "clarify_prompt": None,
        "goal": "go",
        "inputs": {},
    })

    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_mock

    events = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    assert any(event.type == RuntimeEventType.ERROR and "Preflight failed" in str(event.data.get("error")) for event in events)


@pytest.mark.asyncio
async def test_pipeline_planner_fail_open_returns_degraded_final(
    pipeline: RuntimePipeline,
    runtime: MagicMock,
):
    pipeline._load_platform_config = AsyncMock(return_value={"planner_fail_open": True})
    exec_request = SimpleNamespace(
        run_id=uuid4(),
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
    triage_mock = AsyncMock(return_value={
        "type": "orchestrate",
        "confidence": 0.9,
        "answer": None,
        "clarify_prompt": None,
        "goal": "go",
        "inputs": {},
    })

    async def planner_raises(**kwargs):
        raise RuntimeError("planner boom")
        yield  # pragma: no cover

    runtime.run_sequential_planner = planner_raises
    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_mock

    events = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    assert any(event.type == RuntimeEventType.STATUS and event.data.get("stage") == "planner_degraded" for event in events)
    assert any(event.type == RuntimeEventType.FINAL for event in events)


@pytest.mark.asyncio
async def test_pipeline_planner_fail_closed_returns_error(
    pipeline: RuntimePipeline,
    runtime: MagicMock,
):
    pipeline._load_platform_config = AsyncMock(return_value={"planner_fail_open": False})
    exec_request = SimpleNamespace(
        run_id=uuid4(),
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
    triage_mock = AsyncMock(return_value={
        "type": "orchestrate",
        "confidence": 0.9,
        "answer": None,
        "clarify_prompt": None,
        "goal": "go",
        "inputs": {},
    })

    async def planner_raises(**kwargs):
        raise RuntimeError("planner boom")
        yield  # pragma: no cover

    runtime.run_sequential_planner = planner_raises
    pipeline.agent_service = agent_service
    pipeline._preflight = preflight
    pipeline._run_triage = triage_mock

    events = [
        event
        async for event in pipeline.execute(
            request_text="orchestrate",
            user_id=uuid4(),
            tenant_id=uuid4(),
            messages=[{"role": "user", "content": "orchestrate"}],
            ctx=SimpleNamespace(extra={}),
            agent_slug=None,
            model=None,
        )
    ]

    assert any(event.type == RuntimeEventType.ERROR and "Planner failed" in str(event.data.get("error")) for event in events)
