from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.contracts import PipelineStopReason
from app.runtime.memory.components import MemoryBundle
from app.runtime.stages.planner_budget_initializer import PlannerBudgetInitializer
from app.runtime.stages.planner_next_step_invoker import PlannerNextStepInvoker
from app.runtime.stages.planner_post_call_arbiter import PlannerPostCallArbiter
from app.runtime.stages.planning_outcome_mapper import PlanningOutcomeMapper
from app.runtime.turn_state import RuntimeTurnState


class _FakeBudgetRegistry:
    def __init__(self) -> None:
        self.register_called = False

    def register(self, **_kwargs) -> None:
        self.register_called = True

    def emit_snapshot(self, *_args, **_kwargs):
        return {"own": {"planner_steps": 0}, "limits": {"planner_steps": 10}, "at_ms": 1}


def _state() -> RuntimeTurnState:
    return RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=None,
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="g",
        current_user_query="q",
        memory_bundle=MemoryBundle(),
    )


def test_planner_budget_initializer_registers_and_emits():
    registry = _FakeBudgetRegistry()
    event = PlannerBudgetInitializer.register_and_emit_init(
        planner_registry=registry,
        orchestrator_id="orch-1",
        run_id="run-1",
        planner_limits={"planner_steps": 10},
    )
    assert registry.register_called is True
    assert event is not None
    assert event.event.type.value == "budget_snapshot"


def test_planning_outcome_mapper_maps_terminal_and_call_agent():
    terminal = SimpleNamespace(
        outcome_kind="paused",
        stop_reason=PipelineStopReason.WAITING_INPUT,
        planner_hint=None,
        final_answer_strategy="synthesize",
        error_message=None,
    )
    mapped_terminal = PlanningOutcomeMapper.from_terminal_result(terminal)
    assert mapped_terminal["outcome_kind"] == "paused"
    assert mapped_terminal["stop_reason"] == PipelineStopReason.WAITING_INPUT

    mapped_call_agent = PlanningOutcomeMapper.from_call_agent_result(
        SimpleNamespace(outcome="needs_final")
    )
    assert mapped_call_agent is not None
    assert mapped_call_agent["outcome_kind"] == "needs_final"
    assert mapped_call_agent["stop_reason"] == PipelineStopReason.FAILED


@pytest.mark.asyncio
async def test_planner_next_step_invoker_handles_tuple_and_single_result():
    planner = AsyncMock()
    state = _state()

    planner.next_step = AsyncMock(return_value=("step-a", ["trace-a"]))
    step, traces = await PlannerNextStepInvoker.invoke(
        planner=planner,
        runtime_state=state,
        available_agents=[],
        outline=None,
        platform_config={},
        chat_id=None,
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        agent_run_id=state.run_id,
        planner_iteration_id="it-1",
        sandbox_overrides=None,
    )
    assert step == "step-a"
    assert traces == ["trace-a"]

    planner.next_step = AsyncMock(return_value="step-b")
    step, traces = await PlannerNextStepInvoker.invoke(
        planner=planner,
        runtime_state=state,
        available_agents=[],
        outline=None,
        platform_config={},
        chat_id=None,
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        agent_run_id=state.run_id,
        planner_iteration_id="it-2",
        sandbox_overrides=None,
    )
    assert step == "step-b"
    assert traces == []


def test_planner_post_call_arbiter_loop_and_continue_paths():
    loop_state = _state()
    loop_state.recent_action_signatures = ["dup", "dup", "dup"]
    events, result = PlannerPostCallArbiter.evaluate(
        runtime_state=loop_state,
        planner_run_id="run-1",
        planner_iteration_id="it-1",
        planner_iteration=1,
        orchestrator_id="orch-1",
    )
    assert result.should_stop is True
    assert result.stop_reason == PipelineStopReason.LOOP_DETECTED
    assert any(e.event.type.value == "status" for e in events)

    ok_state = _state()
    events, result = PlannerPostCallArbiter.evaluate(
        runtime_state=ok_state,
        planner_run_id="run-2",
        planner_iteration_id="it-2",
        planner_iteration=2,
        orchestrator_id="orch-2",
    )
    assert result.should_stop is False
    assert len(events) == 1
    assert events[0].event.type.value == "planner_iteration_end"
