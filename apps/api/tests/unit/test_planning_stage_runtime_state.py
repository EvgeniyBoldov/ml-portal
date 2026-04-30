from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from uuid import UUID, uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import NextStep, NextStepKind, PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.memory.working_memory import WorkingMemory
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


def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="goal",
        question="goal",
        status="running",
    )


def _request(memory: WorkingMemory) -> PipelineRequest:
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
    assert any(item.event.type.value == "waiting_input" for item in events)

    assert runtime_state.status == PipelineStopReason.WAITING_INPUT.value
    assert runtime_state.iter_count == 1
    assert runtime_state.open_questions == ["точни период"]
    assert len(runtime_state.planner_steps) == 1


def _runtime_state(memory: WorkingMemory, *, chat_id: str | None) -> RuntimeTurnState:
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
