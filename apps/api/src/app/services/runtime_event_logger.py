"""Canonical persisted logger for runtime execution events.

The logger is deliberately scope-based: a child logger never mutates its
parent, which keeps entity ownership correct when executor runs are parallel.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.runtime_observability import RuntimeEventSequence, RuntimeExecutionEvent
from app.runtime.redactor import RuntimeRedactor
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.services.runtime_progress_streamer import RuntimeProgressStreamer

_IDENTITY_ENTITY_TYPES = {
    "run", "orchestrator", "planner_iteration", "step", "agent_execution",
    "attempt", "orchestrator_checkpoint", "synthesis_run", "llm_call",
    "tool_call", "interaction", "memory_component", "error",
}


def _validate_runtime_identity(entity_type: Any, entity_id: Any, parent_type: Any, parent_id: Any) -> None:
    """Reject ambiguous composite identities at the journal boundary."""
    for kind, value in ((entity_type, entity_id), (parent_type, parent_id)):
        if kind in _IDENTITY_ENTITY_TYPES and isinstance(value, str) and ":" in value:
            raise ValueError(f"Composite runtime identity is not allowed for {kind}: {value}")


class RuntimeLoggingLevel(StrEnum):
    NONE = "none"
    ERROR = "error"
    BRIEF = "brief"
    FULL = "full"

    @classmethod
    def parse(cls, value: str | None) -> "RuntimeLoggingLevel":
        if str(value or "").lower() == "errors":
            return cls.ERROR
        try:
            return cls(str(value or cls.BRIEF).lower())
        except ValueError:
            return cls.BRIEF


_BRIEF_EVENTS = frozenset({
    "run_start", "run_end", "orchestrator_start", "orchestrator_end",
    "planner_iteration_start", "planner_iteration_end", "planner_invocation_started", "planner_invocation_finished", "step_start", "step_end",
    "agent_start", "agent_end", "planner_decision", "plan_created", "plan_patch_applied",
    "plan_waiting_input", "plan_completed", "plan_failed", "task_ready", "task_claimed",
    "task_started", "task_paused", "task_resumed", "task_completed", "task_unfulfillable",
    "task_failed", "attempt_started", "attempt_succeeded", "attempt_failed",
    "attempt_retry_scheduled", "preflight_snapshot", "rbac_snapshot", "limits_snapshot",
    "preflight_started", "preflight_completed", "preflight_failed",
    "budget_snapshot", "budget_consumed", "budget_rejected", "intent", "final", "error",
    "waiting_input", "confirmation_required", "question_answer", "protocol_retry",
    "extraction_started", "extraction_completed", "extraction_failed",
})

_NEVER_PERSIST_EVENTS = frozenset({"delta", "stop"})


@dataclass(frozen=True)
class PersistedRuntimeEvent:
    """The single record used by both the journal and runtime transport."""

    event_id: UUID
    sequence: int
    occurred_at: datetime
    event: RuntimeEvent


@dataclass(frozen=True)
class RuntimeLogContext:
    """JSON transport contract for continuing a runtime trace in a worker."""

    run_id: UUID
    level: RuntimeLoggingLevel
    origin: str
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    parent_entity_type: Optional[str] = None
    parent_entity_id: Optional[str] = None
    # Raw journal-tail events and user-safe progress are intentionally separate.
    # Chat never exposes raw diagnostic events, but it can still show progress.
    stream_logs: bool = False
    stream_progress: bool = False
    correlation_id: Optional[str] = None
    version: int = 2

    def model_dump(self) -> dict[str, Any]:
        return {
            "version": self.version, "run_id": str(self.run_id), "level": self.level.value,
            "origin": self.origin, "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "chat_id": str(self.chat_id) if self.chat_id else None,
            "entity_type": self.entity_type, "entity_id": self.entity_id,
            "parent_entity_type": self.parent_entity_type,
            "parent_entity_id": self.parent_entity_id,
            "stream_logs": self.stream_logs,
            "stream_progress": self.stream_progress,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuntimeLogContext":
        return cls(
            run_id=UUID(str(payload["run_id"])), level=RuntimeLoggingLevel.parse(payload.get("level")),
            origin=str(payload.get("origin") or "worker"),
            tenant_id=UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None,
            user_id=UUID(str(payload["user_id"])) if payload.get("user_id") else None,
            chat_id=UUID(str(payload["chat_id"])) if payload.get("chat_id") else None,
            entity_type=payload.get("entity_type"), entity_id=payload.get("entity_id"),
            parent_entity_type=payload.get("parent_entity_type"),
            parent_entity_id=payload.get("parent_entity_id"),
            stream_logs=bool(payload.get("stream_logs")),
            stream_progress=bool(payload.get("stream_progress")),
            correlation_id=payload.get("correlation_id"), version=int(payload.get("version") or 2),
        )


class RuntimeEventLogger:
    def __init__(
        self, *, context: RuntimeLogContext, session: Optional[AsyncSession] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        stream_publisher: Optional[Any] = None,
        progress_streamer: Optional[RuntimeProgressStreamer] = None,
    ) -> None:
        self.context = context
        self._session = session
        self._session_factory = session_factory
        self._stream_publisher = stream_publisher
        self._progress_streamer = progress_streamer or RuntimeProgressStreamer()
        self._redactor = RuntimeRedactor()
        self._request_event_ids: dict[tuple[str, str], UUID] = {}

    def for_entity(
        self, *, entity_type: str, entity_id: str, parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None, level: Optional[RuntimeLoggingLevel] = None,
    ) -> "RuntimeEventLogger":
        return RuntimeEventLogger(
            context=replace(
                self.context, entity_type=entity_type, entity_id=entity_id,
                level=level or self.context.level,
                parent_entity_type=parent_entity_type if parent_entity_type is not None else self.context.entity_type,
                parent_entity_id=parent_entity_id if parent_entity_id is not None else self.context.entity_id,
            ), session=self._session, session_factory=self._session_factory,
            stream_publisher=self._stream_publisher,
            progress_streamer=self._progress_streamer,
        )

    def worker_payload(self) -> dict[str, Any]:
        return self.context.model_dump()

    def should_log(self, event_type: str) -> bool:
        if event_type in _NEVER_PERSIST_EVENTS:
            return False
        level = self.context.level
        if level is RuntimeLoggingLevel.NONE:
            return False
        if level is RuntimeLoggingLevel.ERROR:
            return event_type == "error" or event_type.endswith("_rejected")
        return level is RuntimeLoggingLevel.FULL or event_type in _BRIEF_EVENTS

    def should_publish_progress(self, event_type: str) -> bool:
        """Apply visibility policy without changing journal persistence policy."""
        if not self.context.stream_progress:
            return False
        # The chat root is intentionally non-persistent but still owns the
        # generic lifecycle visible to the user. Agent scopes below it obey
        # their configured observation level.
        if self.context.entity_type == "run":
            return event_type in {
                "run_start", "orchestrator_start", "planner_iteration_start",
                "plan_created", "plan_patch_applied", "task_started",
                "task_completed", "plan_completed", "confirmation_required",
                "waiting_input", "error",
            }
        return self.should_log(event_type)

    async def event(
        self, event_type: str, *, payload: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None, entity_id: Optional[str] = None,
        parent_entity_type: Optional[str] = None, parent_entity_id: Optional[str] = None,
        caused_by_event_id: Optional[UUID] = None, duration_ms: Optional[int] = None,
    ) -> Optional[UUID]:
        if not self.should_log(event_type):
            return None
        try:
            runtime_type = RuntimeEventType(event_type)
        except ValueError as exc:
            raise ValueError(f"Unknown canonical runtime event type: {event_type}") from exc
        persisted = await self._append(
            RuntimeEvent(runtime_type, payload or {}),
            phase=OrchestrationPhase.PIPELINE,
            entity_type=entity_type,
            entity_id=entity_id,
            parent_entity_type=parent_entity_type,
            parent_entity_id=parent_entity_id,
            caused_by_event_id=caused_by_event_id,
            duration_ms=duration_ms,
        )
        return persisted.event_id if persisted is not None else None

    async def append_runtime_event(
        self, runtime_event: RuntimeEvent, *, phase: OrchestrationPhase = OrchestrationPhase.PIPELINE,
    ) -> Optional[RuntimeEvent]:
        """Persist and project one canonical event with its DB-assigned envelope."""
        event_type = getattr(getattr(runtime_event, "type", None), "value", None)
        if not isinstance(event_type, str):
            raise TypeError("append_runtime_event expects RuntimeEvent")
        payload = dict(getattr(runtime_event, "data", {}) or {})
        if event_type == "error" and not payload.get("entity_id"):
            error_key = uuid4()
            payload.update({
                "entity_type": "error",
                "entity_id": str(error_key),
                "parent_entity_type": payload.get("parent_entity_type") or "run",
                "parent_entity_id": payload.get("parent_entity_id") or str(self.context.run_id),
            })
        _validate_runtime_identity(
            payload.get("entity_type"), payload.get("entity_id"),
            payload.get("parent_entity_type"), payload.get("parent_entity_id"),
        )
        caused_by = payload.get("caused_by_event_id")
        try:
            caused_by_event_id = UUID(str(caused_by)) if caused_by else None
        except (TypeError, ValueError):
            caused_by_event_id = None
        duration_ms = payload.get("duration_ms")
        persisted = await self._append(
            RuntimeEvent(runtime_event.type, payload),
            phase=phase,
            entity_type=payload.get("entity_type"),
            entity_id=payload.get("entity_id"),
            parent_entity_type=payload.get("parent_entity_type"),
            parent_entity_id=payload.get("parent_entity_id"),
            caused_by_event_id=caused_by_event_id,
            duration_ms=duration_ms if isinstance(duration_ms, int) else None,
        )
        return persisted.event if persisted is not None else None

    async def emit(self, event: RuntimeEvent, *, phase: OrchestrationPhase) -> RuntimeEvent:
        """Admit one semantic event, optionally persist it, and project progress."""
        data = dict(event.data)
        entity_key = (str(data.get("entity_type") or ""), str(data.get("entity_id") or ""))
        if not data.get("caused_by_event_id") and event.type.value in {"llm_response", "tool_result", "protocol_retry"}:
            caused_by = self._request_event_ids.get(entity_key)
            if caused_by is not None:
                data["caused_by_event_id"] = str(caused_by)
        admitted = RuntimeEvent(event.type, data)
        presentation_data = self._redactor.redact({
            key: value for key, value in data.items()
            if key not in {"debug", "traceback", "stack_trace", "raw_traceback"}
        })
        progress = self._progress_streamer.project(
            RuntimeEvent(event.type, presentation_data), run_id=str(self.context.run_id), phase=phase,
        )
        if progress is not None:
            admitted.data["_progress"] = progress
        persisted = await self.append_runtime_event(admitted, phase=phase)
        result = persisted or admitted
        if event.type.value in {"llm_request", "tool_call"} and persisted is not None:
            envelope = persisted.data.get("_envelope") or {}
            if envelope.get("event_id"):
                self._request_event_ids[entity_key] = UUID(str(envelope["event_id"]))
        if progress is not None and self.should_publish_progress(event.type.value):
            await self._publish_progress(progress)
        return result

    async def _publish_progress(self, progress: dict[str, Any]) -> None:
        try:
            publisher = self._stream_publisher
            if publisher is None:
                from app.services.runtime_tail_event_bus import RuntimeTailEventBus
                publisher = RuntimeTailEventBus()
            await publisher.publish(stream_key=str(self.context.run_id), payload=progress)
            try:
                from app.core.prometheus_metrics import runtime_progress_published_total
                runtime_progress_published_total.labels(origin=self.context.origin).inc()
            except Exception:
                pass
        except Exception:
            try:
                from app.core.prometheus_metrics import runtime_progress_delivery_failures_total
                runtime_progress_delivery_failures_total.labels(origin=self.context.origin).inc()
            except Exception:
                pass

    async def error(self, error: Exception | str, *, payload: Optional[dict[str, Any]] = None) -> Optional[UUID]:
        from app.runtime.events import RuntimeEvent

        data = dict(payload or {})
        data.update({"error_type": type(error).__name__ if isinstance(error, Exception) else "RuntimeError"})
        event = await self.append_runtime_event(RuntimeEvent.error(str(error), **data))
        envelope = event.data.get("_envelope", {}) if event is not None else {}
        return UUID(str(envelope["event_id"])) if envelope.get("event_id") else None

    async def _append(
        self, runtime_event: RuntimeEvent, *, phase: OrchestrationPhase,
        entity_type: Optional[str], entity_id: Optional[str], parent_entity_type: Optional[str],
        parent_entity_id: Optional[str], caused_by_event_id: Optional[UUID], duration_ms: Optional[int],
    ) -> Optional[PersistedRuntimeEvent]:
        event_type = runtime_event.type.value
        if not self.should_log(event_type):
            return None
        clean_payload = self._payload(dict(runtime_event.data or {}))
        event_id = uuid4()
        occurred_at = datetime.now(timezone.utc)
        sequence: int | None = None
        resolved_entity_type = entity_type or self.context.entity_type
        resolved_entity_id = entity_id or self.context.entity_id
        resolved_parent_type = parent_entity_type if parent_entity_type is not None else self.context.parent_entity_type
        resolved_parent_id = parent_entity_id if parent_entity_id is not None else self.context.parent_entity_id

        async def append(session: AsyncSession) -> None:
            nonlocal sequence
            sequence = await self._next_sequence(session)
            session.add(RuntimeExecutionEvent(
                id=event_id, run_id=self.context.run_id, sequence=sequence, event_type=event_type,
                tenant_id=self.context.tenant_id, user_id=self.context.user_id, chat_id=self.context.chat_id,
                origin=self.context.origin, entity_type=resolved_entity_type, entity_id=resolved_entity_id,
                parent_entity_type=resolved_parent_type, parent_entity_id=resolved_parent_id,
                caused_by_event_id=caused_by_event_id, logging_level=self.context.level.value,
                schema_version=1, duration_ms=duration_ms, payload_hash=self._hash(clean_payload),
                payload=clean_payload, occurred_at=occurred_at,
            ))
            await session.flush()

        try:
            if self._session is not None:
                await append(self._session)
            else:
                factory = self._session_factory
                if factory is None:
                    from app.core.db import get_session_factory
                    factory = get_session_factory()
                async with factory() as session:
                    async with session.begin():
                        await append(session)
        except Exception:
            try:
                from app.core.prometheus_metrics import runtime_journal_append_failures_total
                runtime_journal_append_failures_total.labels(origin=self.context.origin).inc()
            except Exception:
                pass
            raise
        assert sequence is not None
        try:
            from app.core.prometheus_metrics import record_runtime_journal_event
            record_runtime_journal_event(
                event_type=event_type, origin=self.context.origin, duration_ms=duration_ms,
            )
        except Exception:
            # Metrics must never become a dependency of the runtime journal.
            pass
        wire = runtime_event.with_envelope(
            phase=phase, sequence=sequence, run_id=str(self.context.run_id),
            chat_id=str(self.context.chat_id) if self.context.chat_id else None,
            event_id=str(event_id), occurred_at=occurred_at.isoformat(),
        )
        if self.context.stream_logs:
            try:
                publisher = self._stream_publisher
                if publisher is None:
                    from app.services.runtime_tail_event_bus import RuntimeTailEventBus
                    publisher = RuntimeTailEventBus()
                await publisher.publish(stream_key=str(self.context.run_id), payload={
                    "type": event_type, "run_id": str(self.context.run_id), "event_id": str(event_id),
                    "sequence": sequence, "entity_type": resolved_entity_type, "entity_id": resolved_entity_id,
                    "parent_entity_type": resolved_parent_type, "parent_entity_id": resolved_parent_id,
                    "caused_by_event_id": str(caused_by_event_id) if caused_by_event_id else None,
                    "duration_ms": duration_ms, "occurred_at": occurred_at.isoformat(), **clean_payload,
                })
            except Exception:
                try:
                    from app.core.prometheus_metrics import runtime_progress_delivery_failures_total
                    runtime_progress_delivery_failures_total.labels(origin=self.context.origin).inc()
                except Exception:
                    pass
        return PersistedRuntimeEvent(event_id=event_id, sequence=sequence, occurred_at=occurred_at, event=wire)

    async def _next_sequence(self, session: AsyncSession) -> int:
        row = (await session.execute(
            select(RuntimeEventSequence).where(RuntimeEventSequence.run_id == self.context.run_id).with_for_update()
        )).scalar_one_or_none()
        if row is None:
            session.add(RuntimeEventSequence(run_id=self.context.run_id, next_sequence=2))
            return 1
        sequence = row.next_sequence
        row.next_sequence += 1
        return sequence

    def _payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"debug", "traceback", "stack_trace", "raw_traceback"}
        }
        redacted = self._redactor.redact(safe_payload)
        if self.context.level is RuntimeLoggingLevel.FULL:
            return redacted
        heavy = {"messages", "prompt", "system_prompt", "content", "arguments", "input", "output", "result", "raw_response"}
        result: dict[str, Any] = {}
        for key, value in redacted.items():
            if key in heavy:
                raw = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
                result[f"{key}_hash"] = hashlib.sha256(raw.encode()).hexdigest()
                result[f"{key}_length"] = len(raw)
            else:
                result[key] = value
        return result

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()


class RuntimeEventJournalFactory:
    """Only construction boundary for root and worker runtime journals."""

    @staticmethod
    def create(
        *, context: RuntimeLogContext, session: Optional[AsyncSession] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        stream_publisher: Optional[Any] = None,
    ) -> RuntimeEventLogger:
        return RuntimeEventLogger(
            context=context,
            session=session,
            session_factory=session_factory,
            stream_publisher=stream_publisher,
        )

    @staticmethod
    def restore_worker(
        payload: dict[str, Any], *, session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> RuntimeEventLogger:
        return RuntimeEventJournalFactory.create(
            context=replace(RuntimeLogContext.from_payload(payload), origin="worker"),
            session_factory=session_factory,
        )
