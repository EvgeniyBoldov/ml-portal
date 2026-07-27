from uuid import uuid4

import pytest

from app.services.runtime_event_logger import (
    RuntimeEventLogger,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.services.runtime_progress_streamer import RuntimeProgressStreamer


def _logger(level: RuntimeLoggingLevel) -> RuntimeEventLogger:
    return RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=level, origin="chat",
    ))


def test_none_never_creates_runtime_events() -> None:
    logger = _logger(RuntimeLoggingLevel.NONE)
    assert logger.should_log("error") is False
    assert logger.should_log("agent_start") is False


def test_error_level_is_errors_only() -> None:
    logger = _logger(RuntimeLoggingLevel.ERROR)
    assert logger.should_log("error") is True
    assert logger.should_log("budget_rejected") is True
    assert logger.should_log("executor_started") is False


def test_brief_level_contains_lifecycle_and_snapshots_not_io() -> None:
    logger = _logger(RuntimeLoggingLevel.BRIEF)
    assert logger.should_log("agent_start") is True
    assert logger.should_log("budget_snapshot") is True
    assert logger.should_log("tool_call") is False
    assert logger.should_log("llm_response") is False
    assert logger.should_log("delta") is False
    assert logger.should_log("stop") is False


def test_errors_alias_normalizes_to_error_level() -> None:
    assert RuntimeLoggingLevel.parse("errors") is RuntimeLoggingLevel.ERROR


def test_full_payload_drops_debug_tracebacks() -> None:
    logger = _logger(RuntimeLoggingLevel.FULL)
    assert logger._payload({"safe": "ok", "debug": {"traceback": "private"}}) == {"safe": "ok"}


def test_worker_context_round_trip() -> None:
    context = RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox",
        stream_logs=True, stream_progress=True,
    )
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
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox",
        stream_logs=True, stream_progress=True,
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
        "caused_by_event_id": None,
        "duration_ms": None,
        "request": "hello",
        "occurred_at": published[0]["occurred_at"],
    }]


@pytest.mark.asyncio
async def test_direct_canonical_error_is_entity_and_live_stream_complete(monkeypatch) -> None:
    published: list[dict] = []

    class Session:
        def add(self, _row) -> None: pass
        async def flush(self) -> None: pass

    class Publisher:
        async def publish(self, *, stream_key: str, payload: dict) -> None:
            published.append(payload)

    context = RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="sandbox",
        stream_logs=True, stream_progress=True,
    )
    logger = RuntimeEventLogger(context=context, session=Session(), stream_publisher=Publisher())

    async def next_sequence(_session) -> int: return 9

    monkeypatch.setattr(logger, "_next_sequence", next_sequence)
    emitted = await logger.append_runtime_event(RuntimeEvent.error("router failed", duration_ms=25))

    assert published[0]["entity_type"] == "error"
    assert published[0]["parent_entity_id"] == str(context.run_id)
    assert published[0]["duration_ms"] == 25
    assert published[0]["caused_by_event_id"] is None
    assert emitted is not None
    assert emitted.data["_envelope"]["event_id"] == published[0]["event_id"]
    assert emitted.data["_envelope"]["sequence"] == published[0]["sequence"] == 9


def test_chat_root_progress_is_visible_without_root_persistence() -> None:
    logger = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.NONE, origin="chat",
        entity_type="run", stream_logs=False, stream_progress=True,
    ))

    assert logger.should_log("run_start") is False
    assert logger.should_publish_progress("run_start") is True
    assert logger.should_publish_progress("tool_call") is False


def test_agent_none_hides_agent_progress() -> None:
    logger = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.NONE, origin="chat",
        entity_type="agent_execution", stream_progress=True,
    ))

    assert logger.should_publish_progress("agent_start") is False


def test_agent_completion_progress_uses_bounded_summary() -> None:
    streamer = RuntimeProgressStreamer()
    progress = streamer.project(
        RuntimeEvent.agent_end(
            agent_execution_id="agent-1",
            parent_entity_id="iteration-1",
            agent_slug="researcher",
            summary=f"token=secret {'результат ' * 80}",
        ),
        run_id="run-1",
        phase=OrchestrationPhase.AGENT,
    )

    assert progress is not None
    assert progress["kind"] == "agent_end"
    assert len(progress["description"]) <= 240
