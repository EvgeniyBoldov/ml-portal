"""Accounting is independent of diagnostics and excludes sandbox at admission."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.services.platform_usage_service import record_usage
from app.services.runtime_event_logger import RuntimeEventLogger, RuntimeLogContext, RuntimeLoggingLevel


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["sandbox", "worker", "health", "unknown"])
async def test_nonproduction_origins_never_open_accounting_session(origin):
    factory = Mock(side_effect=AssertionError("must not access database"))
    context = SimpleNamespace(origin=origin, user_id=uuid4())
    await record_usage(context, "llm_response", {"entity_id": str(uuid4())}, factory)
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_none_diagnostic_level_still_accounts_for_request(monkeypatch):
    accounting = AsyncMock()
    monkeypatch.setattr("app.services.platform_usage_service.record_usage", accounting)
    context = RuntimeLogContext(run_id=uuid4(), user_id=uuid4(), origin="chat", level=RuntimeLoggingLevel.NONE)
    journal = RuntimeEventLogger(context=context)
    await journal.emit(RuntimeEvent.run_start(run_id=str(context.run_id)), phase=OrchestrationPhase.PIPELINE)
    accounting.assert_awaited_once()
    assert accounting.call_args.args[1] == "run_start"
    assert journal.should_log("run_start") is False


@pytest.mark.asyncio
async def test_accounting_retains_only_scalars_and_distinguishes_attempts(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("app.services.platform_usage_service.PlatformUsageRepository", lambda _: SimpleNamespace(upsert=upsert))

    @asynccontextmanager
    async def transaction():
        yield

    @asynccontextmanager
    async def session():
        yield SimpleNamespace(begin=transaction)

    context = SimpleNamespace(origin="chat", user_id=uuid4(), run_id=uuid4())
    call_id = str(uuid4())
    for attempt in (1, 2):
        await record_usage(context, "llm_response", {
            "entity_id": call_id, "model": "llm.production", "attempt": attempt,
            "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            "messages": [{"content": "private request"}], "content": "private answer",
        }, session)
    first, second = [call.args[0] for call in upsert.await_args_list]
    assert first["entity_id"] != second["entity_id"]
    assert first["tokens_in"] == 40 and first["tokens_out"] == 10
    assert first["token_source"] == "provider"
    assert "private" not in str(first)
    assert "messages" not in first and "content" not in first


@pytest.mark.asyncio
async def test_accounting_failure_does_not_fail_runtime():
    context = SimpleNamespace(origin="shadow", user_id=uuid4(), run_id=uuid4())
    factory = Mock(side_effect=RuntimeError("database unavailable"))
    await record_usage(context, "run_end", {"entity_id": str(context.run_id)}, factory)
