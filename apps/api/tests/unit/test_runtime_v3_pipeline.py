from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import PipelineRequest, TriageDecision, TriageIntent
from app.runtime.events import RuntimeEventType
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.pipeline import RuntimePipeline
from app.runtime.platform_config import PlatformSnapshot


class _MemoryPort:
    def __init__(self) -> None:
        self._store: dict = {}

    async def save(self, memory: WorkingMemory) -> None:
        self._store[memory.run_id] = memory.model_copy(deep=True)

    async def load(self, run_id):
        return self._store.get(run_id)

    async def load_latest_for_chat(self, chat_id):
        return None

    async def load_paused_for_chat(self, chat_id):
        return []


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
