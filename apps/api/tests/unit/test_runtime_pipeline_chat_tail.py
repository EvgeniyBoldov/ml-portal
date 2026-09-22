from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.pipeline import RuntimePipeline


class _SessionContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_chat_post_final_tail_waits_for_assistant_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The detached tail must not touch chat context before the final message commits."""
    apply_outcome = AsyncMock()

    async def finalize_memory(*_args: object, **_kwargs: object):
        if False:
            yield None

    monkeypatch.setattr(RuntimePipeline, "_apply_chat_context_outcome", apply_outcome)
    monkeypatch.setattr(RuntimePipeline, "_finalize_memory", finalize_memory)

    pipeline = RuntimePipeline(session=MagicMock(), llm_client=MagicMock())
    start_event = asyncio.Event()
    emitter = MagicMock()
    emitter.emit = AsyncMock()
    request = PipelineRequest(
        request_text="test",
        chat_id="00000000-0000-0000-0000-000000000001",
        chat_turn_id="00000000-0000-0000-0000-000000000002",
        user_id="00000000-0000-0000-0000-000000000003",
        tenant_id="00000000-0000-0000-0000-000000000004",
    )

    task = asyncio.create_task(
        pipeline._run_chat_post_final_tail(
            session_factory=lambda: _SessionContext(MagicMock()),
            turn_mem=MagicMock(),
            runtime_state=SimpleNamespace(run_id="run-1"),
            request=request,
            stop_reason=PipelineStopReason.COMPLETED,
            emitter=emitter,
            branch_id=None,
            project_context={},
            term_bindings=[],
            start_event=start_event,
            terminal_orchestrator_id=None,
            recall_item=None,
            recall_tenant_id=None,
            logging_level=None,
        )
    )
    await asyncio.sleep(0)
    apply_outcome.assert_not_awaited()

    start_event.set()
    await task

    apply_outcome.assert_awaited_once()
    emitter.emit.assert_awaited_once()
