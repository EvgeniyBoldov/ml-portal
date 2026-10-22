from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.phase_limits import iter_with_phase_deadline, stream_synthesis_with_deadline
from app.agents.context import ToolContext
from app.runtime.budgets import BudgetRegistry, EntityLimits, RunLimits
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.stages.graph_planning_stage import GraphPlanningOutcomeKind, GraphPlanningStage
from app.runtime.turn_state import RuntimeTurnState


@pytest.mark.asyncio
async def test_phase_deadline_cancels_long_running_async_stream() -> None:
    cancelled = asyncio.Event()

    async def slow_stream():
        try:
            await asyncio.sleep(0.05)
            yield "late"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(TimeoutError):
        async for _ in iter_with_phase_deadline(slow_stream(), 5):
            pass

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_synthesis_stream_receives_budget_controls_and_phase_deadline() -> None:
    registry = object()
    resolver = SimpleNamespace(resolve_orchestrator=AsyncMock(
        return_value=SimpleNamespace(wall_time_ms=5),
    ))
    received: dict = {}

    class SlowSynthesizer:
        async def stream(self, **kwargs):
            received.update(kwargs)
            await asyncio.sleep(0.05)
            yield "late"

    with pytest.raises(TimeoutError):
        async for _ in stream_synthesis_with_deadline(
            SlowSynthesizer(), budget_registry=registry, budget_resolver=resolver,
            sandbox_overrides={"role_overrides": {}}, run_id="run", runtime_state=object(),
        ):
            pass

    resolver.resolve_orchestrator.assert_awaited_once_with(
        "synthesizer", {"role_overrides": {}},
    )
    assert received["budget_registry"] is registry
    assert received["budget_resolver"] is resolver
    assert received["sandbox_overrides"] == {"role_overrides": {}}


@pytest.mark.asyncio
async def test_phase_stream_without_deadline_completes() -> None:
    async def stream():
        yield "event"

    events = [item async for item in iter_with_phase_deadline(stream(), None)]

    assert events == ["event"]


@pytest.mark.asyncio
async def test_graph_planning_stage_marks_plan_failed_when_phase_deadline_expires(monkeypatch) -> None:
    import app.runtime.stages.graph_planning_stage as stage_module

    run_id, plan_id = uuid4(), uuid4()
    store = SimpleNamespace(
        get_by_run=AsyncMock(return_value=None),
        create=AsyncMock(return_value=SimpleNamespace(id=plan_id, status="draft", goal="goal")),
        mark_failed=AsyncMock(),
        snapshot=AsyncMock(return_value={
            "status": "failed", "root_run_id": str(run_id),
            "last_failure": {"code": "planner_phase_timeout", "message": "timeout"},
        }),
    )

    async def slow_orchestration(**_kwargs):
        await asyncio.sleep(0.05)
        yield SimpleNamespace()

    orchestrator = SimpleNamespace(run=slow_orchestration, synthesizer=object(), logging_level="none")
    registry = BudgetRegistry(run_limits=RunLimits())
    resolver = SimpleNamespace(resolve_orchestrator=AsyncMock(return_value=EntityLimits(wall_time_ms=5)))
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={
        "runtime_budget_registry": registry,
        "runtime_budget_resolver": resolver,
    })

    async def no_partial_answer(**_kwargs):
        if False:
            yield None

    monkeypatch.setattr(stage_module, "stream_partial_answer", no_partial_answer)
    stage = GraphPlanningStage(orchestrator=orchestrator, store=store, max_steps=1)
    request = PipelineRequest(request_text="goal", user_id=str(ctx.user_id), tenant_id=str(ctx.tenant_id))
    state = RuntimeTurnState(run_id=run_id, goal="goal")

    async for _ in stage.run(
        runtime_state=state, request=request, ctx=ctx, user_id=ctx.user_id, tenant_id=ctx.tenant_id,
        available_agents=[], platform_config={}, orchestrator_id="planner",
    ):
        pass

    assert stage.outcome is not None
    assert stage.outcome.kind is GraphPlanningOutcomeKind.FAILED
    store.mark_failed.assert_awaited_once_with(
        plan_id, "planner_phase_timeout", "Planner exceeded its configured phase time limit",
    )
    assert stage.outcome.stop_reason is PipelineStopReason.FAILED
