from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.contracts import PipelineRequest, TriageDecision, TriageIntent
from app.runtime.events import RuntimeEventType
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.pipeline import RuntimePipeline


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

    pipeline._memory = _MemoryPort()  # type: ignore[attr-defined]
    pipeline._resume = SimpleNamespace(  # type: ignore[attr-defined]
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
    pipeline._triage = SimpleNamespace(  # type: ignore[attr-defined]
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
    pipeline._summary = SimpleNamespace(run=AsyncMock(return_value=None))  # type: ignore[attr-defined]
    pipeline._config = SimpleNamespace(get_pipeline_config=AsyncMock(return_value={}))  # type: ignore[attr-defined]
    pipeline._list_routable_agents = AsyncMock(return_value=[])  # type: ignore[method-assign]

    request = PipelineRequest(
        request_text="hello",
        chat_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        messages=[{"role": "user", "content": "hello"}],
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())

    events = [event async for event in pipeline.execute(request, ctx)]

    assert any(event.type == RuntimeEventType.FINAL for event in events)
    final_event = next(event for event in events if event.type == RuntimeEventType.FINAL)
    assert final_event.data.get("content") == "hey"
    assert "_envelope" in final_event.data
    assert final_event.data["_envelope"]["phase"] == "triage"
    assert final_event.data["_envelope"]["sequence"] >= 1
