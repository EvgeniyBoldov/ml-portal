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


class RuntimeLoggingLevel(StrEnum):
    NONE = "none"
    ERROR = "error"
    BRIEF = "brief"
    FULL = "full"

    @classmethod
    def parse(cls, value: str | None) -> "RuntimeLoggingLevel":
        try:
            return cls(str(value or cls.BRIEF).lower())
        except ValueError:
            return cls.BRIEF


_BRIEF_EVENTS = frozenset({
    "run_started", "run_finished", "orchestrator_started", "orchestrator_finished",
    "iteration_started", "iteration_finished", "executor_started", "executor_finished",
    "planner_decision", "task_started", "task_finished", "attempt_started",
    "attempt_finished", "rbac_snapshot", "limit_snapshot", "budget_snapshot",
    "budget_rejected", "final", "error", "waiting_input", "confirmation_required", "question_answer",
})


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
    stream: bool = False
    correlation_id: Optional[str] = None
    version: int = 1

    def model_dump(self) -> dict[str, Any]:
        return {
            "version": self.version, "run_id": str(self.run_id), "level": self.level.value,
            "origin": self.origin, "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "chat_id": str(self.chat_id) if self.chat_id else None,
            "entity_type": self.entity_type, "entity_id": self.entity_id,
            "parent_entity_type": self.parent_entity_type,
            "parent_entity_id": self.parent_entity_id, "stream": self.stream,
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
            parent_entity_id=payload.get("parent_entity_id"), stream=bool(payload.get("stream")),
            correlation_id=payload.get("correlation_id"), version=int(payload.get("version") or 1),
        )


class RuntimeEventLogger:
    def __init__(
        self, *, context: RuntimeLogContext, session: Optional[AsyncSession] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        stream_publisher: Optional[Any] = None,
    ) -> None:
        self.context = context
        self._session = session
        self._session_factory = session_factory
        self._stream_publisher = stream_publisher
        self._redactor = RuntimeRedactor()

    @classmethod
    def disabled(cls) -> "NoopRuntimeEventLogger":
        return NoopRuntimeEventLogger()

    def for_entity(
        self, *, entity_type: str, entity_id: str, parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
    ) -> "RuntimeEventLogger":
        return RuntimeEventLogger(
            context=replace(
                self.context, entity_type=entity_type, entity_id=entity_id,
                parent_entity_type=parent_entity_type if parent_entity_type is not None else self.context.entity_type,
                parent_entity_id=parent_entity_id if parent_entity_id is not None else self.context.entity_id,
            ), session=self._session, session_factory=self._session_factory,
            stream_publisher=self._stream_publisher,
        )

    def worker_payload(self) -> dict[str, Any]:
        return self.context.model_dump()

    def should_log(self, event_type: str) -> bool:
        level = self.context.level
        if level is RuntimeLoggingLevel.NONE:
            return False
        if level is RuntimeLoggingLevel.ERROR:
            return event_type == "error" or event_type.endswith("_rejected")
        return level is RuntimeLoggingLevel.FULL or event_type in _BRIEF_EVENTS

    async def event(
        self, event_type: str, *, payload: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None, entity_id: Optional[str] = None,
        parent_entity_type: Optional[str] = None, parent_entity_id: Optional[str] = None,
        caused_by_event_id: Optional[UUID] = None, duration_ms: Optional[int] = None,
    ) -> Optional[UUID]:
        if not self.should_log(event_type):
            return None
        clean_payload = self._payload(payload or {})
        event_id = uuid4()
        sequence: int | None = None
        async def append(session: AsyncSession) -> None:
            nonlocal sequence
            sequence = await self._next_sequence(session)
            session.add(RuntimeExecutionEvent(
                id=event_id, run_id=self.context.run_id, sequence=sequence, event_type=event_type,
                tenant_id=self.context.tenant_id, user_id=self.context.user_id, chat_id=self.context.chat_id,
                origin=self.context.origin, entity_type=entity_type or self.context.entity_type,
                entity_id=entity_id or self.context.entity_id,
                parent_entity_type=parent_entity_type if parent_entity_type is not None else self.context.parent_entity_type,
                parent_entity_id=parent_entity_id if parent_entity_id is not None else self.context.parent_entity_id,
                caused_by_event_id=caused_by_event_id, logging_level=self.context.level.value,
                schema_version=1, duration_ms=duration_ms, payload_hash=self._hash(clean_payload),
                payload=clean_payload, occurred_at=datetime.now(timezone.utc),
            ))
            await session.flush()

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
        if self.context.stream:
            publisher = self._stream_publisher
            if publisher is None:
                from app.services.runtime_tail_event_bus import RuntimeTailEventBus
                publisher = RuntimeTailEventBus()
            await publisher.publish(
                stream_key=str(self.context.run_id),
                payload={
                    "type": event_type,
                    "run_id": str(self.context.run_id),
                    "event_id": str(event_id),
                    "sequence": sequence,
                    "entity_type": entity_type or self.context.entity_type,
                    "entity_id": entity_id or self.context.entity_id,
                    "parent_entity_type": (
                        parent_entity_type
                        if parent_entity_type is not None
                        else self.context.parent_entity_type
                    ),
                    "parent_entity_id": (
                        parent_entity_id
                        if parent_entity_id is not None
                        else self.context.parent_entity_id
                    ),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    **clean_payload,
                },
            )
        return event_id

    async def error(self, error: Exception | str, *, payload: Optional[dict[str, Any]] = None) -> Optional[UUID]:
        data = dict(payload or {})
        data.update({"message": str(error), "error_type": type(error).__name__ if isinstance(error, Exception) else "RuntimeError"})
        return await self.event("error", payload=data)

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
        redacted = self._redactor.redact(payload)
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


class NoopRuntimeEventLogger:
    context = None
    def for_entity(self, **_: Any) -> "NoopRuntimeEventLogger": return self
    def worker_payload(self) -> dict[str, Any]: return {}
    def should_log(self, _: str) -> bool: return False
    async def event(self, *_: Any, **__: Any) -> None: return None
    async def error(self, *_: Any, **__: Any) -> None: return None
