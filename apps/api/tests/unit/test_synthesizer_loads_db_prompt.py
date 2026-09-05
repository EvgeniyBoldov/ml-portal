from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.runtime.memory.components import MemoryBundle
from app.runtime.events import RuntimeEventType
from app.runtime.llm.streaming import StreamError, StreamTurn
from app.runtime.synthesizer import Synthesizer
from app.runtime.turn_state import RuntimeTurnState


class _LLMClientProbe:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[dict] = []

    async def chat_stream(self, messages, model=None, params=None, options=None):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "params": params,
                "options": options,
            }
        )
        for chunk in self.chunks:
            yield chunk


def _runtime_state() -> RuntimeTurnState:
    return RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="compare docs",
        current_user_query="compare docs",
        memory_bundle=MemoryBundle(),
    )


def _synthesis_context(*, artifacts=None) -> dict:
    return {
        "synthesis_task": {
            "task_id": "synthesize",
            "intent": "Answer the user's request",
            "instructions": "Give a direct answer from the completed reports.",
        },
        "completed_task_reports": [
            {"task_id": "inspect", "intent": "Inspect", "instructions": "Read", "report": {"description": "Found data", "outputs": {}}},
        ],
        "artifacts": artifacts or [],
        "sources": [],
    }


@pytest.mark.asyncio
async def test_synthesizer_loads_db_prompt_and_passes_role_params_to_llm():
    llm = _LLMClientProbe(["hello ", "world"])
    synth = Synthesizer(session=SimpleNamespace(), llm_client=llm)
    state = _runtime_state()

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
    ), patch(
        "app.services.model_call_config_service.ModelCallConfigService.resolve",
        new=AsyncMock(
            return_value=SimpleNamespace(
                max_output_tokens=None,
                request_timeout_s=30,
                max_retries=2,
            )
        ),
    ):
        events = [event async for event in synth.stream(
            runtime_state=state,
            run_id=state.run_id,
            synthesis_context=_synthesis_context(),
        )]

    assert llm.calls, "chat_stream was not called"
    call = llm.calls[0]
    assert call["model"] == "gpt-test"
    assert call["params"] == {"temperature": 0.15, "max_tokens": 321}
    assert call["options"].timeout_s == 30
    assert call["messages"][0]["content"].startswith("SYNTH-PROMPT")
    assert "Сгенерированные файлы доставляются интерфейсом отдельными вложениями" in call["messages"][0]["content"]
    assert events[0].type.value == "synthesis_start"
    assert any(ev.type.value == "status" for ev in events)
    assert events[-2].type.value == "final"
    assert events[-1].type.value == "synthesis_end"
    assert state.final_answer == "hello world"


@pytest.mark.asyncio
async def test_synthesizer_finalizes_deduplicated_attachment_download_urls():
    synth = Synthesizer(session=SimpleNamespace(), llm_client=_LLMClientProbe(["Файл готов"]))
    state = _runtime_state()

    events = [
        event
        async for event in synth.stream(
            runtime_state=state,
            run_id=state.run_id,
            synthesis_context=_synthesis_context(artifacts=[
                {"artifact_id": "artifact-1", "file_name": "result.txt"},
                {"artifact_id": "artifact-1", "file_name": "result.txt"},
            ]),
        )
    ]

    final = next(event for event in events if event.type.value == "final")
    assert final.data["attachments"] == [{
        "artifact_id": "artifact-1",
        "file_name": "result.txt",
        "download_url": "/api/v1/files/artifact-1/download",
        "content_type": "",
        "size_bytes": None,
    }]


@pytest.mark.asyncio
async def test_synthesizer_falls_back_when_db_role_load_fails():
    llm = _LLMClientProbe(["fallback answer"])
    synth = Synthesizer(session=SimpleNamespace(), llm_client=llm)
    state = _runtime_state()

    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        events = [event async for event in synth.stream(
            runtime_state=state,
            run_id=state.run_id,
            synthesis_context=_synthesis_context(),
        )]

    assert llm.calls, "chat_stream was not called on fallback"
    call = llm.calls[0]
    assert call["model"] is None
    assert call["params"] == {"temperature": 0.3, "max_tokens": 2000}
    assert call["options"].timeout_s == 60
    assert call["messages"][0]["content"]  # fallback prompt is non-empty
    assert events[-2].type.value == "final"
    assert events[-2].data["content"] == "fallback answer"
    assert events[-1].type.value == "synthesis_end"


@pytest.mark.asyncio
async def test_synthesizer_retries_retryable_stream_error_before_fallback():
    synth = Synthesizer(session=SimpleNamespace(), llm_client=_LLMClientProbe([]))
    state = _runtime_state()
    calls = 0

    async def stream_once(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield StreamError(
                code="llm_rate_limited",
                message="LLM provider rate limit reached",
                recoverable=True,
                error_type="LLMProviderError",
                retry_after_ms=1,
            )
            return
        yield StreamTurn(
            llm_call_id="retry-call",
            model="gpt-test",
            content="retry answer",
            response_length=12,
        )

    synth._streaming_call.invoke_stream = stream_once
    with (
        patch(
            "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
            new=AsyncMock(return_value={"prompt": "SYNTH-PROMPT", "model": "gpt-test"}),
        ),
        patch(
            "app.services.model_call_config_service.ModelCallConfigService.resolve",
            new=AsyncMock(return_value=SimpleNamespace(max_retries=1)),
        ),
        patch("app.runtime.synthesizer.asyncio.sleep", new=AsyncMock()),
    ):
        events = [
            event
            async for event in synth.stream(
                runtime_state=state,
                run_id=state.run_id,
                synthesis_context=_synthesis_context(),
            )
        ]

    assert calls == 2
    assert len([event for event in events if event.type is RuntimeEventType.LLM_REQUEST]) == 2
    retry = next(event for event in events if event.type is RuntimeEventType.PROTOCOL_RETRY)
    assert retry.data["reason"] == "transport_error"
    assert retry.data["retry_after_ms"] == 1
    assert not any(event.type is RuntimeEventType.ERROR for event in events)
    assert events[-2].type is RuntimeEventType.FINAL
    assert events[-2].data["content"] == "retry answer"
    assert events[-1].data["status"] == "completed"


@pytest.mark.asyncio
async def test_synthesizer_empty_response_is_an_explicit_error():
    llm = _LLMClientProbe([])
    synth = Synthesizer(session=SimpleNamespace(), llm_client=llm)
    state = _runtime_state()

    events = [
        event
        async for event in synth.stream(
            runtime_state=state,
            run_id=state.run_id,
            synthesis_context=_synthesis_context(),
        )
    ]

    assert not any(event.type is RuntimeEventType.FINAL for event in events)
    assert any(
        event.type is RuntimeEventType.ERROR
        and event.data["error_code"] == "synthesizer_empty_response"
        for event in events
    )
    assert state.final_error == "synthesizer_empty_response"
