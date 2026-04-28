from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import NextStep, NextStepKind, PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.stages.planning_stage import PlanningOutcomeKind, PlanningStage


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
        max_wall_time_ms=30_000,
    )
    request = _request(memory)
    ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)

    events = await _collect(
        stage.run(
            memory=memory,
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

    runtime_state = memory.memory_state.get("runtime_turn_state")
    assert isinstance(runtime_state, dict)
    assert runtime_state["status"] == PipelineStopReason.WAITING_INPUT.value
    assert runtime_state["iter_count"] == 1
    assert runtime_state["open_questions"] == ["точни период"]
    assert len(runtime_state["planner_steps"]) == 1
