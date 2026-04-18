from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.services.runtime_planner_orchestrator import RuntimePlannerOrchestrator
from app.services.runtime_triage_orchestrator import RuntimeTriageOrchestrator


@pytest.mark.asyncio
async def test_runtime_triage_orchestrator_fail_open_returns_orchestrate():
    trace_logger = SimpleNamespace(log_error=AsyncMock())
    orchestrator = RuntimeTriageOrchestrator(trace_logger)
    pipeline_run = SimpleNamespace(run_id="r1", log_step=AsyncMock(), finish=AsyncMock())

    async def _raise(**kwargs):
        raise RuntimeError("triage fail")

    result = await orchestrator.execute(
        run_triage=_raise,
        request_text="q",
        messages=[],
        platform_config={"triage_fail_open": True},
        routable_agents=[],
        pipeline_run=pipeline_run,
    )
    assert result is not None
    assert result.type == "orchestrate"
    pipeline_run.log_step.assert_awaited_once()
    pipeline_run.finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_planner_orchestrator_fail_open_emits_degraded_final():
    trace_logger = SimpleNamespace(log_error=AsyncMock())
    orchestrator = RuntimePlannerOrchestrator(trace_logger)

    class _UseCase:
        async def execute(self, **kwargs):
            raise RuntimeError("planner fail")
            yield  # pragma: no cover

    events = []
    async for ev in orchestrator.stream(
        execute_planner_use_case=_UseCase(),
        exec_request=SimpleNamespace(run_id="run-1"),
        messages=[],
        ctx=SimpleNamespace(),
        model=None,
        enable_logging=True,
        platform_config={"planner_fail_open": True},
        pipeline_run=SimpleNamespace(run_id="run-1", log_step=AsyncMock()),
    ):
        events.append(ev)

    assert orchestrator.last_status == "completed"
    assert any(event.type == RuntimeEventType.STATUS and event.data.get("stage") == "planner_degraded" for event in events)
    assert any(event.type == RuntimeEventType.FINAL for event in events)


@pytest.mark.asyncio
async def test_runtime_planner_orchestrator_tracks_terminal_status():
    trace_logger = SimpleNamespace(log_error=AsyncMock())
    orchestrator = RuntimePlannerOrchestrator(trace_logger)

    class _UseCase:
        async def execute(self, **kwargs):
            yield RuntimeEvent(RuntimeEventType.STOP, {"reason": "waiting_input", "question": "q"})

    events = []
    async for ev in orchestrator.stream(
        execute_planner_use_case=_UseCase(),
        exec_request=SimpleNamespace(run_id="run-1"),
        messages=[],
        ctx=SimpleNamespace(),
        model=None,
        enable_logging=True,
        platform_config={},
        pipeline_run=SimpleNamespace(run_id="run-1", log_step=AsyncMock()),
    ):
        events.append(ev)

    assert events
    assert orchestrator.last_status == "waiting_input"
    assert orchestrator.last_error == "q"


@pytest.mark.asyncio
async def test_runtime_planner_orchestrator_updates_state_store():
    trace_logger = SimpleNamespace(log_error=AsyncMock())
    orchestrator = RuntimePlannerOrchestrator(trace_logger)
    state_store = SimpleNamespace(update=AsyncMock())

    class _UseCase:
        async def execute(self, **kwargs):
            yield RuntimeEvent(
                RuntimeEventType.PLANNER_ACTION,
                {"action_type": "agent_call", "iteration": 1, "agent_slug": "a1", "phase_id": "p1"},
            )
            yield RuntimeEvent(RuntimeEventType.STOP, {"reason": "waiting_input", "question": "q"})

    async for _ in orchestrator.stream(
        execute_planner_use_case=_UseCase(),
        exec_request=SimpleNamespace(run_id="run-1"),
        messages=[],
        ctx=SimpleNamespace(),
        model=None,
        enable_logging=True,
        platform_config={},
        pipeline_run=SimpleNamespace(run_id="run-1", log_step=AsyncMock()),
        state_store=state_store,
        state_chat_id="c1",
        state_tenant_id="t1",
    ):
        pass

    assert state_store.update.await_count >= 2
