from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.runtime.planner import PlannerRuntime


async def _collect(async_gen):
    items = []
    async for item in async_gen:
        items.append(item)
    return items


@pytest.mark.asyncio
async def test_recover_or_fail_without_facts_emits_error_and_finishes():
    runtime = PlannerRuntime(llm_client=AsyncMock(), run_store=None)
    runtime._synthesize_from_facts = AsyncMock()

    compact_ctx = SimpleNamespace(facts=[])
    run_session = AsyncMock()
    memory_service = AsyncMock()
    exec_request = SimpleNamespace(run_id=uuid4())
    ctx = SimpleNamespace(chat_id=uuid4(), tenant_id=uuid4())

    events = await _collect(
        runtime._recover_or_fail(
            messages=[],
            compact_ctx=compact_ctx,
            gen=SimpleNamespace(),
            policy=SimpleNamespace(),
            run_session=run_session,
            memory_service=memory_service,
            exec_request=exec_request,
            ctx=ctx,
            error_type="unexpected",
            finish_error="boom",
            client_message="boom",
            recoverable=False,
        )
    )

    assert len(events) == 1
    assert events[0].type.value == "error"
    run_session.finish.assert_awaited_once_with("failed", "boom")
    memory_service.finish_run.assert_awaited()


@pytest.mark.asyncio
async def test_recover_or_fail_with_facts_uses_synthesis_path():
    runtime = PlannerRuntime(llm_client=AsyncMock(), run_store=None)

    async def _fake_synthesis(*args, **kwargs):
        yield SimpleNamespace(type=SimpleNamespace(value="delta"), data={"content": "ok"})

    runtime._synthesize_from_facts = _fake_synthesis

    compact_ctx = SimpleNamespace(facts=["f1"])
    run_session = AsyncMock()
    memory_service = AsyncMock()
    exec_request = SimpleNamespace(run_id=uuid4())
    ctx = SimpleNamespace(chat_id=uuid4(), tenant_id=uuid4())

    events = await _collect(
        runtime._recover_or_fail(
            messages=[],
            compact_ctx=compact_ctx,
            gen=SimpleNamespace(),
            policy=SimpleNamespace(),
            run_session=run_session,
            memory_service=memory_service,
            exec_request=exec_request,
            ctx=ctx,
            error_type="timeout",
            finish_error="timeout",
            client_message="Request timed out",
            recoverable=True,
        )
    )

    assert len(events) == 1
    assert events[0].data["content"] == "ok"
    memory_service.finish_run.assert_not_awaited()
