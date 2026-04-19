from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.synthesizer import Synthesizer


class _LLMClientProbe:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[dict] = []

    async def chat_stream(self, messages, model=None, params=None):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "params": params,
            }
        )
        for chunk in self.chunks:
            yield chunk


def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="compare docs",
        question="compare docs",
        status="running",
    )


@pytest.mark.asyncio
async def test_synthesizer_loads_db_prompt_and_passes_role_params_to_llm():
    llm = _LLMClientProbe(["hello ", "world"])
    synth = Synthesizer(session=SimpleNamespace(), llm_client=llm)
    memory = _memory()

    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(
            return_value={
                "prompt": "SYNTH-PROMPT",
                "model": "gpt-test",
                "temperature": 0.15,
                "max_tokens": 321,
            }
        ),
    ):
        events = [event async for event in synth.stream(
            memory=memory,
            run_id=memory.run_id,
            planner_hint="force full synthesis path",
        )]

    assert llm.calls, "chat_stream was not called"
    call = llm.calls[0]
    assert call["model"] == "gpt-test"
    assert call["params"] == {"temperature": 0.15, "max_tokens": 321}
    assert call["messages"][0]["content"] == "SYNTH-PROMPT"
    assert events[0].type.value == "status"
    assert events[-1].type.value == "final"
    assert memory.final_answer == "hello world"


@pytest.mark.asyncio
async def test_synthesizer_falls_back_when_db_role_load_fails():
    llm = _LLMClientProbe(["fallback answer"])
    synth = Synthesizer(session=SimpleNamespace(), llm_client=llm)
    memory = _memory()

    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        events = [event async for event in synth.stream(
            memory=memory,
            run_id=memory.run_id,
            planner_hint="force full synthesis path",
        )]

    assert llm.calls, "chat_stream was not called on fallback"
    call = llm.calls[0]
    assert call["model"] is None
    assert call["params"] == {"temperature": 0.3, "max_tokens": 2000}
    assert call["messages"][0]["content"]  # fallback prompt is non-empty
    assert events[-1].type.value == "final"
    assert events[-1].data["content"] == "fallback answer"
