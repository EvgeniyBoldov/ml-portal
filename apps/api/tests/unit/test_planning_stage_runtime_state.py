from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.budgets import BudgetRegistry, RunLimits
from app.runtime.budgets.errors import BudgetExceededError
from app.runtime.contracts import NextStep, NextStepKind, PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.stages.planning_stage import PlanningOutcomeKind, PlanningStage
from app.runtime.turn_state import RuntimeTurnState


class _PlannerAskUser:
    async def next_step(self, **kwargs) -> NextStep:
        return NextStep(
            kind=NextStepKind.ASK_USER,
            rationale="need input",
            question="точни период",
        )


class _AgentNoop:
    async def execute(self, **kwargs) -> AsyncIterator[Any]:
        if False:
            yield None
        return


class _PlannerCallAgent:
    async def next_step(self, **kwargs) -> NextStep:
        return NextStep(
            kind=NextStepKind.CALL_AGENT,
            rationale="delegate",
            agent_slug="ops",
            agent_input={"query": "q"},
        )


class _PlannerBadStep:
    async def next_step(self, **kwargs):
        return {"kind": "call_agent"}


class _AgentCaptureAndPause:
    def __init__(self) -> None:
        self.captured_agent_version_id: UUID | None = None

    async def execute(self, **kwargs) -> AsyncIterator[Any]:
        self.captured_agent_version_id = kwargs.get("agent_version_id")
        yield RuntimeEvent(
            RuntimeEventType.CONFIRMATION_REQUIRED,
            {
                "summary": "needs confirmation",
                "operation_fingerprint": "fp-1",
                "tool_slug": "ops.delete",
                "operation": "ops.delete",
                "risk_level": "destructive",
                "args_preview": "{}",
            },
        )


class _AgentErrorThenSuccess:
    async def execute(self, **kwargs) -> AsyncIterator[Any]:
        runtime_state: RuntimeTurnState = kwargs["runtime_state"]
        yield RuntimeEvent(
            RuntimeEventType.ERROR,
            {"message": "temporary problem", "recoverable": True},
        )
        runtime_state.add_agent_result(
            {
                "iteration": runtime_state.iter_count,
                "agent_slug": "ops",
                "phase_id": None,
                "summary": "ok",
                "success": True,
                "outcome": "success",
                "sufficient_for_phase": True,
                "missing_inputs": [],
                "retryable": None,
                "error_code": None,
            }
        )


class _PlannerFinalAfterCall:
    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, **kwargs) -> NextStep:
        self.calls += 1
        if self.calls == 1:
            return NextStep(
                kind=NextStepKind.CALL_AGENT,
                rationale="delegate",
                agent_slug="ops",
                agent_input={"query": "q"},
            )
        return NextStep(
            kind=NextStepKind.FINAL,
            rationale="done",
            final_answer="готово",
        )


def _memory():
    return SimpleNamespace(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="goal",
        question="goal",
        status="running",
        memory_state={},
    )


def _request(memory) -> PipelineRequest:
    return PipelineRequest(
        request_text="goal",
        chat_id=str(memory.chat_id),
        user_id=str(memory.user_id),
        tenant_id=str(memory.tenant_id),
        messages=[],
    )


async def _collect(gen: AsyncIterator[PhasedEvent]) -> List[PhasedEvent]:
    out: List[PhasedEvent] = []
    async for item in gen:
        out.append(item)
    return out


@pytest.mark.asyncio
async def test_planning_stage_syncs_runtime_turn_state_on_pause():
    memory = _memory()
    stage = PlanningStage(
        planner=_PlannerAskUser(),
        agent_executor=_AgentNoop(),
        max_iterations=3,
    )
    state = memory.memory_state["runtime_turn_state"] = {
        "run_id": str(memory.run_id),
        "chat_id": str(memory.chat_id),
        "user_id": str(memory.user_id),
        "tenant_id": str(memory.tenant_id),
        "goal": memory.goal,
        "current_user_query": memory.question,
        "memory_bundle": {"sections": [], "diagnostics": {}, "total_budget_used_chars": 0},
        "planner_steps": [],
        "agent_results": [],
        "runtime_facts": [],
        "tool_ledger": {"calls": []},
        "open_questions": [],
        "iter_count": 0,
        "used_tool_calls": 0,
        "recent_action_signatures": [],
        "status": "running",
        "final_answer": None,
        "final_error": None,
    }
    runtime_state = RuntimeTurnState.model_validate(state)
    request = _request(memory)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)

    events = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[],
            platform_config={},
        )
    )

    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.PAUSED
    assert stage.outcome.stop_reason == PipelineStopReason.WAITING_INPUT
    assert any(
        item.event.type.value == "stop"
        and item.event.data.get("reason") == PipelineStopReason.WAITING_INPUT.value
        for item in events
    )

    assert runtime_state.status == PipelineStopReason.WAITING_INPUT.value
    assert runtime_state.iter_count == 1
    assert runtime_state.open_questions == ["точни период"]
    assert len(runtime_state.planner_steps) == 1


def _runtime_state(memory, *, chat_id: str | None) -> RuntimeTurnState:
    return RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=UUID(chat_id) if chat_id else None,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal=memory.goal,
        current_user_query=memory.question,
        memory_bundle={"sections": [], "diagnostics": {}, "total_budget_used_chars": 0},
    )


@pytest.mark.asyncio
async def test_planning_stage_ignores_agent_version_id_for_chat_runtime():
    memory = _memory()
    agent = _AgentCaptureAndPause()
    stage = PlanningStage(
        planner=_PlannerCallAgent(),
        agent_executor=agent,
        max_iterations=2,
    )
    request = PipelineRequest(
        request_text="goal",
        chat_id=str(memory.chat_id),
        user_id=str(memory.user_id),
        tenant_id=str(memory.tenant_id),
        messages=[],
        agent_version_id=str(uuid4()),
    )
    runtime_state = _runtime_state(memory, chat_id=request.chat_id)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)

    _ = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[],
            platform_config={},
        )
    )
    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.PAUSED
    assert agent.captured_agent_version_id is None
    assert runtime_state.iteration_results
    assert runtime_state.iteration_results[-1].outcome == "needs_confirmation"


@pytest.mark.asyncio
async def test_planning_stage_passes_agent_version_id_for_sandbox_runtime():
    memory = _memory()
    agent = _AgentCaptureAndPause()
    stage = PlanningStage(
        planner=_PlannerCallAgent(),
        agent_executor=agent,
        max_iterations=2,
    )
    version_id = uuid4()
    request = PipelineRequest(
        request_text="goal",
        chat_id=None,
        user_id=str(memory.user_id),
        tenant_id=str(memory.tenant_id),
        messages=[],
        agent_version_id=str(version_id),
    )
    runtime_state = _runtime_state(memory, chat_id=None)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=None)

    _ = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[],
            platform_config={},
        )
    )
    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.PAUSED
    assert agent.captured_agent_version_id == version_id


class _BudgetRegistryFailStep(BudgetRegistry):
    def __init__(self) -> None:
        super().__init__(run_limits=RunLimits())

    def consume(self, *_args, **_kwargs):  # type: ignore[override]
        raise BudgetExceededError(scope="planner", metric="planner_steps", used=11, limit=10)


@pytest.mark.asyncio
async def test_planning_stage_emits_iteration_end_on_step_budget_failure():
    memory = _memory()
    stage = PlanningStage(
        planner=_PlannerAskUser(),
        agent_executor=_AgentNoop(),
        max_iterations=2,
    )
    request = _request(memory)
    runtime_state = _runtime_state(memory, chat_id=request.chat_id)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)
    ctx.extra["runtime_budget_registry"] = _BudgetRegistryFailStep()

    events = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[],
            platform_config={},
        )
    )
    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.FAILED
    assert any(e.event.type.value == "planner_iteration_end" for e in events)


@pytest.mark.asyncio
async def test_planning_stage_handles_invalid_planner_step_as_failed_iteration():
    memory = _memory()
    stage = PlanningStage(
        planner=_PlannerBadStep(),
        agent_executor=_AgentNoop(),
        max_iterations=2,
    )
    request = _request(memory)
    runtime_state = _runtime_state(memory, chat_id=request.chat_id)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)

    events = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[],
            platform_config={},
        )
    )
    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.FAILED
    assert any(e.event.type.value == "planner_iteration_end" for e in events)


@pytest.mark.asyncio
async def test_planning_stage_agent_end_completed_when_error_then_success_result():
    memory = _memory()
    stage = PlanningStage(
        planner=_PlannerFinalAfterCall(),
        agent_executor=_AgentErrorThenSuccess(),
        max_iterations=3,
    )
    request = _request(memory)
    runtime_state = _runtime_state(memory, chat_id=request.chat_id)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)

    events = await _collect(
        stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            available_agents=[{"slug": "ops"}],
            platform_config={},
        )
    )
    agent_end_events = [
        e.event.data for e in events if e.event.type.value == "agent_end"
    ]
    assert agent_end_events
    assert agent_end_events[-1].get("status") == "completed"
