from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import (
    NextStep,
    NextStepKind,
    PipelineRequest,
    TriageDecision,
    TriageIntent,
)
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.pipeline import RuntimePipeline
from app.runtime.platform_config import PlatformSnapshot
from app.runtime.resume import ResumeResolver


class _MemoryPort:
    def __init__(self) -> None:
        self._store: dict = {}
        self._history: list[WorkingMemory] = []

    async def save(self, memory: WorkingMemory) -> None:
        snapshot = memory.model_copy(deep=True)
        self._store[memory.run_id] = snapshot
        self._history = [m for m in self._history if m.run_id != snapshot.run_id]
        self._history.append(snapshot)

    async def load(self, run_id):
        return self._store.get(run_id)

    async def load_latest_for_chat(self, chat_id):
        for item in reversed(self._history):
            if str(item.chat_id) == str(chat_id):
                return item
        return None

    async def load_paused_for_chat(self, chat_id):
        paused = []
        for item in reversed(self._history):
            if str(item.chat_id) != str(chat_id):
                continue
            if item.status in {"waiting_input", "waiting_confirmation"}:
                paused.append(item)
        return paused


@pytest.mark.asyncio
async def test_runtime_pipeline_direct_final_emits_enveloped_final():
    pipeline = RuntimePipeline(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )

    # Pre-seed the assembler's cached_property slots so no real adapters are
    # ever constructed (session/llm_client are SimpleNamespace stubs).
    assembler = pipeline._assembler
    memory_port = _MemoryPort()
    assembler.__dict__["memory"] = memory_port
    assembler.__dict__["triage"] = SimpleNamespace(
        decide=AsyncMock(
            return_value=TriageDecision(
                intent=TriageIntent.FINAL,
                confidence=0.9,
                reason="smalltalk",
                goal="hello",
                answer="hey",
            )
        )
    )
    assembler.__dict__["summary"] = SimpleNamespace(run=AsyncMock(return_value=None))
    assembler.__dict__["synthesizer"] = SimpleNamespace()  # unused on FINAL path
    assembler.__dict__["planner"] = SimpleNamespace()
    assembler.__dict__["agent_executor"] = SimpleNamespace()
    assembler.__dict__["resume"] = SimpleNamespace(
        bootstrap=AsyncMock(
            return_value=SimpleNamespace(
                memory=WorkingMemory(
                    run_id=uuid4(),
                    chat_id=uuid4(),
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                    goal="hello",
                    question="hello",
                    status="running",
                ),
                latest=None,
                paused_runs=[],
            )
        )
    )

    request = PipelineRequest(
        request_text="hello",
        chat_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        messages=[{"role": "user", "content": "hello"}],
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())

    empty_platform = PlatformSnapshot()  # empty config/agents/default policy
    with patch(
        "app.runtime.pipeline.PlatformConfigLoader.load",
        new=AsyncMock(return_value=empty_platform),
    ):
        events = [event async for event in pipeline.execute(request, ctx)]

    assert any(event.type == RuntimeEventType.FINAL for event in events)
    final_event = next(event for event in events if event.type == RuntimeEventType.FINAL)
    assert final_event.data.get("content") == "hey"
    assert "_envelope" in final_event.data
    assert final_event.data["_envelope"]["phase"] == "triage"
    assert final_event.data["_envelope"]["sequence"] >= 1


@pytest.mark.asyncio
async def test_runtime_pipeline_clarify_emits_terminal_contract_with_envelopes():
    pipeline = RuntimePipeline(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )

    assembler = pipeline._assembler
    memory_port = _MemoryPort()
    assembler.__dict__["memory"] = memory_port
    assembler.__dict__["resume"] = ResumeResolver(memory_port)
    assembler.__dict__["triage"] = SimpleNamespace(
        decide=AsyncMock(
            return_value=TriageDecision(
                intent=TriageIntent.CLARIFY,
                confidence=0.8,
                reason="need scope",
                clarify_prompt="Уточни контур",
            )
        )
    )
    assembler.__dict__["summary"] = SimpleNamespace(run=AsyncMock(return_value=None))
    assembler.__dict__["synthesizer"] = SimpleNamespace()
    assembler.__dict__["planner"] = SimpleNamespace()
    assembler.__dict__["agent_executor"] = SimpleNamespace()

    request = PipelineRequest(
        request_text="do task",
        chat_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        messages=[{"role": "user", "content": "do task"}],
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader.load",
        new=AsyncMock(return_value=PlatformSnapshot()),
    ):
        events = [event async for event in pipeline.execute(request, ctx)]

    assert any(event.type == RuntimeEventType.WAITING_INPUT for event in events)
    assert any(event.type == RuntimeEventType.STOP for event in events)
    assert all("_envelope" in event.data for event in events)

    sequences = [event.data["_envelope"]["sequence"] for event in events]
    assert sequences == sorted(sequences)
    assert sequences == list(range(1, len(events) + 1))

    stop_event = next(event for event in events if event.type == RuntimeEventType.STOP)
    assert stop_event.data.get("reason") == "waiting_input"
    assert stop_event.data["_envelope"]["phase"] == "triage"
    assert not any(event.type == RuntimeEventType.FINAL for event in events)


@pytest.mark.asyncio
async def test_runtime_pipeline_replay_paused_run_then_resume_to_final():
    pipeline = RuntimePipeline(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )
    assembler = pipeline._assembler
    memory_port = _MemoryPort()
    assembler.__dict__["memory"] = memory_port
    assembler.__dict__["resume"] = ResumeResolver(memory_port)

    assembler.__dict__["triage"] = SimpleNamespace(
        decide=AsyncMock(
            return_value=TriageDecision(
                intent=TriageIntent.CLARIFY,
                confidence=0.8,
                reason="need details",
                clarify_prompt="Уточни фильтр",
            )
        )
    )
    assembler.__dict__["planner"] = SimpleNamespace(
        next_step=AsyncMock(
            return_value=NextStep(
                kind=NextStepKind.FINAL,
                rationale="enough facts",
                final_answer="planner hint",
            )
        )
    )
    assembler.__dict__["agent_executor"] = SimpleNamespace(
        execute=lambda **kwargs: _empty_async_events()
    )

    async def _synth_stream(*, memory, run_id, model=None, planner_hint=None):
        memory.final_answer = "final after resume"
        yield RuntimeEvent.delta("final")
        yield RuntimeEvent.final("final after resume", run_id=str(run_id))

    assembler.__dict__["synthesizer"] = SimpleNamespace(stream=_synth_stream)
    assembler.__dict__["summary"] = SimpleNamespace(run=AsyncMock(return_value="summary"))

    platform = PlatformSnapshot(
        config={},
        routable_agents=[{"slug": "ops", "description": ""}],
    )
    request = PipelineRequest(
        request_text="start task",
        chat_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        messages=[{"role": "user", "content": "start task"}],
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader.load",
        new=AsyncMock(return_value=platform),
    ):
        events_turn_1 = [event async for event in pipeline.execute(request, ctx)]

    stop1 = next(event for event in events_turn_1 if event.type == RuntimeEventType.STOP)
    resumed_run_id = stop1.data.get("run_id")
    assert resumed_run_id

    assembler.__dict__["triage"] = SimpleNamespace(
        decide=AsyncMock(
            return_value=TriageDecision(
                intent=TriageIntent.RESUME,
                confidence=0.9,
                reason="answer to open question",
                resume_run_id=resumed_run_id,
            )
        )
    )

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader.load",
        new=AsyncMock(return_value=platform),
    ):
        events_turn_2 = [event async for event in pipeline.execute(request, ctx)]

    assert stop1.data.get("reason") == "waiting_input"
    assert any(event.type == RuntimeEventType.STATUS and event.data.get("stage") == "resumed_paused_run" for event in events_turn_2)
    assert any(event.type == RuntimeEventType.DELTA for event in events_turn_2)
    assert any(event.type == RuntimeEventType.FINAL for event in events_turn_2)

    final2 = next(event for event in events_turn_2 if event.type == RuntimeEventType.FINAL)
    assert final2.data.get("content") == "final after resume"
    assert final2.data["_envelope"]["sequence"] >= 1


async def _empty_async_events():
    if False:
        yield RuntimeEvent.status("noop")
