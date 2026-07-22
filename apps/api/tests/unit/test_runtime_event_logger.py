from uuid import uuid4

import pytest

from app.services.runtime_event_logger import (
    RuntimeEventLogger,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)


def _logger(level: RuntimeLoggingLevel) -> RuntimeEventLogger:
    return RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=level, origin="chat",
    ))


def test_none_never_creates_runtime_events() -> None:
    logger = _logger(RuntimeLoggingLevel.NONE)
    assert logger.should_log("error") is False
    assert logger.should_log("executor_started") is False


def test_error_level_is_errors_only() -> None:
    logger = _logger(RuntimeLoggingLevel.ERROR)
    assert logger.should_log("error") is True
    assert logger.should_log("budget_rejected") is True
    assert logger.should_log("executor_started") is False


def test_brief_level_contains_lifecycle_and_snapshots_not_io() -> None:
    logger = _logger(RuntimeLoggingLevel.BRIEF)
    assert logger.should_log("executor_started") is True
    assert logger.should_log("budget_snapshot") is True
    assert logger.should_log("tool_request") is False
    assert logger.should_log("llm_response") is False


def test_worker_context_round_trip() -> None:
    context = RuntimeLogContext(run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox", stream=True)
    restored = RuntimeLogContext.from_payload(context.model_dump())
    assert restored == context


@pytest.mark.asyncio
async def test_streaming_logger_publishes_the_persisted_event(monkeypatch) -> None:
    published: list[dict] = []

    class Session:
        def add(self, _row) -> None:
            pass

        async def flush(self) -> None:
            pass

    class Publisher:
        async def publish(self, *, stream_key: str, payload: dict) -> None:
            assert stream_key == str(context.run_id)
            published.append(payload)

    context = RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox", stream=True,
    )
    logger = RuntimeEventLogger(context=context, session=Session(), stream_publisher=Publisher())

    async def next_sequence(_session) -> int:
        return 7

    monkeypatch.setattr(logger, "_next_sequence", next_sequence)
    event_id = await logger.event("run_start", payload={"request": "hello"})

    assert published == [{
        "type": "run_start",
        "run_id": str(context.run_id),
        "event_id": str(event_id),
        "sequence": 7,
        "entity_type": None,
        "entity_id": None,
        "parent_entity_type": None,
        "parent_entity_id": None,
        "request": "hello",
        "occurred_at": published[0]["occurred_at"],
    }]
