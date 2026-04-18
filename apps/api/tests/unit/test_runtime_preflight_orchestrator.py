from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.execution_preflight import AgentUnavailableError
from app.agents.runtime.events import RuntimeEventType
from app.services.runtime_preflight_orchestrator import RuntimePreflightOrchestrator


@pytest.mark.asyncio
async def test_preflight_orchestrator_success():
    orchestrator = RuntimePreflightOrchestrator(trace_logger=SimpleNamespace(log_error=AsyncMock()))
    exec_request = SimpleNamespace(agent_slug="a1")
    prepare = AsyncMock(return_value=exec_request)
    pipeline_run = SimpleNamespace(run_id="r1", log_step=AsyncMock(), finish=AsyncMock())

    outcome = await orchestrator.execute(
        prepare_execution=prepare,
        prepare_kwargs={"x": 1},
        platform_config={},
        pipeline_run=pipeline_run,
    )

    assert outcome.exec_request is exec_request
    assert not outcome.should_stop
    assert not outcome.events


@pytest.mark.asyncio
async def test_preflight_orchestrator_agent_unavailable_stops():
    trace_logger = SimpleNamespace(log_error=AsyncMock())
    orchestrator = RuntimePreflightOrchestrator(trace_logger=trace_logger)
    prepare = AsyncMock(side_effect=AgentUnavailableError("unavailable"))
    pipeline_run = SimpleNamespace(run_id="r1", log_step=AsyncMock(), finish=AsyncMock())

    outcome = await orchestrator.execute(
        prepare_execution=prepare,
        prepare_kwargs={},
        platform_config={},
        pipeline_run=pipeline_run,
    )

    assert outcome.should_stop
    assert outcome.events and outcome.events[0].type == RuntimeEventType.ERROR
    trace_logger.log_error.assert_awaited_once()
    pipeline_run.finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_preflight_orchestrator_fail_open_returns_degraded_final():
    orchestrator = RuntimePreflightOrchestrator(trace_logger=SimpleNamespace(log_error=AsyncMock()))
    prepare = AsyncMock(side_effect=RuntimeError("boom"))
    pipeline_run = SimpleNamespace(run_id="r1", log_step=AsyncMock(), finish=AsyncMock())

    outcome = await orchestrator.execute(
        prepare_execution=prepare,
        prepare_kwargs={},
        platform_config={"preflight_fail_open": True},
        pipeline_run=pipeline_run,
    )

    assert outcome.should_stop
    assert [event.type for event in outcome.events] == [RuntimeEventType.STATUS, RuntimeEventType.FINAL]
    pipeline_run.log_step.assert_awaited_once()
    pipeline_run.finish.assert_awaited_once()
