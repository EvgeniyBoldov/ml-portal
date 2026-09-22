from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.runtime_logging_resolver import RuntimeLoggingResolver
from app.services.runtime_event_logger import (
    RuntimeEventLogger,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)


@pytest.mark.asyncio
async def test_nested_agent_runtime_inherits_existing_agent_scope() -> None:
    logger = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="chat",
        entity_type="agent_execution", entity_id="agent-1",
    ))
    ctx = SimpleNamespace(extra={"runtime_event_logger": logger})

    resolved = await RuntimeLoggingResolver().resolve_logging_level(ctx, "brief")

    assert resolved is RuntimeLoggingLevel.FULL


@pytest.mark.asyncio
async def test_chat_root_none_does_not_hide_a_direct_agent_scope() -> None:
    logger = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.NONE, origin="chat",
        entity_type="run",
    ))
    ctx = SimpleNamespace(extra={"runtime_event_logger": logger})

    resolved = await RuntimeLoggingResolver().resolve_logging_level(ctx, "full")

    assert resolved is RuntimeLoggingLevel.FULL


@pytest.mark.asyncio
async def test_sandbox_forces_full_observation_for_nested_agent_runtime() -> None:
    logger = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox",
        entity_type="run",
    ))
    ctx = SimpleNamespace(extra={"runtime_event_logger": logger})

    resolved = await RuntimeLoggingResolver().resolve_logging_level(ctx, "none")

    assert resolved is RuntimeLoggingLevel.FULL
