from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import (
    NextStep,
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
    TriageDecision,
    TriageIntent,
)
from app.runtime.events import RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.resume import ResumeResolver
from app.runtime.stages.finalization_stage import FinalizationStage
from app.runtime.stages.planning_stage import PlanningOutcomeKind, PlanningStage
from app.runtime.stages.triage_stage import TriageOutcomeKind, TriageStage


class _MemoryPort:
    def __init__(self) -> None:
        self.saved: list[WorkingMemory] = []

    async def save(self, memory: WorkingMemory) -> None:
        self.saved.append(memory.model_copy(deep=True))

    async def load(self, run_id):
        return None

    async def load_latest_for_chat(self, chat_id):
        return None

    async def load_paused_for_chat(self, chat_id):
        return []


def _request() -> PipelineRequest:
    return PipelineRequest(
        request_text="check inventory",
        chat_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        messages=[{"role": "user", "content": "check inventory"}],
    )


def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="check inventory",
        question="check inventory",
        status="running",
    )


@pytest.mark.asyncio
async def test_triage_stage_clarify_pauses_run():
    memory_port = _MemoryPort()
    triage = SimpleNamespace(
        decide=AsyncMock(
            return_value=TriageDecision(
                intent=TriageIntent.CLARIFY,
                confidence=0.7,
                clarify_prompt="Уточни диапазон дат",
            )
        )
    )
    stage = TriageStage(
        triage=triage,
        memory_port=memory_port,
        resume=ResumeResolver(memory_port),
    )

    events = []
    async for phased in stage.run(
        memory=_memory(),
        latest_memory=None,
        paused_runs=[],
        request=_request(),
        routable_agents=[],
        platform_config={},
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
    ):
        events.append(phased.event.type.value)

    assert "waiting_input" in events
    assert "stop" in events
    assert stage.outcome is not None
    assert stage.outcome.kind == TriageOutcomeKind.CLARIFY_PAUSED


@pytest.mark.asyncio
async def test_planning_stage_ask_user_sets_paused_outcome():
    memory_port = _MemoryPort()
    planner = SimpleNamespace(
        next_step=AsyncMock(
            return_value=NextStep(
                kind=NextStepKind.ASK_USER,
                rationale="need input",
                question="Какой регион?",
            )
        )
    )
    agent_executor = SimpleNamespace(execute=lambda **kwargs: _empty_async_iter())
    stage = PlanningStage(
        planner=planner,
        agent_executor=agent_executor,
        memory_port=memory_port,
        max_iterations=3,
        max_wall_time_ms=10_000,
    )

    events = []
    async for phased in stage.run(
        memory=_memory(),
        request=_request(),
        ctx=ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4()),
        user_id=uuid4(),
        tenant_id=uuid4(),
        available_agents=[{"slug": "ops", "description": ""}],
        platform_config={},
    ):
        events.append(phased.event.type.value)

    assert "planner_step" in events
    assert "waiting_input" in events
    assert stage.outcome is not None
    assert stage.outcome.kind == PlanningOutcomeKind.PAUSED
    assert stage.outcome.stop_reason == PipelineStopReason.WAITING_INPUT


@pytest.mark.asyncio
async def test_finalization_stage_runs_synthesizer_and_persists():
    memory = _memory()

    async def _synth_stream(**kwargs):
        yield RuntimeEvent.delta("hello")
        memory.final_answer = "hello world"

    summary = SimpleNamespace(run=AsyncMock(return_value="summary"))
    memory_port = _MemoryPort()
    stage = FinalizationStage(
        synthesizer=SimpleNamespace(stream=_synth_stream),
        summary=summary,
        memory_port=memory_port,
    )

    event_types = []
    async for phased in stage.run(
        memory=memory,
        stop_reason=PipelineStopReason.COMPLETED,
        planner_hint=None,
        model=None,
        run_synthesizer=True,
    ):
        event_types.append(phased.event.type.value)

    assert "delta" in event_types
    assert memory.status == PipelineStopReason.COMPLETED.value
    assert memory.finished_at is not None
    assert len(memory_port.saved) >= 1
    summary.run.assert_awaited_once()


async def _empty_async_iter():
    if False:
        yield None
